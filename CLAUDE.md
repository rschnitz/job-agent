# Job Agent — Claude Code Instructions

## Cross-project coordination

This project shares scoring infrastructure with `~/Dropbox/RAS` (Ray's job search system).

**Inbox**: Check `.claude/inbox/` at session start for messages from other Claude instances.
**Outbox**: Write messages to `~/Dropbox/RAS/.claude/inbox/` when coordination is needed.

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
