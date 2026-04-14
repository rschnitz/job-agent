#!/usr/bin/env python3
"""
Job Scout Scraper - runs every 30 min via cron
Uses JobSpy for multi-board scraping with Claude relevance filtering
"""

import os
import sqlite3
import json
import logging
import re
import time
import requests
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from jobspy import scrape_jobs
from discord_webhook import DiscordWebhook, DiscordEmbed
import anthropic
import sys
sys.path.insert(0, os.path.expanduser("~/src/job-search-lib"))
from job_search_lib.scoring import quick_score as lib_quick_score, classify_role, JobResult
from job_search_lib.compensation import compute_total_comp

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
INGEST_URL = os.getenv("INGEST_URL", "https://job-agent-henna.vercel.app/api/jobs/ingest")
INGEST_API_KEY = os.getenv("INGEST_API_KEY")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "scraper.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %I:%M:%S %p"
)

# Search terms — consolidated with boolean OR to reduce LinkedIn queries
# Each string is one query. OR combines equivalent title searches.
SEARCH_TERMS = [
    '"Engineering Manager" OR "Senior Engineering Manager"',
    '"Director of Engineering" OR "Head of Engineering" OR "VP Engineering"',
    '"Principal Engineer" OR "Staff Engineer"',
]

# Domain-targeted search — runs as additional query, not replacement
# Wider title range but filtered by domain keywords
DOMAIN_SEARCH_TERMS = [
    '"Engineering Manager" AND ("identity" OR "authentication" OR "security")',
    '"Engineering Manager" AND ("fintech" OR "platform" OR "payments")',
]

# No intern or comms searches for this profile
INTERN_SEARCH_TERMS = []
PROMPT_ENG_SEARCH_TERMS = []
COMMS_SEARCH_TERMS = []

HIGH_CONVERSION_COMPANIES = []  # Not used for this profile

# Single search center — 40mi radius covers SF, Oakland, Berkeley, and upper Peninsula
SEARCH_CENTER = "Orinda, CA"
SEARCH_RADIUS = 40  # miles

WATCHLIST_COMPANIES = [
    "anthropic", "nvidia", "openai", "stripe", "plaid", "perplexity",
    "playstation", "sony", "sony interactive entertainment",
    "splunk", "cisco", "thousandeyes",
    "apple", "meta", "wealthfront",
    "lendingclub", "ratiotech", "redfin", "zillow",
    "postman", "quizlet", "semgrep",
    "databricks", "snowflake", "rippling", "doordash",
    "figma", "notion", "linear", "vercel", "cloudflare",
    "hashicorp", "confluent", "netflix", "scale ai", "cohere",
]

EXCLUDE_INDUSTRIES = [
    "hospital", "clinic", "legal",
    "pharmaceutical", "pharma", "dental", "therapy", "staffing",
    "recruiting agency", "we are hiring on behalf", "blockchain", "cryptocurrency",
]

# Job aggregator sites — exclude only when the company name IS the aggregator
# (not when the aggregator lists a real company's role)
JOB_AGGREGATORS = [
    "lensa", "ziprecruiter", "remotehunter", "jobs via dice",
]

REPOST_SIGNALS = [
    "repost", "re-post", "reposting", "re-posting",
    "previously posted", "originally posted", "posting again",
    "reactivated", "re-listed", "relisted", "re-opening",
]

EXCLUDED_TITLES = [
    "software engineer", "data engineer", "data scientist",
    "machine learning engineer", "ml engineer",
    "head of machine learning", "head of ml", "head of data science",
    "research scientist", "applied scientist",
    "mechanical engineer",
    "electrical engineer", "hardware engineer",
    "civil engineer", "structural engineer", "chemical engineer",
    "nurse", "physician", "therapist", "dentist", "teacher",
    "scientist", "researcher", "accountant",
    "attorney", "paralegal", "intern",
    "associate engineer", "junior engineer", "entry level",
    "new grad", "manufacturing engineer", "controls engineer",
    "sales development", "business development representative",
    "sdr", "bdr", "account executive entry",
    "sales representative", "sales associate",
    "product manager", "program manager", "project manager",
    "category manager", "account manager",
    "sales specialist", "sales manager",
    "substation engineer", "power engineer",
    "security specialist", "information security",
]

# Companies to skip entirely (non-tech manufacturing/consulting)
EXCLUDED_COMPANIES = [
    "foth companies", "pinnacle method",
]



def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_url TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            date_found TEXT,
            outcome TEXT,
            score INTEGER
        )
    """)
    # Migrate: add columns if missing (existing DBs won't have them)
    try:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN outcome TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE seen_jobs ADD COLUMN score INTEGER")
    except sqlite3.OperationalError:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            job_url TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            status TEXT DEFAULT 'applied',
            date_added TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    return conn


def is_seen(conn, job_url):
    return conn.execute("SELECT 1 FROM seen_jobs WHERE job_url = ?", (job_url,)).fetchone() is not None


def get_seen_score(conn, job_url):
    """Get the stored outcome and score for a previously seen job."""
    row = conn.execute("SELECT outcome, score FROM seen_jobs WHERE job_url = ?", (job_url,)).fetchone()
    if row:
        return row[0], row[1]  # outcome, score
    return None, None


def mark_seen(conn, job_url, title="", company="", outcome="", score=None):
    conn.execute(
        "INSERT OR IGNORE INTO seen_jobs (job_url, title, company, date_found, outcome, score) VALUES (?, ?, ?, ?, ?, ?)",
        (job_url, str(title), str(company), datetime.now(timezone.utc).isoformat(), outcome, score)
    )
    conn.commit()


POSTING_CACHE_DIR = os.path.expanduser("~/.cache/job-search/postings")
CACHE_TTL_DAYS = 7


def _job_id_from_url(url):
    """Extract LinkedIn job ID from URL for cache keying."""
    m = re.search(r'/view/(\d+)', url)
    return m.group(1) if m else None


def _cache_get(job_url):
    """Check posting cache. Returns (html, text, fetch_time) or (None, None, None)."""
    job_id = _job_id_from_url(job_url)
    if not job_id:
        return None, None, None
    cache_dir = os.path.join(POSTING_CACHE_DIR, job_id)
    html_path = os.path.join(cache_dir, "page.html")
    text_path = os.path.join(cache_dir, "text.txt")
    meta_path = os.path.join(cache_dir, "meta.json")
    if not os.path.exists(html_path):
        return None, None, None
    try:
        with open(meta_path) as f:
            meta = json.load(f)
        fetch_time = meta.get("fetched_at", "")
        # Check TTL
        from datetime import timedelta
        fetched = datetime.fromisoformat(fetch_time)
        if datetime.now(timezone.utc) - fetched > timedelta(days=CACHE_TTL_DAYS):
            return None, None, None  # expired
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
        text = None
        if os.path.exists(text_path):
            with open(text_path, encoding="utf-8") as f:
                text = f.read()
        return html, text, fetch_time
    except Exception:
        return None, None, None


def _cache_put(job_url, html, text):
    """Store posting in cache."""
    job_id = _job_id_from_url(job_url)
    if not job_id:
        return
    cache_dir = os.path.join(POSTING_CACHE_DIR, job_id)
    os.makedirs(cache_dir, exist_ok=True)
    with open(os.path.join(cache_dir, "page.html"), "w", encoding="utf-8") as f:
        f.write(html)
    if text:
        with open(os.path.join(cache_dir, "text.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(cache_dir, "meta.json"), "w") as f:
        json.dump({"url": job_url, "fetched_at": datetime.now(timezone.utc).isoformat()}, f)


def _parse_job_page(html):
    """Extract description, applicant count, and repost flag from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    full_desc = None
    for selector in [
        ".show-more-less-html__markup",
        ".description__text",
        ".job-description",
        "[data-testid='job-description']",
        ".jobsearch-jobDescriptionText",
    ]:
        el = soup.select_one(selector)
        if el and len(el.get_text(strip=True)) > 200:
            full_desc = el.get_text(separator="\n", strip=True)
            break

    applicant_count = None
    page_text = soup.get_text()
    for pattern in [
        r"(\d[\d,]+)\s+applicants?",
        r"Over\s+(\d[\d,]+)\s+applicants?",
        r"Be among the first\s+(\d+)",
        r"(\d+)\s+people\s+clicked\s+apply",
        r"(\d+)\s+clicked\s+apply",
    ]:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            try:
                applicant_count = int(match.group(1).replace(",", ""))
            except ValueError:
                pass
            break

    page_repost = bool(re.search(r"reposted", html, re.IGNORECASE))
    return full_desc, applicant_count, page_repost


def fetch_full_job_details(job_url):
    """Fetch full description and applicant count, using cache when available."""
    # Check cache first
    cached_html, cached_text, _ = _cache_get(job_url)
    if cached_html:
        logging.info(f"Cache hit: {job_url}")
        return _parse_job_page(cached_html)

    # Fetch from LinkedIn
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(job_url, headers=headers, timeout=15)
        html = resp.text

        full_desc, applicant_count, page_repost = _parse_job_page(html)

        # Cache the result
        _cache_put(job_url, html, full_desc)

        return full_desc, applicant_count, page_repost
    except Exception as e:
        logging.warning(f"Failed to fetch job details from {job_url}: {e}")
        return None, None, False


def quick_filter(job):
    title = str(job.get("title") or "").lower()
    company = str(job.get("company") or "").lower()
    title_company = title + " " + company

    if any(c in company for c in EXCLUDED_COMPANIES):
        return False, "excluded company"
    # Job aggregators: exclude only when the company name IS the aggregator
    # (real companies listing through aggregators will have the actual company name)
    if any(company.strip() == agg or company.startswith(agg) for agg in JOB_AGGREGATORS):
        return False, "job aggregator listing"
    if any(term in title_company for term in EXCLUDE_INDUSTRIES):
        return False, "excluded industry"
    if any(t in title for t in EXCLUDED_TITLES):
        return False, "excluded title"

    min_sal = job.get("min_amount")
    max_sal = job.get("max_amount")
    if min_sal and max_sal:
        try:
            if float(max_sal) < 150000:
                return False, f"salary too low: {max_sal}"
        except (ValueError, TypeError):
            pass

    return True, "ok"


def detect_repost(job):
    """Return True if the job shows signs of being a repost.
    Reposts get a fresh timestamp but are stale -- don't treat them as newly listed.
    """
    title = str(job.get("title") or "").lower()
    desc = str(job.get("description") or "").lower()[:600]
    combined = title + " " + desc
    return any(signal in combined for signal in REPOST_SIGNALS)


def passes_or_filter(job, is_repost=False):
    """Pass if posted < 2 hours ago OR applicants < 10.
    Reposts are never treated as fresh regardless of their timestamp.
    Returns (passes, age_hours, applicant_count).
    """
    applicant_count = job.get("applicants")
    age_hours = None

    date_posted = job.get("date_posted")
    if date_posted:
        try:
            now = datetime.now(timezone.utc)
            dp = date_posted
            if hasattr(dp, "tzinfo") and dp.tzinfo is None:
                dp = dp.replace(tzinfo=timezone.utc)
            age_hours = (now - dp).total_seconds() / 3600
        except Exception:
            pass

    # Reposts get a fresh timestamp but are stale -- ignore age for them
    age_under_2hrs = not is_repost and age_hours is not None and age_hours <= 2
    few_applicants = applicant_count is not None and applicant_count < 10

    if age_under_2hrs or few_applicants:
        return True, age_hours, applicant_count

    # Job is old (or reposted) -- require confirmed low applicant count to proceed.
    # Unknown applicant count on a non-fresh job is assumed stale.
    if age_hours is not None and age_hours > 2:
        return False, age_hours, applicant_count

    # Age truly unknown -- let Claude decide
    return True, age_hours, applicant_count


def get_rejection_context():
    """Pull recent rejection reasons from DB to inform Claude."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            """SELECT title, company, reason FROM rejections
               WHERE reason IS NOT NULL AND reason != ''
               ORDER BY date_rejected DESC LIMIT 15"""
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["Ray has recently passed on these roles and here's why (use this to calibrate):"]
        for title, company, reason in rows:
            lines.append(f"  - {title} @ {company}: \"{reason}\"")
        return "\n".join(lines)
    except Exception:
        return ""


def claude_relevance_check(job):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    rejection_context = get_rejection_context()

    prompt = f"""You are filtering job postings for Ray Schnitzler, an engineering leader who helps teams deliver production systems companies can rely on.

Target profile:
- Roles: Engineering Manager, Senior Engineering Manager, Director of Engineering, Head of Engineering, VP Engineering, Principal/Staff Engineer
- Background: MIT BS/MS CS+EE. Built teams from 0→20+ multiple times. Led enterprise auth platform securing tens of millions of daily users at Wells Fargo. Currently building production AI platform at Lexicon Branding (Next.js, Supabase, LLM workflows). Independent consulting for energy trading ops, platform migrations. $2M+ fraud savings, multiple US patents.
- AI experience: Strong at building systems that USE AI (LLM integration, function-calling frameworks, AI-enabled platforms). NOT an ML/data science practitioner — exclude roles where core job is training models, ML research, or building ML infrastructure.
- Industries: Fintech, authentication/identity, platform engineering, developer tools, AI-enabled products (not pure ML/AI research), energy/trading (no healthcare, insurance, staffing)
- Location: Bay Area (SF, Oakland, Berkeley, East Bay) or Remote. South Bay acceptable but less preferred.
- Compensation: $200k+ total comp baseline
- Experience: 20+ years — roles should be senior IC (Staff+) or management/director level
- Exclude: entry-level roles, junior roles, BDR/SDR, roles requiring < 10 years experience, non-tech industries, contract/temp roles, pure ML/data science roles, ML research positions

{rejection_context}

Job posting:
Title: {job.get("title")}
Company: {job.get("company")}
Location: {job.get("location")}
Description (first 3000 chars): {str(job.get("description") or "")[:3000]}

Respond with JSON only:
{{
  "relevant": true or false,
  "reason": "one sentence max",
  "fit_score": 1 to 10,
  "experience_match": "e.g. strong match, overqualified, underleveled",
  "location_ok": true or false
}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        logging.warning(f"Claude check failed: {e}")
        return {"relevant": False, "reason": "api error", "fit_score": 0}


def claude_prompt_eng_check(job):
    """Unused — kept as stub for compatibility."""
    return claude_relevance_check(job)


def claude_comms_check(job):
    """Unused — kept as stub for compatibility."""
    return claude_relevance_check(job)


def determine_urgency(fit_score, age_hours, applicant_count):
    """Determine urgency tier based on score, freshness, and applicant count.

    Tiers (overlapping ranges, highest matching tier wins):
      URGENT: score 8+ AND (<1h OR <=25 applicants)  [25 is temporary until counts are accurate]
      HIGH:   score 6+ AND (<4h OR <25 applicants)
      MEDIUM: score 5+ AND (<24h OR <50 applicants)
      LOW:    everything else
    """
    score = fit_score or 0
    fresh_1h = age_hours is not None and age_hours < 1
    fresh_4h = age_hours is not None and age_hours < 4
    fresh_24h = age_hours is not None and age_hours < 24
    few_25 = applicant_count is not None and applicant_count <= 25  # temporary threshold
    few_50 = applicant_count is not None and applicant_count < 50

    if score >= 8 and (fresh_1h or few_25):
        return "URGENT"
    if score >= 6 and (fresh_4h or few_25):
        return "HIGH"
    if score >= 5 and (fresh_24h or few_50):
        return "MEDIUM"
    return "LOW"


URGENCY_CONFIG = {
    "URGENT": {"color": "FF0000", "prefix": "🚨 URGENT", "ping": True},
    "HIGH":   {"color": "FF8C00", "prefix": "⚡ HIGH",   "ping": True},
    "MEDIUM": {"color": "03b2f8", "prefix": "📋",        "ping": False},
    "LOW":    {"color": "808080", "prefix": "📋",        "ping": False},
}


def send_discord_alert(job, analysis, is_intern=False, is_prompt_eng=False, is_repost=False, is_comms=False):
    applicants = job.get("applicants")
    date_posted = job.get("date_posted")
    company_lower = str(job.get("company") or "").lower()
    is_watchlist = any(w in company_lower for w in WATCHLIST_COMPANIES)

    age_hours = None
    if date_posted:
        try:
            now = datetime.now(timezone.utc)
            dp = date_posted
            if hasattr(dp, "tzinfo") and dp.tzinfo is None:
                dp = dp.replace(tzinfo=timezone.utc)
            age_hours = (now - dp).total_seconds() / 3600
        except Exception:
            pass

    haiku_score = analysis.get("fit_score", 0)
    lib_score_val = job.get("_lib_score")
    try:
        n_applicants = int(applicants) if applicants is not None else None
    except (ValueError, TypeError):
        n_applicants = None

    # Use the higher of the two scores for urgency determination
    # Lib score is 0-100, Haiku is 1-10 — normalize lib to 1-10 for urgency
    lib_normalized = int(lib_score_val / 10) if lib_score_val is not None else 0
    urgency_score = max(haiku_score, lib_normalized)
    urgency = determine_urgency(urgency_score, age_hours, n_applicants)
    urg_cfg = URGENCY_CONFIG[urgency]

    # Ping user only for URGENT and HIGH
    if urg_cfg["ping"]:
        mention = f"<@{DISCORD_USER_ID}>" if DISCORD_USER_ID else "@here"
    else:
        mention = ""

    is_hot = not is_repost and age_hours is not None and age_hours <= 1

    if is_watchlist:
        color = "FFD700"
    else:
        color = urg_cfg["color"]

    flags = []
    if urgency in ("URGENT", "HIGH"):
        flags.append(f"{urg_cfg['prefix']} — act now")
    if is_repost:
        flags.append("♻️ REPOST -- timestamp unreliable, likely stale")
    elif is_hot:
        flags.append("🔥 FRESH -- under 1 hour old")
    elif age_hours is not None and age_hours <= 4:
        flags.append(f"🔥 FRESH -- posted {age_hours:.0f}h ago")
    if is_watchlist:
        flags.append("⭐ WATCHLIST COMPANY")
    if is_intern:
        flags.append("🎓 INTERNSHIP -- high conversion company")
    if is_prompt_eng:
        flags.append("🤖 AI/PROMPT ENGINEER ROLE")
    if is_comms:
        flags.append("📣 COMMS/DEVREL ROLE")
    if applicants is not None:
        try:
            n = int(applicants)
            # LinkedIn uses "Be among the first 25 applicants" as a bucket (0-24 actual)
            if n == 25:
                flags.append("👀 <25 applicants")
            else:
                flags.append(f"👀 {n} applicant{'s' if n != 1 else ''}")
        except (ValueError, TypeError):
            pass

    # Handle pandas NaN in posted date
    posted_str = "Unknown"
    if age_hours is not None:
        posted_str = f"{age_hours:.1f}h ago"
    elif date_posted is not None and str(date_posted) not in ("nan", "NaT", "None", ""):
        posted_str = str(date_posted)
    # Dual score display
    haiku_display = analysis.get("fit_score", "?")
    lib_display = f"{int(lib_score_val)}" if lib_score_val is not None else "?"
    score_line = f"Haiku: {haiku_display}/10 | Lib: {lib_display}/100"

    description_preview = str(job.get("description") or "")[:300] + "..."

    embed_description = ("\n".join(flags) + "\n\n" if flags else "") + description_preview

    urgency_label = f"[{urgency}] " if urgency in ("URGENT", "HIGH") else ""
    webhook = DiscordWebhook(
        url=WEBHOOK_URL,
        content=f"{mention} {urgency_label}New job match! {score_line}".strip()
    )

    embed = DiscordEmbed(
        title=f"{job.get('title', 'Unknown Role')} @ {job.get('company', 'Unknown')}",
        url=job.get("job_url", ""),
        description=embed_description,
        color=color
    )

    # Format salary range — try structured fields first, then extract from description
    min_sal = job.get("min_amount")
    max_sal = job.get("max_amount")
    interval = str(job.get("interval", "")).lower()
    salary_str = "N/A"

    if min_sal and max_sal:
        try:
            lo, hi = float(min_sal), float(max_sal)
            if interval == "hourly":
                salary_str = f"${lo:.0f}-${hi:.0f}/hr"
            elif lo >= 1000:
                salary_str = f"${lo/1000:.0f}k-${hi/1000:.0f}k"
            else:
                salary_str = f"${lo:.0f}-${hi:.0f}"
        except (ValueError, TypeError):
            pass
    elif max_sal:
        try:
            hi = float(max_sal)
            salary_str = f"Up to ${hi/1000:.0f}k" if hi >= 1000 else f"Up to ${hi:.0f}"
        except (ValueError, TypeError):
            pass

    # Fallback: extract salary from description text
    if salary_str == "N/A":
        desc = str(job.get("description") or "")
        # Match patterns like $234,650 - $259,350 or $200k - $300k or $200,000-$300,000
        sal_match = re.search(
            r'\$\s*([\d,]+(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[kK]?',
            desc
        )
        if sal_match:
            try:
                lo_str = sal_match.group(1).replace(",", "")
                hi_str = sal_match.group(2).replace(",", "")
                lo = float(lo_str)
                hi = float(hi_str)
                # Handle "k" suffix
                if "k" in sal_match.group(0).lower():
                    if lo < 1000: lo *= 1000
                    if hi < 1000: hi *= 1000
                # Only show if it looks like annual salary (> $50k)
                if hi >= 50000:
                    salary_str = f"~${lo/1000:.0f}k-${hi/1000:.0f}k"
            except (ValueError, TypeError):
                pass

    embed.add_embed_field(name="Company", value=str(job.get("company", "N/A")), inline=True)
    embed.add_embed_field(name="Location", value=str(job.get("location", "N/A")), inline=True)
    embed.add_embed_field(name="Salary", value=salary_str, inline=True)
    embed.add_embed_field(name="Posted", value=posted_str, inline=True)
    applicant_str = "N/A"
    if applicants is not None:
        try:
            n = int(applicants)
            applicant_str = "<25" if n == 25 else str(n)
        except (ValueError, TypeError):
            pass
    embed.add_embed_field(name="Applicants", value=applicant_str, inline=True)
    embed.add_embed_field(name="Source", value=str(job.get("site", "N/A")).capitalize(), inline=True)
    lib_breakdown = job.get("_lib_breakdown", "")
    if lib_breakdown:
        embed.add_embed_field(name="Lib Score", value=f"{lib_display}/100 ({lib_breakdown})", inline=False)
    embed.add_embed_field(name="Why it fits", value=str(analysis.get("reason", "N/A")), inline=False)
    embed.set_footer(text="✅ prepare application  |  📨 mark applied  |  ❌ dismiss")

    webhook.add_embed(embed)
    webhook.execute()


def post_to_job_agent(job, analysis):
    """POST a filtered job to the job-agent web UI ingest endpoint."""
    if not INGEST_API_KEY:
        return
    try:
        # Parse salary from structured fields
        sal_min = None
        sal_max = None
        try:
            if job.get("min_amount"):
                sal_min = int(float(job["min_amount"]))
            if job.get("max_amount"):
                sal_max = int(float(job["max_amount"]))
        except (ValueError, TypeError):
            pass

        # Parse posted date (guard against pandas NaN/NaT)
        posted_at = None
        dp = job.get("date_posted")
        if dp is not None and str(dp) not in ("nan", "NaT", "None", ""):
            try:
                if hasattr(dp, "isoformat"):
                    posted_at = dp.isoformat()
                else:
                    posted_at = str(dp)
            except Exception:
                pass

        payload = {
            "title": str(job.get("title") or ""),
            "company": str(job.get("company") or ""),
            "url": str(job.get("job_url") or ""),
            "description": str(job.get("description") or ""),
            "source": str(job.get("site") or "linkedin"),
            "haiku_score": analysis.get("fit_score"),
            "relevance_explanation": analysis.get("reason"),
            "salary_min": sal_min,
            "salary_max": sal_max,
            "location": str(job.get("location") or "") if str(job.get("location", "")) not in ("nan", "None") else "",
            "posted_at": posted_at,
            "applicant_count": int(job["applicants"]) if job.get("applicants") is not None and str(job.get("applicants")) not in ("nan", "None") else None,
        }
        resp = requests.post(
            INGEST_URL,
            json=payload,
            headers={"x-api-key": INGEST_API_KEY},
            timeout=10,
        )
        if resp.status_code == 201:
            logging.info(f"Ingested to job-agent: {payload['title']} @ {payload['company']}")
        else:
            logging.warning(f"Ingest failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logging.warning(f"post_to_job_agent error: {e}")


# Track title+company combos seen this run to avoid duplicate Claude calls
_seen_this_run = set()


def process_jobs(jobs_df, conn, is_intern=False, is_remote=False, is_prompt_eng=False, is_comms=False):
    alerted = 0
    seen_count = 0
    new_count = 0
    for _, job in jobs_df.iterrows():
        job_dict = job.to_dict()
        job_url = str(job_dict.get("job_url", ""))
        if not job_url:
            continue
        if is_seen(conn, job_url):
            seen_count += 1
            continue
        new_count += 1

        # Dedup same title+company across locations within this run — keep first (local > remote)
        dedup_key = (str(job_dict.get("title") or "").lower(), str(job_dict.get("company") or "").lower())
        if dedup_key in _seen_this_run:
            logging.info(f"Dedup (same role, different location): {job_dict.get('title')} @ {job_dict.get('company')}")
            mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"))
            continue
        _seen_this_run.add(dedup_key)

        passed, reason = quick_filter(job_dict)
        if not passed:
            logging.info(f"Quick filtered: {job_dict.get('title')} @ {job_dict.get('company')} -- {reason}")
            log_outcome(job_url, "quick_filtered", reason=reason)
            mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="quick_filtered")
            continue

        # Deterministic scoring via shared lib (no LLM, no HTTP fetch)
        try:
            title_str = str(job_dict.get("title") or "")
            company_str = str(job_dict.get("company") or "")
            location_str = str(job_dict.get("location") or "")
            if str(location_str) in ("nan", "None"):
                location_str = ""
            salary_hint = ""
            if job_dict.get("min_amount") and job_dict.get("max_amount"):
                try:
                    salary_hint = f"${int(float(job_dict['min_amount']))}-${int(float(job_dict['max_amount']))}"
                except (ValueError, TypeError):
                    pass
            job_id_match = re.search(r'/view/(\d+)', job_url)
            source_id = job_id_match.group(1) if job_id_match else ""
            recency_str = str(job_dict.get("date_posted") or "")
            if recency_str in ("nan", "NaT", "None"):
                recency_str = ""

            jr = JobResult(
                source="linkedin",
                source_id=source_id,
                title=title_str,
                company=company_str,
                location=location_str,
                url=job_url,
                recency=recency_str,
                salary_hint=salary_hint,
                role_type=classify_role(title_str),
            )
            lib_score = lib_quick_score(jr)
            job_dict["_lib_score"] = lib_score
            job_dict["_lib_breakdown"] = jr.score_breakdown
            logging.info(f"Lib score: {lib_score:.0f} for {title_str} @ {company_str} ({jr.score_breakdown})")

            # Low lib scores skip the expensive fetch + Claude steps
            LIB_SCORE_THRESHOLD = 0  # TEMPORARY: disabled for parallel comparison (normally 30)
            if lib_score < LIB_SCORE_THRESHOLD:
                logging.info(f"Lib filtered ({lib_score:.0f} < {LIB_SCORE_THRESHOLD}): {title_str} @ {company_str}")
                log_outcome(job_url, "lib_filtered", score=int(lib_score), reason=jr.score_breakdown)
                mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="lib_filtered", score=int(lib_score))
                continue
        except Exception as e:
            logging.warning(f"Lib scoring failed for {job_dict.get('title')}: {e}")
            lib_score = None  # fall through to Claude

        # Fetch full description, applicant count, and repost flag from page HTML
        full_desc, applicant_count, page_repost = fetch_full_job_details(job_url)
        if full_desc:
            job_dict["description"] = full_desc
        if applicant_count is not None:
            job_dict["applicants"] = applicant_count

        repost = page_repost or detect_repost(job_dict)
        if repost:
            logging.info(f"Repost detected: {job_dict.get('title')} @ {job_dict.get('company')} -- skipping freshness fast-pass")

        # OR filter
        passes, age_hours, applicant_count = passes_or_filter(job_dict, is_repost=repost)
        if not passes:
            logging.info(f"OR filtered ({age_hours:.1f}h old, {applicant_count} applicants): {job_dict.get('title')} @ {job_dict.get('company')}")
            log_outcome(job_url, "freshness_filtered", reason=f"{age_hours:.1f}h old, {applicant_count} applicants")
            mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="freshness_filtered")
            continue

        # Intern gate: only high-conversion companies
        if is_intern:
            company_lower = str(job_dict.get("company") or "").lower()
            if not any(c in company_lower for c in HIGH_CONVERSION_COMPANIES):
                mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"))
                continue

        if is_prompt_eng:
            analysis = claude_prompt_eng_check(job_dict)
        elif is_comms:
            analysis = claude_comms_check(job_dict)
        else:
            analysis = claude_relevance_check(job_dict)

        fit_score = analysis.get("fit_score", 0)
        min_score = 4 if is_intern else (5 if is_remote else 5)
        if not analysis.get("relevant") or fit_score < min_score:
            logging.info(f"Claude filtered: {job_dict.get('title')} @ {job_dict.get('company')} -- {analysis.get('reason')}")
            log_outcome(job_url, "claude_filtered", score=fit_score, reason=analysis.get("reason", ""))
            mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="claude_filtered", score=fit_score)
            continue

        # Late discovery flag: newly seen with high applicant count
        discovery_applicants = job_dict.get("applicants")
        if discovery_applicants is not None:
            try:
                n = int(discovery_applicants)
                if n > 50:
                    logging.warning(f"LATE DISCOVERY ({n} applicants): {job_dict.get('title')} @ {job_dict.get('company')} -- investigate search coverage")
                elif n > 25:
                    logging.warning(f"Late discovery ({n} applicants): {job_dict.get('title')} @ {job_dict.get('company')}")
            except (ValueError, TypeError):
                pass

        send_discord_alert(job_dict, analysis, is_intern=is_intern, is_prompt_eng=is_prompt_eng, is_repost=repost, is_comms=is_comms)
        post_to_job_agent(job_dict, analysis)
        mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="alerted", score=fit_score)
        alerted += 1
        log_outcome(job_url, "alerted", score=fit_score, reason=analysis.get("reason", ""))
        logging.info(f"Alerted: {job_dict.get('title')} @ {job_dict.get('company')} (score {fit_score})")

    logging.info(f"  Batch stats: {seen_count} seen, {new_count} new, {alerted} alerted")
    return alerted


import csv

OVERLAP_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "query_overlap.csv")


def log_query_results(search_term, location, jobs_df, run_ts):
    """Log each job_url seen per query to CSV for overlap analysis, with position."""
    os.makedirs(os.path.dirname(OVERLAP_LOG), exist_ok=True)
    file_exists = os.path.exists(OVERLAP_LOG)
    with open(OVERLAP_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "search_term", "location", "position", "job_url", "title", "company"])
        for position, (_, job) in enumerate(jobs_df.iterrows(), 1):
            writer.writerow([
                run_ts,
                search_term,
                location,
                position,
                str(job.get("job_url", "")),
                str(job.get("title", "")),
                str(job.get("company", "")),
            ])


# Outcome tracking: populated during process_jobs, keyed by job_url
_job_outcomes = {}  # url -> {"outcome": str, "score": int|None, "reason": str}

OUTCOME_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "job_outcomes.csv")


def _update_applicant_counts(conn):
    """Re-fetch applicant counts for high-rated, low-applicant seen jobs."""
    MAX_UPDATES = 10  # limit HTTP requests per run
    rows = conn.execute(
        """SELECT job_url, title, company, score FROM seen_jobs
           WHERE outcome = 'alerted' AND score >= 7
           ORDER BY score DESC LIMIT ?""",
        (MAX_UPDATES * 3,)  # fetch more than we'll update, to filter
    ).fetchall()

    updated = 0
    for url, title, company, score in rows:
        if updated >= MAX_UPDATES:
            break
        # Only re-check from cache (no new HTTP fetch — use cache TTL)
        cached_html, _, _ = _cache_get(url)
        if not cached_html:
            continue
        _, new_count, _ = _parse_job_page(cached_html)
        if new_count is not None:
            conn.execute(
                "UPDATE seen_jobs SET score = ? WHERE job_url = ?",
                (score, url)  # keep score, just logging
            )
            updated += 1

    if updated:
        conn.commit()
        logging.info(f"Updated applicant counts for {updated} high-rated jobs")


def log_outcome(job_url, outcome, score=None, reason=""):
    """Record outcome for a job URL (for later correlation with search terms)."""
    _job_outcomes[job_url] = {"outcome": outcome, "score": score, "reason": reason}


def write_outcome_log(run_ts):
    """Write outcomes to CSV, correlatable with query_overlap.csv by job_url + timestamp."""
    os.makedirs(os.path.dirname(OUTCOME_LOG), exist_ok=True)
    file_exists = os.path.exists(OUTCOME_LOG)
    with open(OUTCOME_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "job_url", "outcome", "score", "reason"])
        for url, data in _job_outcomes.items():
            writer.writerow([run_ts, url, data["outcome"], data["score"] or "", data["reason"]])


def run():
    logging.info("=== Scraper run started ===")
    conn = init_db()
    total_alerted = 0
    run_ts = datetime.now(timezone.utc).isoformat()

    # Determine hours_old based on time of day
    # During frequent runs (daytime), use short window to maximize fresh results
    # During infrequent runs (overnight), use longer window as safety net
    from zoneinfo import ZoneInfo
    pt_hour = datetime.now(ZoneInfo("America/Los_Angeles")).hour
    if 7 <= pt_hour < 19:
        search_hours = 4   # daytime: tight window, most results will be fresh
    else:
        search_hours = 24  # overnight: wider safety net

    # Bay Area searches — single radius from Orinda covers SF, Oakland, Berkeley, Peninsula
    for search_term in SEARCH_TERMS:
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=search_term,
                location="Orinda, CA",
                distance=40,
                results_wanted=100,
                hours_old=search_hours,
                job_type="fulltime",
            )
            if jobs_df is not None and not jobs_df.empty:
                logging.info(f"'{search_term}' (40mi from Orinda, {search_hours}h): {len(jobs_df)} results")
                log_query_results(search_term, "Orinda, CA (40mi)", jobs_df, run_ts)
                total_alerted += process_jobs(jobs_df, conn)
        except Exception as e:
            logging.error(f"Error scraping '{search_term}': {e}")
        time.sleep(2)

    # Remote searches — consolidated with OR
    REMOTE_SEARCH_TERMS = [
        '"Engineering Manager" OR "Senior Engineering Manager" OR "Director of Engineering"',
    ]
    for search_term in REMOTE_SEARCH_TERMS:
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=search_term,
                location="United States",
                results_wanted=100,
                hours_old=search_hours,
                job_type="fulltime",
                is_remote=True,
            )
            if jobs_df is not None and not jobs_df.empty:
                logging.info(f"'{search_term}' (remote, {search_hours}h): {len(jobs_df)} results")
                log_query_results(search_term, "United States (remote)", jobs_df, run_ts)
                total_alerted += process_jobs(jobs_df, conn, is_remote=True)
        except Exception as e:
            logging.error(f"Error scraping remote '{search_term}': {e}")
        time.sleep(2)

    # Domain-targeted searches — additional, not replacement
    # Catches niche roles in target domains with wider title range
    DOMAIN_SEARCH_INTERVAL_HOURS = 12
    deep_search_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", ".last_deep_search")
    run_deep = True
    try:
        with open(deep_search_file) as f:
            last_deep = datetime.fromisoformat(f.read().strip())
        if (datetime.now(timezone.utc) - last_deep).total_seconds() < DOMAIN_SEARCH_INTERVAL_HOURS * 3600:
            run_deep = False
    except (FileNotFoundError, ValueError):
        pass

    if run_deep:
        logging.info("Running domain-targeted search (72h window)")
        for search_term in DOMAIN_SEARCH_TERMS:
            try:
                jobs_df = scrape_jobs(
                    site_name=["linkedin"],
                    search_term=search_term,
                    location="Orinda, CA",
                    distance=40,
                    results_wanted=50,
                    hours_old=72,
                    job_type="fulltime",
                )
                if jobs_df is not None and not jobs_df.empty:
                    logging.info(f"'{search_term}' (domain, 72h): {len(jobs_df)} results")
                    log_query_results(search_term, "Orinda, CA (domain)", jobs_df, run_ts)
                    total_alerted += process_jobs(jobs_df, conn)
            except Exception as e:
                logging.error(f"Error in domain search '{search_term}': {e}")
            time.sleep(2)
        with open(deep_search_file, "w") as f:
            f.write(datetime.now(timezone.utc).isoformat())

    # Update applicant counts for high-rated seen jobs
    try:
        _update_applicant_counts(conn)
    except Exception as e:
        logging.warning(f"Applicant count update failed: {e}")

    conn.close()
    logging.info(f"=== Scraper run complete. Jobs alerted: {total_alerted} ===")

    # Write outcome log and print overlap summary
    try:
        write_outcome_log(run_ts)
        _print_overlap_summary(run_ts)
    except Exception as e:
        logging.warning(f"Post-run analysis failed: {e}")

    # Clear run-level state
    _seen_this_run.clear()
    _job_outcomes.clear()


def _print_overlap_summary(run_ts):
    """Analyze query overlap from the CSV for the current run, enriched with scores."""
    with open(OVERLAP_LOG, "r") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["timestamp"] == run_ts]

    # Map: job_url -> set of search terms that found it
    url_to_terms = {}
    url_to_info = {}  # url -> {title, company}
    for r in rows:
        url = r["job_url"]
        if url not in url_to_terms:
            url_to_terms[url] = set()
        url_to_terms[url].add(r["search_term"])
        url_to_info[url] = {"title": r.get("title", ""), "company": r.get("company", "")}

    # Get scores from this run's outcomes + historical seen_jobs
    url_scores = {}
    for url in url_to_terms:
        if url in _job_outcomes:
            url_scores[url] = _job_outcomes[url].get("score")
        else:
            # Look up from seen_jobs DB
            conn = sqlite3.connect(DB_PATH)
            outcome, score = get_seen_score(conn, url)
            conn.close()
            url_scores[url] = score

    total_urls = len(url_to_terms)
    unique_to_one = sum(1 for terms in url_to_terms.values() if len(terms) == 1)
    found_by_multiple = sum(1 for terms in url_to_terms.values() if len(terms) > 1)

    # Per-term stats with score breakdown
    term_counts = {}
    term_unique = {}
    term_high_score = {}  # terms that found score >= 7
    term_alerted = {}     # terms that found alerted jobs
    for url, terms in url_to_terms.items():
        score = url_scores.get(url)
        for t in terms:
            term_counts[t] = term_counts.get(t, 0) + 1
            if len(terms) == 1:
                term_unique[t] = term_unique.get(t, 0) + 1
            if score is not None and score >= 7:
                term_high_score[t] = term_high_score.get(t, 0) + 1
            outcome = _job_outcomes.get(url, {}).get("outcome", "")
            if outcome == "alerted":
                term_alerted[t] = term_alerted.get(t, 0) + 1

    logging.info(f"=== Query overlap: {total_urls} unique URLs, {found_by_multiple} found by 2+ queries, {unique_to_one} unique to one query ===")
    logging.info(f"  {'Search term':<40} {'Total':>6} {'Unique':>7} {'Score7+':>8} {'Alerted':>8}")
    for term in sorted(term_counts, key=lambda t: term_counts[t], reverse=True):
        uniq = term_unique.get(term, 0)
        high = term_high_score.get(term, 0)
        alert = term_alerted.get(term, 0)
        logging.info(f"  {term:<40} {term_counts[term]:>6} {uniq:>7} {high:>8} {alert:>8}")

    # List high-score jobs unique to one query (these are the ones that justify specialized searches)
    exclusive_high = []
    for url, terms in url_to_terms.items():
        score = url_scores.get(url)
        if len(terms) == 1 and score is not None and score >= 7:
            info = url_to_info.get(url, {})
            exclusive_high.append((list(terms)[0], score, info.get("title", ""), info.get("company", "")))
    if exclusive_high:
        logging.info(f"  --- High-score jobs (7+) found by only one query ---")
        for term, score, title, company in sorted(exclusive_high, key=lambda x: -x[1]):
            logging.info(f"    [{score}/10] '{term}' -> {title} @ {company}")


if __name__ == "__main__":
    run()
