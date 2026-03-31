*POIND generated: 2026-03-31T00:15:00-07:00*

## Active threads

**Scoring architecture — designed, blocked on RAS integration.** We agreed on a two-table schema: `jobs` (core facts: relevance + fit scores, salary min/max/bonus/equity, location, remote_days, posted_at, applicant_count) and `job_evaluations` (bespoke derived scores: effective comp, commute, recency, overall priority). The core columns are in Supabase. The next step is extracting `evaluate_job.py` from RAS's `/evaluate` and `/score-fit` commands — this replaces Claude Haiku's too-generous scoring with RAS's calibrated rubric. A message has been sent to RAS's inbox but no response yet. The blocker is that I can't invoke RAS commands, only read its files.

**Search optimization — instrumented, awaiting data.** Scraper now logs query overlap + position + scores to CSV. We bumped to 100 results per query to test whether the long tail (positions 51-100) has value. Need 2-3 more runs to determine the minimum viable search set. Current hypothesis: "Engineering Manager", "Head of Engineering", "Principal Engineer", and "EM remote" might be sufficient — the specialized terms produced zero exclusive high-score jobs in one analyzed run.

**Cross-project coordination — protocol established.** Inbox convention in `~/CLAUDE.md`: markdown files in `.claude/inbox/`, check every 3+ minutes during active work. Message sent to RAS requesting scoring infrastructure cooperation. No response yet. Bead `ja-p0l` to evaluate `/loop` or `/schedule` for periodic polling.

**Job detail page — may still be broken.** Diagnosed as Node upgrade issue requiring dev server restart. User restarted but hasn't confirmed it works. The `.maybeSingle()` fix should resolve the hang.

## Open between us

- **Does the job detail page work now?** You restarted the dev server but we haven't confirmed the fix landed.
- **RAS inbox response.** Need you to open a Claude session in `~/Dropbox/RAS` and point it at the message in `.claude/inbox/`. That session can evaluate whether `evaluate_job.py` extraction is feasible and respond.
- **Uncommitted work.** Schema migration (new core columns), scraper changes (radius search, exclusions, overlap logging), POIND skill update, cross-project inbox setup, CLAUDE.md updates — all uncommitted since last commit.

## Settled

- Relevance (do I want this?) and fit (am I qualified?) are separate scores, both in core `jobs` table
- Comp stored as facts (salary_min, salary_max, bonus_or_commission_est, equity_est); scoring is derived in `job_evaluations`
- Urgency model: jobs passing relevance + fit get tiered alerts (URGENT/HIGH/MEDIUM/LOW) based on freshness x applicant count (`ja-7fi`)
- Commute model: weekly effective one-way minutes, remote day penalties (1d=10m, 2d=35m, 3d=60m, 4d=105m, 5d=150m), shuttle = usable time not speed (`ja-sek`)
- Insurance is NOT an excluded industry
- Job aggregators excluded only when the company name IS the aggregator, not when they list real companies
- Cross-project communication via `.claude/inbox/` markdown files, documented in `~/CLAUDE.md`
- POIND writes to `.claude/poind.md` as well as chat

## Next pull

Commit the current changes, then open a RAS session to get the scoring integration unblocked.
