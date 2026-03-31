#!/usr/bin/env python3
"""
Backfill outcome and score columns in seen_jobs from scraper logs.

Parses log lines like:
  Alerted: Title @ Company (score 8)
  Claude filtered: Title @ Company -- reason
  Quick filtered: Title @ Company -- reason
  OR filtered (5.2h old, 45 applicants): Title @ Company

Matches to seen_jobs by title+company (since URLs aren't in logs).
"""

import re
import sqlite3
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "jobs.db")
LOG_PATH = os.path.join(SCRIPT_DIR, "logs", "scraper.log")


def backfill():
    conn = sqlite3.connect(DB_PATH)

    # Ensure columns exist
    for col in ["outcome", "score"]:
        try:
            conn.execute(f"ALTER TABLE seen_jobs ADD COLUMN {col} {'TEXT' if col == 'outcome' else 'INTEGER'}")
        except sqlite3.OperationalError:
            pass

    # Count current state
    total = conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    has_outcome = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE outcome IS NOT NULL AND outcome != ''").fetchone()[0]
    print(f"seen_jobs: {total} total, {has_outcome} already have outcomes, {total - has_outcome} to backfill")

    # Build lookup: (title_lower, company_lower) -> job_url
    rows = conn.execute("SELECT job_url, title, company FROM seen_jobs WHERE outcome IS NULL OR outcome = ''").fetchall()
    lookup = {}
    for url, title, company in rows:
        key = (str(title).lower().strip(), str(company).lower().strip())
        lookup[key] = url

    # Parse log
    updated = 0
    with open(LOG_PATH, "r") as f:
        for line in f:
            # Alerted: Title @ Company (score 8)
            m = re.search(r"Alerted: (.+?) @ (.+?) \(score (\d+)\)", line)
            if m:
                title, company, score = m.group(1).strip(), m.group(2).strip(), int(m.group(3))
                key = (title.lower(), company.lower())
                if key in lookup:
                    conn.execute(
                        "UPDATE seen_jobs SET outcome = ?, score = ? WHERE job_url = ?",
                        ("alerted", score, lookup[key])
                    )
                    del lookup[key]
                    updated += 1
                continue

            # Claude filtered: Title @ Company -- reason
            m = re.search(r"Claude filtered: (.+?) @ (.+?) -- (.+)", line)
            if m:
                title, company = m.group(1).strip(), m.group(2).strip()
                key = (title.lower(), company.lower())
                if key in lookup:
                    conn.execute(
                        "UPDATE seen_jobs SET outcome = ? WHERE job_url = ?",
                        ("claude_filtered", lookup[key])
                    )
                    del lookup[key]
                    updated += 1
                continue

            # Quick filtered: Title @ Company -- reason
            m = re.search(r"Quick filtered: (.+?) @ (.+?) -- (.+)", line)
            if m:
                title, company = m.group(1).strip(), m.group(2).strip()
                key = (title.lower(), company.lower())
                if key in lookup:
                    conn.execute(
                        "UPDATE seen_jobs SET outcome = ? WHERE job_url = ?",
                        ("quick_filtered", lookup[key])
                    )
                    del lookup[key]
                    updated += 1
                continue

            # OR filtered
            m = re.search(r"OR filtered .+?: (.+?) @ (.+?)$", line)
            if m:
                title, company = m.group(1).strip(), m.group(2).strip()
                key = (title.lower(), company.lower())
                if key in lookup:
                    conn.execute(
                        "UPDATE seen_jobs SET outcome = ? WHERE job_url = ?",
                        ("freshness_filtered", lookup[key])
                    )
                    del lookup[key]
                    updated += 1
                continue

    conn.commit()

    # Summary
    has_outcome_after = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE outcome IS NOT NULL AND outcome != ''").fetchone()[0]
    has_score = conn.execute("SELECT COUNT(*) FROM seen_jobs WHERE score IS NOT NULL").fetchone()[0]
    print(f"Backfilled {updated} records")
    print(f"  Outcomes: {has_outcome_after}/{total}")
    print(f"  Scores: {has_score}/{total}")

    # Breakdown
    for row in conn.execute("SELECT outcome, COUNT(*) FROM seen_jobs GROUP BY outcome ORDER BY COUNT(*) DESC").fetchall():
        print(f"    {row[0] or '(none)'}: {row[1]}")

    conn.close()


if __name__ == "__main__":
    backfill()
