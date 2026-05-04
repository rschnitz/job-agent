#!/usr/bin/env python3
"""
Refresh applicant counts and detect NLAA for active jobs in Supabase.

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
# Load from job-agent .env.local (parent dir), then local .env as fallback
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

# Refresh intervals by priority tier (hours)
INTERVAL_HOT    = 6   # in-pipeline or top-scored
INTERVAL_WARM   = 12  # mid-tier interest
INTERVAL_COLD   = 24  # low-interest or unscored

# NLAA detection: any of these in page text → outcome = closed
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

ACTIVE_OUTCOMES = {"active", "ghosted"}
ACTIVE_STAGES   = {"applied", "acked", "screened", "interviewed", "offered"}


# ── Supabase helpers ───────────────────────────────────────────────────────────

def supa_get(path):
    req = urllib.request.Request(
        f"{SURL}/rest/v1/{path}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def supa_patch(path, payload):
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
    """Return how often this job should be re-checked (hours)."""
    stage    = job.get("stage") or "new"
    interest = job.get("ras_interest")
    fit      = job.get("ras_fit")

    if stage in ACTIVE_STAGES:
        return INTERVAL_HOT
    if (interest is not None and interest >= 85) or (fit is not None and fit >= 8):
        return INTERVAL_HOT
    if (interest is not None and interest >= 70) or (fit is not None and fit >= 7):
        return INTERVAL_WARM
    return INTERVAL_COLD


def is_due(job: dict, force: bool = False) -> bool:
    """Return True if the job hasn't been refreshed recently enough."""
    if force:
        return True
    last = job.get("last_refreshed_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        interval = refresh_interval_hours(job)
        return datetime.now(timezone.utc) - last_dt > timedelta(hours=interval)
    except (ValueError, TypeError):
        return True


# ── Page fetching & parsing ────────────────────────────────────────────────────

def fetch_job_page(url: str) -> tuple[str | None, int]:
    """Fetch job posting page. Returns (html, status_code). html=None on hard error."""
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
    """Return True if the posting is no longer accepting applications."""
    if status_code == 404:
        return True
    if status_code == 0 or html is None:
        return False  # network error; don't close on ambiguous failure

    text_lower = html.lower()
    for pattern in NLAA_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    # LinkedIn-specific: redirect to job search when posting is gone
    if "linkedin.com/jobs/view/" in original_url:
        # LinkedIn's NLAA page has very short body or missing job title area
        soup = BeautifulSoup(html, "html.parser")
        has_job_title = bool(
            soup.select_one(".topcard__title") or
            soup.select_one("h1.top-card-layout__title") or
            soup.select_one("[data-testid='job-title']") or
            soup.select_one(".job-details-jobs-unified-top-card__job-title")
        )
        if not has_job_title and status_code == 200 and len(html) < 20000:
            return True

    return False


def parse_applicant_count(html: str) -> int | None:
    """Extract applicant count from page HTML."""
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


# ── Main run ───────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, max_refreshes: int = DEFAULT_MAX_REFRESHES, force: bool = False):
    if not SURL or not KEY:
        print("ERROR: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set", file=sys.stderr)
        sys.exit(1)

    logging.info(f"=== refresh_postings started (dry_run={dry_run}, max={max_refreshes}, force={force}) ===")

    # Fetch all jobs that could still be active
    jobs = supa_get(
        "jobs?select=id,ras_id,title,company,url,stage,outcome,"
        "ras_interest,ras_fit,last_refreshed_at,applicant_count"
        "&outcome=not.in.(closed,accepted,declined,withdrawn)"
        "&url=not.is.null"
        "&limit=500"
    )
    logging.info(f"Fetched {len(jobs)} candidate jobs from Supabase")

    # Filter to jobs that are due for refresh, sorted by priority (hottest first)
    due = [j for j in jobs if j.get("url") and is_due(j, force=force)]
    due.sort(key=lambda j: refresh_interval_hours(j))  # hot (6h) before cold (24h)

    logging.info(f"{len(due)} jobs due for refresh (capped at {max_refreshes})")
    due = due[:max_refreshes]

    stats = {"nlaa": 0, "count_updated": 0, "unchanged": 0, "error": 0}

    for job in due:
        url   = job["url"]
        jid   = job.get("ras_id") or job["id"][:8]
        title = job.get("title", "?")
        company = job.get("company", "?")

        html, status = fetch_job_page(url)
        now_iso = datetime.now(timezone.utc).isoformat()

        nlaa = detect_nlaa(html, status, url)
        new_count = parse_applicant_count(html) if html else None

        patch: dict = {"last_refreshed_at": now_iso}
        changes = []

        if nlaa:
            patch["outcome"] = "closed"
            changes.append("outcome→closed (NLAA)")
            stats["nlaa"] += 1
        elif new_count is not None:
            old_count = job.get("applicant_count")
            if new_count != old_count:
                patch["applicant_count"] = new_count
                changes.append(f"applicants {old_count}→{new_count}")
                stats["count_updated"] += 1
            else:
                stats["unchanged"] += 1
        else:
            stats["unchanged"] += 1

        change_str = ", ".join(changes) if changes else "no changes"
        logging.info(f"  {jid:8s} {company[:20]:20s} [{status}] {change_str}")

        if not dry_run and (nlaa or new_count is not None):
            try:
                supa_patch(f"jobs?id=eq.{job['id']}", patch)
            except Exception as e:
                logging.warning(f"  PATCH failed for {jid}: {e}")
                stats["error"] += 1
        elif dry_run and changes:
            print(f"  DRY RUN  {jid:8s}  {title[:30]:30s} @ {company[:20]:20s}  {change_str}")

        time.sleep(random.uniform(*REQUEST_DELAY_RANGE))

    logging.info(
        f"=== refresh_postings done: {stats['nlaa']} NLAA, "
        f"{stats['count_updated']} count updates, "
        f"{stats['unchanged']} unchanged, "
        f"{stats['error']} errors ==="
    )
    if dry_run:
        print(f"\nDry run: {stats['nlaa']} NLAA, {stats['count_updated']} count updates, "
              f"{stats['unchanged']} unchanged")

    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--max",     type=int, default=DEFAULT_MAX_REFRESHES, metavar="N")
    parser.add_argument("--force",   action="store_true", help="Ignore refresh schedule; check all")
    args = parser.parse_args()

    run(dry_run=args.dry_run, max_refreshes=args.max, force=args.force)
