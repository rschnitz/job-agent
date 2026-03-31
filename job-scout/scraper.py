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

# Search terms -- kept focused on EM/Director roles
SEARCH_TERMS = [
    "Engineering Manager",
    "Senior Engineering Manager",
    "Director of Engineering",
    "Head of Engineering",
    "VP Engineering",
    "Engineering Manager fintech",
    "Engineering Manager platform",
    # "Principal Engineer" covers "Principal Software Engineer" on LinkedIn
    "Principal Engineer",
    # "Staff Engineer" covers "Staff Software Engineer" and "Senior Staff" variants
    "Staff Engineer",
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


def fetch_full_job_details(job_url):
    """Fetch full description and applicant count from the actual job page."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(job_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

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

        # "Reposted" appears in the raw HTML as a label even when plain text strips context
        page_repost = bool(re.search(r"reposted", resp.text, re.IGNORECASE))

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


def send_discord_alert(job, analysis, is_intern=False, is_prompt_eng=False, is_repost=False, is_comms=False):
    mention = f"<@{DISCORD_USER_ID}>" if DISCORD_USER_ID else "@here"

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

    is_hot = not is_repost and age_hours is not None and age_hours <= 1

    if is_watchlist:
        color = "FFD700"
    elif is_hot:
        color = "00FF7F"
    else:
        color = "03b2f8"

    flags = []
    if is_repost:
        flags.append("♻️ REPOST -- timestamp unreliable, likely stale")
    elif is_hot:
        flags.append("🔥 FRESH -- under 1 hour old")
    elif age_hours is not None and age_hours <= 2:
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
            flags.append(f"👀 {n} applicant{'s' if n != 1 else ''}")
        except (ValueError, TypeError):
            pass

    posted_str = f"{age_hours:.1f}h ago" if age_hours is not None else str(date_posted) if date_posted else "Unknown"
    fit_score = analysis.get("fit_score", "?")
    description_preview = str(job.get("description") or "")[:300] + "..."

    embed_description = ("\n".join(flags) + "\n\n" if flags else "") + description_preview

    webhook = DiscordWebhook(
        url=WEBHOOK_URL,
        content=f"{mention} New job match! Fit score: {fit_score}/10"
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
    embed.add_embed_field(name="Applicants", value=str(applicants) if applicants is not None else "N/A", inline=True)
    embed.add_embed_field(name="Source", value=str(job.get("site", "N/A")).capitalize(), inline=True)
    embed.add_embed_field(name="Why it fits", value=str(analysis.get("reason", "N/A")), inline=False)
    embed.set_footer(text="✅ tailor resume  |  📨 mark applied  |  ❌ dismiss")

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

        # Parse posted date
        posted_at = None
        dp = job.get("date_posted")
        if dp:
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
            "fit_score": analysis.get("fit_score"),
            "relevance_score": analysis.get("fit_score"),  # currently same; will diverge with /evaluate
            "relevance_explanation": analysis.get("reason"),
            "salary_min": sal_min,
            "salary_max": sal_max,
            "location": str(job.get("location") or ""),
            "posted_at": posted_at,
            "applicant_count": job.get("applicants"),
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
    for _, job in jobs_df.iterrows():
        job_dict = job.to_dict()
        job_url = str(job_dict.get("job_url", ""))
        if not job_url or is_seen(conn, job_url):
            continue

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

        send_discord_alert(job_dict, analysis, is_intern=is_intern, is_prompt_eng=is_prompt_eng, is_repost=repost, is_comms=is_comms)
        post_to_job_agent(job_dict, analysis)
        mark_seen(conn, job_url, job_dict.get("title"), job_dict.get("company"), outcome="alerted", score=fit_score)
        alerted += 1
        log_outcome(job_url, "alerted", score=fit_score, reason=analysis.get("reason", ""))
        logging.info(f"Alerted: {job_dict.get('title')} @ {job_dict.get('company')} (score {fit_score})")

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

    # Bay Area searches — single radius from Orinda covers SF, Oakland, Berkeley, Peninsula
    # Request 100 results to capture the long tail and measure value by position
    for search_term in SEARCH_TERMS:
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=search_term,
                location="Orinda, CA",
                distance=40,
                results_wanted=100,
                hours_old=24,
                job_type="fulltime",
            )
            if jobs_df is not None and not jobs_df.empty:
                logging.info(f"'{search_term}' (40mi from Orinda): {len(jobs_df)} results")
                log_query_results(search_term, "Orinda, CA (40mi)", jobs_df, run_ts)
                total_alerted += process_jobs(jobs_df, conn)
        except Exception as e:
            logging.error(f"Error scraping '{search_term}': {e}")
        time.sleep(2)

    # Remote searches
    for search_term in ["Engineering Manager remote", "Senior Engineering Manager remote", "Director of Engineering remote"]:
        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=search_term,
                location="United States",
                results_wanted=100,
                hours_old=24,
                job_type="fulltime",
                is_remote=True,
            )
            if jobs_df is not None and not jobs_df.empty:
                logging.info(f"'{search_term}' (remote): {len(jobs_df)} results")
                log_query_results(search_term, "United States (remote)", jobs_df, run_ts)
                total_alerted += process_jobs(jobs_df, conn, is_remote=True)
        except Exception as e:
            logging.error(f"Error scraping remote '{search_term}': {e}")
        time.sleep(2)

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
