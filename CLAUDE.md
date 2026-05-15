# Job Agent — Claude Code Instructions

## Project Ecosystem Responsibilities

Three projects form a coordinated job-search system:

- **job-agent** (`~/src/job-agent/`) — **This project.** Maintains the current production system: JobSpy scraper, Supabase database, and Next.js dashboard. Source of record for raw job data and pipeline state. Keep this running and stable.
- **RAS** (`~/Dropbox/RAS/`) — Manages actual job applications: cover letter prep, submission, recruiter follow-up, interview prep. Works with jobs sourced from job-agent or its own tools, including Discord-triggered workflows.
- **job-search** (`~/src/job-search/`) — Coordinates the long-term refactoring of job-agent and RAS into a unified, user-agnostic system. Primary responsibility is architecture and migration, not day-to-day operations.

## Cross-project coordination

**Session start — check all three project inboxes:**
1. job-agent inbox: `.claude/inbox/`
2. job-search inbox: `~/src/job-search/.claude/inbox/`
3. RAS inbox: `~/Dropbox/RAS/.claude/inbox/`
4. Broadcast inbox: `~/.claude/inbox/`

Direct messages to your own inbox go to `.claude/inbox/`. To reach another project, write to its inbox or use the inbox-send tool.

Related RAS capabilities: `/evaluate`, `/score-fit`, `comp_calculator.py`, `posting_cache.py`.

## Stack
- Next.js 16 (App Router, TypeScript)
- Supabase (PostgreSQL)
- Anthropic Claude API
- Tailwind CSS + shadcn/ui components
- Deployed on Vercel (auto-deploys on `git push origin master`)

## Dev

```bash
export PATH="/c/Program Files/nodejs:$PATH"
npm run dev    # local dev server at http://localhost:3000
npm run build  # production build (requires Vercel env vars or .env.local)
```

## Testing

```bash
npm test           # run all tests (vitest)
npm run test:watch # watch mode
```

See [TESTING.md](./TESTING.md) for conventions.

### Test expectations
- 100% test coverage is the goal — tests make vibe coding safe
- When writing new functions in `lib/`, write a corresponding test in `test/`
- When fixing a bug, write a regression test
- When adding error handling, write a test that triggers the error
- When adding a conditional (if/else), write tests for both paths
- Never commit code that makes existing tests fail
- Mock `@anthropic-ai/sdk` and `@supabase/supabase-js` — never make real API calls in tests

## Key Files
- `app/api/jobs/ingest/route.ts` — webhook for scraper (POST with `x-api-key` header)
- `app/api/chat/route.ts` — Claude streaming chat
- `lib/claude.ts` — system prompt builder + `buildSystemPrompt()`
- `lib/supabase.ts` — DB client + TypeScript types
- `components/ui/` — shadcn/ui components (Button, Card, Input, Textarea, Badge)
