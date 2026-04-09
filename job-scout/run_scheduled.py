#!/usr/bin/env python3
"""
Scheduled scraper runner. Called every 15 min by launchctl.
Decides whether to actually run based on time since last run
and a target interval that varies by time of day.

Schedule (target interval in minutes by hour boundary):
  midnight-2am: 90 min    2am-6am: 120 min
  6am-7am: 60 min         7am-7pm: 15 min
  7pm-midnight: 60 min
"""

import os
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_RUN_FILE = os.path.join(SCRIPT_DIR, "logs", ".last_run")

# Hour (PT) -> target interval (minutes) for hours >= this key
# Read as: "from this hour onward, use this interval (until next key)"
SCHEDULE = {0: 90, 2: 120, 6: 60, 7: 15, 19: 60}


def target_interval_minutes() -> int:
    """Return the target scrape interval for the current time of day."""
    PT = ZoneInfo("America/Los_Angeles")
    hour = datetime.now(PT).hour
    keys = sorted(SCHEDULE)
    i = bisect_right(keys, hour) - 1
    return SCHEDULE[keys[max(i, 0)]]


def minutes_since_last_run() -> float:
    """Minutes since the last successful scraper run."""
    try:
        with open(LAST_RUN_FILE) as f:
            last = datetime.fromisoformat(f.read().strip())
        return (datetime.now(timezone.utc) - last).total_seconds() / 60
    except (FileNotFoundError, ValueError):
        return float("inf")  # never run -> always run


def record_run():
    """Record the current time as the last run."""
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())


def skip_scrape() -> bool:
    """Return True if not enough time has passed since the last run.

    Future: dynamically adjust target_interval based on recent run stats
    (jobs found per run, avg applicant count at discovery).
    Stats available in logs/job_outcomes.csv and seen_jobs.db.
    """
    return minutes_since_last_run() < target_interval_minutes()


EVAL_THRESHOLD = 7  # Haiku score at which to auto-request RAS evaluation
INBOX_SEND = os.path.expanduser("~/.claude/tools/inbox-send.py")
OUTBOX_DIR = os.path.join(SCRIPT_DIR, "..", ".claude", "inbox", "outbox")
LAST_EVAL_REQUEST_FILE = os.path.join(SCRIPT_DIR, "logs", ".last_eval_request")


def request_ras_evaluation():
    """If any jobs scored >= EVAL_THRESHOLD and lack a fit_explanation,
    send an inbox message to RAS requesting evaluation.
    Deduped: won't send more than once per 4 hours."""
    import json
    import urllib.request

    # Dedup: don't spam RAS
    try:
        with open(LAST_EVAL_REQUEST_FILE) as f:
            last = datetime.fromisoformat(f.read().strip())
        if (datetime.now(timezone.utc) - last).total_seconds() < 4 * 3600:
            return  # sent recently, skip
    except (FileNotFoundError, ValueError):
        pass

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        # Load from .env.local in the project root
        env_path = os.path.join(SCRIPT_DIR, "..", ".env.local")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k == "NEXT_PUBLIC_SUPABASE_URL":
                            supabase_url = v
                        elif k == "SUPABASE_SERVICE_ROLE_KEY":
                            supabase_key = v
    if not supabase_url or not supabase_key:
        return

    # Find high-scoring jobs without RAS evaluation
    req = urllib.request.Request(
        f"{supabase_url}/rest/v1/jobs?fit_explanation=is.null&status=neq.rejected&select=id,url,title,company,fit_score&order=fit_score.desc",
        headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
    )
    try:
        jobs = json.loads(urllib.request.urlopen(req).read())
    except Exception:
        return

    needs_eval = [j for j in jobs if (j.get("fit_score") or 0) >= EVAL_THRESHOLD]
    if not needs_eval:
        return

    # Write inbox message
    os.makedirs(OUTBOX_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    msg_file = os.path.join(OUTBOX_DIR, f"{ts}-auto-eval-request.md")

    job_lines = "\n".join(
        f"  [{j.get('fit_score', '?')}] {j['title']} @ {j['company']}  {j.get('url', '')}"
        for j in needs_eval
    )

    msg = f"""---
from: job-agent (~/src/job-agent)
to: RAS (~/Dropbox/RAS)
date: {ts}
expires: {(datetime.now(timezone.utc) + __import__('datetime').timedelta(days=7)).strftime("%Y-%m-%d")}
subject: Auto — {len(needs_eval)} high-scoring jobs need RAS evaluation
---

## Automated evaluation request

{len(needs_eval)} jobs scoring {EVAL_THRESHOLD}+ (Haiku) lack RAS-calibrated fit scores.
Listed below in priority order (8+ first, then 7s). Process up to 15 per session, starting from the top.

Posting cache at `~/.cache/job-search/postings/{{job_id}}/page.html`.
Write results to Supabase (match by URL). Load env from `~/src/job-agent/.env.local`.

```
{job_lines}
```
"""
    with open(msg_file, "w") as f:
        f.write(msg)

    # Send via inbox tool
    import subprocess
    try:
        result = subprocess.run(
            ["uv", "run", INBOX_SEND, msg_file, "ras"],
            capture_output=True, timeout=15
        )
        if result.returncode == 0:
            with open(LAST_EVAL_REQUEST_FILE, "w") as f:
                f.write(datetime.now(timezone.utc).isoformat())
            import logging
            logging.info(f"Auto-requested RAS evaluation for {len(needs_eval)} jobs")
    except Exception:
        pass  # best-effort; message stays in outbox for manual send


def update_eval_queue_cache():
    """Update the eval queue count cache for the status line."""
    import json
    import urllib.request

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        env_path = os.path.join(SCRIPT_DIR, "..", ".env.local")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        if k == "NEXT_PUBLIC_SUPABASE_URL":
                            supabase_url = v
                        elif k == "SUPABASE_SERVICE_ROLE_KEY":
                            supabase_key = v
    if not supabase_url or not supabase_key:
        return

    try:
        hdrs = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        req = urllib.request.Request(
            f"{supabase_url}/rest/v1/jobs?fit_explanation=is.null&status=neq.rejected&fit_score=gte.7&select=fit_score",
            headers=hdrs
        )
        awaiting = len(json.loads(urllib.request.urlopen(req).read()))
        req2 = urllib.request.Request(
            f"{supabase_url}/rest/v1/jobs?fit_explanation=not.is.null&status=neq.rejected&select=fit_score",
            headers=hdrs
        )
        evaluated = len(json.loads(urllib.request.urlopen(req2).read()))

        cache_path = os.path.join(SCRIPT_DIR, "logs", ".eval_queue_count")
        with open(cache_path, "w") as f:
            json.dump({"awaiting": awaiting, "evaluated": evaluated, "timestamp": datetime.now(timezone.utc).isoformat()}, f)
    except Exception:
        pass


if __name__ == "__main__":
    if skip_scrape():
        sys.exit(0)

    from dotenv import load_dotenv
    load_dotenv()

    from scraper import run
    run()
    record_run()
    request_ras_evaluation()
    update_eval_queue_cache()
