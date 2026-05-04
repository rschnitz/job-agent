#!/usr/bin/env python3
"""
Refresh applicant counts, detect NLAA, and backfill missing fields for active jobs.

Run standalone (cron/launchctl) or import and call run() from the scraper.

Usage:
    python3 refresh_postings.py [--dry-run] [--max N] [--force]

    --dry-run   Print proposed changes without writing to Supabase
    --max N     Max jobs to refresh per run (default: 30)
    --force     Ignore last_refreshed_at; refresh all eligible jobs
"""

import os
import re
import sys
import json
import time
import random
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ── Env loading ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_env_local = os.path.join(_here, "..", ".env.local")
_env_file  = os.path.join(_here, ".env")
if os.path.exists(_env_local):
    load_dotenv(_env_local)
elif os.path.exists(_env_file):
    load_dotenv(_env_file)

SURL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
KEY  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_PATH = os.path.join(_here, "logs", "refresh_postings.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %I:%M:%S %p",
)

# ── Config ─────────────────────────────────────────────────────────────────────
DEFAULT_MAX_REFRESHES = 30
REQUEST_TIMEOUT = 15
REQUEST_DELAY_RANGE = (1.5, 3.5)  # seconds between fetches

# Refresh intervals (hours) — applicant count beats interest score
INTERVAL_FEW_APPLICANTS_1  = 1   # < 25 applicants: very competitive, check often
INTERVAL_FEW_APPLICANTS_2  = 2   # < 50 applicants
INTERVAL_HOT               = 6   # high interest/fit score
INTERVAL_WARM              = 12  # mid-tier
INTERVAL_COLD              = 24  # low/unscored

# NLAA detection patterns (LinkedIn + common ATS)
NLAA_PATTERNS = [
    r"no longer accepting applications",
    r"this job is no longer",
    r"job has expired",
    r"position has been filled",
    r"application deadline has passed",
    r"posting has been removed",
    r"this job posting has been",
    r"job listing is no longer",
    r"this listing has expired",
    r"this position has been filled",
    r"applications are no longer being accepted",
]


# ── Supabase helpers ───────────────────────────────────────────────────────────

def supa_get(path: str) -> list:
    req = urllib.request.Request(
        f"{SURL}/rest/v1/{path}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def supa_patch(path: str, payload: dict):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SURL}/rest/v1/{path}",
        data=data,
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"},
        method="PATCH",
    )
    urllib.request.urlopen(req)


# ── Priority / scheduling ──────────────────────────────────────────────────────

def refresh_interval_hours(job: dict) -> int:
    """
    Return how often this job should be re-checked (hours).

    Priority order:
      1. Applicant count (competitive signal, actionable regardless of score)
      2. Interest/fit score
      3. Default cold tier
    """
    count    = job.get("applicant_count")
    interest = job.get("ras_interest")
    fit      = job.get("ras_fit")

    if count is not None and count < 25:
        return INTERVAL_FEW_APPLICANTS_1
    if count is not None and count < 50:
        return INTERVAL_FEW_APPLICANTS_2
    if (interest is not None and interest >= 85) or (fit is not None and fit >= 8):
        return INTERVAL_HOT
    if (interest is not None and interest >= 70) or (fit is not None and fit >= 7):
        return INTERVAL_WARM
    return INTERVAL_COLD


def is_due(job: dict, force: bool = False) -> bool:
    if force:
        return True
    last = job.get("last_refreshed_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt > timedelta(hours=refresh_interval_hours(job))
    except (ValueError, TypeError):
        return True


# ── Page fetching & parsing ────────────────────────────────────────────────────

def fetch_job_page(url: str) -> tuple[str | None, int]:
    """Fetch job posting page fresh (no cache). Returns (html, status_code)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return resp.text, resp.status_code
    except Exception as e:
        logging.warning(f"Fetch error for {url}: {e}")
        return None, 0


def detect_nlaa(html: str, status_code: int, original_url: str) -> bool:
    if status_code == 404:
        return True
    if not html or status_code == 0:
        return False  # network error — don't close on ambiguous failure

    text_lower = html.lower()
    for pattern in NLAA_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    # LinkedIn-specific: no job title element on a short 200 page = expired redirect
    if "linkedin.com/jobs/view/" in original_url:
        soup = BeautifulSoup(html, "html.parser")
        has_title = bool(
            soup.select_one(".topcard__title") or
            soup.select_one("h1.top-card-layout__title") or
            soup.select_one("[data-testid='job-title']") or
            soup.select_one(".job-details-jobs-unified-top-card__job-title")
        )
        if not has_title and len(html) < 20000:
            return True

    return False


def parse_applicant_count(html: str) -> int | None:
    if not html:
        return None
    page_text = BeautifulSoup(html, "html.parser").get_text()
    for pattern in [
        r"(\d[\d,]+)\s+applicants?",
        r"Over\s+(\d[\d,]+)\s+applicants?",
        r"Be among the first\s+(\d+)",
        r"(\d+)\s+people\s+clicked\s+apply",
        r"(\d+)\s+clicked\s+apply",
    ]:
        m = re.search(pattern, page_text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def parse_description(html: str) -> str | None:
    """Extract job description text from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        ".show-more-less-html__markup",
        ".description__text",
        ".job-description",
        "[data-testid='job-description']",
        ".jobsearch-jobDescriptionText",
        ".jobs-description__content",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text
    return None


def parse_salary(html: str) -> tuple[int | None, int | None]:
    """Extract salary range from page HTML. Returns (min, max) or (None, None)."""
    if not html:
        return None, None

    # Try structured LinkedIn salary elements first
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        ".compensation__salary",
        "[data-testid='salary-range']",
        ".job-details-jobs-unified-top-card__job-insight--highlight",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text()
            lo, hi = _salary_from_text(text)
            if lo and hi:
                return lo, hi

    # Fall back to regex over full page text
    page_text = soup.get_text()
    return _salary_from_text(page_text)


def _salary_from_text(text: str) -> tuple[int | None, int | None]:
    m = re.search(
        r'\$\s*([\d,]+(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*\$?\s*([\d,]+(?:\.\d+)?)\s*[kK]?',
        text,
    )
    if not m:
        return None, None
    try:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        if "k" in m.group(0).lower():
            if lo < 1000: lo *= 1000
            if hi < 1000: hi *= 1000
        if hi >= 50000:  # sanity check: must look like annual salary
            return int(lo), int(hi)
    except (ValueError, TypeError):
        pass
    return None, None


# ── Main run ───────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, max_refreshes: int = DEFAULT_MAX_REFRESHES, force: bool = False):
    if not SURL or not KEY:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set", file=sys.stderr)
        sys.exit(1)

    logging.info(f"=== refresh_postings started (dry_run={dry_run}, max={max_refreshes}, force={force}) ===")

    jobs = supa_get(
        "jobs?select=id,ras_id,title,company,url,stage,outcome,"
        "ras_interest,ras_fit,last_refreshed_at,applicant_count,"
        "salary_min,salary_max,description"
        "&outcome=not.in.(closed,accepted,declined,withdrawn)"
        "&url=not.is.null"
        "&limit=500"
    )
    logging.info(f"Fetched {len(jobs)} candidate jobs from Supabase")

    due = [j for j in jobs if j.get("url") and is_due(j, force=force)]
    # Sort: most urgent (shortest interval) first
    due.sort(key=lambda j: refresh_interval_hours(j))
    logging.info(f"{len(due)} jobs due for refresh (capped at {max_refreshes})")
    due = due[:max_refreshes]

    stats = {"nlaa": 0, "count_updated": 0, "backfilled": 0, "unchanged": 0, "error": 0}

    for job in due:
        url     = job["url"]
        jid     = job.get("ras_id") or job["id"][:8]
        company = job.get("company", "?")

        html, status = fetch_job_page(url)
        now_iso = datetime.now(timezone.utc).isoformat()

        nlaa      = detect_nlaa(html, status, url)
        new_count = parse_applicant_count(html) if html else None

        patch: dict = {"last_refreshed_at": now_iso}
        changes: list[str] = []

        if nlaa:
            patch["outcome"] = "closed"
            changes.append("outcome→closed (NLAA)")
            stats["nlaa"] += 1
        else:
            # Applicant count
            if new_count is not None:
                old_count = job.get("applicant_count")
                if new_count != old_count:
                    patch["applicant_count"] = new_count
                    changes.append(f"applicants {old_count}→{new_count}")
                    stats["count_updated"] += 1

            # Backfill salary if missing
            if html and job.get("salary_min") is None and job.get("salary_max") is None:
                sal_min, sal_max = parse_salary(html)
                if sal_min and sal_max:
                    patch["salary_min"] = sal_min
                    patch["salary_max"] = sal_max
                    changes.append(f"salary ${sal_min//1000}k-${sal_max//1000}k")
                    stats["backfilled"] += 1

            # Backfill description if missing
            if html and not job.get("description"):
                desc = parse_description(html)
                if desc:
                    patch["description"] = desc
                    changes.append(f"description ({len(desc)} chars)")
                    stats["backfilled"] += 1

            if not changes:
                stats["unchanged"] += 1

        change_str = ", ".join(changes) if changes else "no changes"
        logging.info(f"  {jid:8s} {company[:20]:20s} [{status}] {change_str}")

        if not dry_run:
            try:
                supa_patch(f"jobs?id=eq.{job['id']}", patch)
            except Exception as e:
                logging.warning(f"  PATCH failed for {jid}: {e}")
                stats["error"] += 1
        elif changes:
            print(f"  DRY RUN  {jid:8s}  {job.get('title','?')[:30]:30s} @ {company[:20]:20s}  {change_str}")

        time.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    logging.info(
        f"=== refresh_postings done: {stats['nlaa']} NLAA, "
        f"{stats['count_updated']} count updates, "
        f"{stats['backfilled']} backfills, "
        f"{stats['unchanged']} unchanged, "
        f"{stats['error']} errors ==="
    )
    if dry_run:
        print(
            f"\nDry run: {stats['nlaa']} NLAA, {stats['count_updated']} count updates, "
            f"{stats['backfilled']} backfills, {stats['unchanged']} unchanged"
        )

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--max",     type=int, default=DEFAULT_MAX_REFRESHES, metavar="N")
    parser.add_argument("--force",   action="store_true", help="Ignore refresh schedule; check all")
    args = parser.parse_args()

    run(dry_run=args.dry_run, max_refreshes=args.max, force=args.force)
