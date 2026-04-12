# POIND: job-agent
*Generated: 2026-04-04T08:00:00-07:00*

## Active threads

**Scraper is operational and automated.** Running every 15 min (daytime) via launchctl. Radius search from Orinda, urgency-tiered Discord alerts, posting cache, auto-evaluation requests to RAS. NaN ingest bug fixed and 39 lost jobs recovered. Overlap analysis logging in place but search term optimization deferred — data still accumulating.

**RAS scoring integration — in progress.** RAS has scored all 42 Haiku 8+ jobs from the initial batch plus individual priority requests (Bugcrowd, Zillow, Checkr, Chainguard, Help Scout, Mechanical Orchard, Banyan, Arcade.dev). 52 jobs sent for full /evaluate in latest batch. Shared lib (~/src/job-search-lib/) extraction agreed but not yet started by RAS. Auto-eval requests sent after each scraper run.

**Resume work — Bugcrowd 1-page version complete.** RaySchnitzler2c.tex: v3 layout, Open Sans 11pt, education inline, all metrics bolded. Ready for submission. Cover letter also prepared by RAS.

**Application pipeline active.** Applied: OpenAI (Fit 9), Arcade.dev (Fit 8), Banyan (Fit 8), Anthropic FinServ (Fit 7), Retool (unscored), Stripe (unscored). Bugcrowd (Fit 8) ready to apply. ~25 Fit 7 roles evaluated and ready.

## Open between us

- **122 jobs still need RAS evaluation** (Haiku 7+, no fit_explanation). Batch of 52 eights sent. Sevens not yet requested.
- **Retool and Stripe** — applied but no RAS evaluation or salary data. Should request.
- **Shared lib not started** — RAS confirmed ownership but no `lib-ready-scoring` message yet. Scoring still uses Haiku.
- **4 unpushed commits** on master. Should push to origin?

## Settled

- relevance_score is 0-100 (matching RAS Suitability), fit_score is 1-8 (RAS scale)
- Urgency tiers: URGENT 8+/<1h/<=25appl, HIGH 6+/<4h/<25, MEDIUM 5+/<24h/<50, LOW rest
- Requests to RAS always use full /evaluate (not /score-fit)
- Posting HTML cache at ~/.cache/job-search/postings/ shared with RAS
- Dismiss = reject with reason, not delete
- Scraper schedule: 15min 7am-7pm, hourly evenings, overnight at 12:30/2/4/6am
- Resume 1-page template: v3 layout, education inline in skills section
