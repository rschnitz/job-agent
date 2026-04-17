# POIND: job-agent
*Generated: 2026-04-16T17:00:00-07:00*

## Active threads

**Job search consolidation v5 — plan complete, execution pending.** Five design iterations (v1→v5) with two critique cycles. v5 at `~/.claude/plans/job-search-consolidation-v5.md`. Cover letter model: XeLaTeX template + paragraph library (letters/paragraphs/*.tex) + per-application config.yaml; PDFs committed as permanent record. Resume: folder-based variants on main (resume/canonical/, resume/variants/{name}/), always named RaySchnitzler.*. 18-tag vocabulary. 4-phase migration with Phase 3 split into 3a-3g. lib_score threshold at 0 — re-enable after migration stabilizes.

## Open between us

- **Begin migration** — Phase 0 (prep) + Phase 1 (subtree import) from v5 plan. No work started yet.
- **lib_score threshold** — still at 0 (every job passes). Re-enable post-migration.

## Settled

- Repo name: `job-search` (private); delete public fork post-migration
- bd v1; Supabase for jobs, Dolt for beads/comms only; kill jobs.xlsx
- Google Sheet: dynamic calculated view, read-only target (not write)
- Cover letters: XeLaTeX (template + paragraphs). Resume: DOCX (canonical + variants as folders). No binaries in git except committed PDFs under letters/applications/{slug}/
- Skills over CLAUDE.md: guidance in `.claude/skills/`, no `.claude/commands/`
- hiresig: don't migrate without intent to develop
- Source abstraction and semantic index: both deferred post-migration
- LinkedIn message ingestion: RAS owns it (Playwright + existing Edge session)
- Scoring: haiku_score (1-10), ras_fit (1-8), ras_interest (0-100)
- Three-tier triage: lib<30 auto-reject, 30-60 Haiku, >60 auto-pass + invest more LLM effort
- DB rename `ras_suitability` → `ras_interest` complete in code + Supabase (confirmed)
