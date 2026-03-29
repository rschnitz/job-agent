# Job Agent — Setup Guide

## Prerequisites

- Node.js 20+ (`node --version`)
- Python 3.11+ (for job-scout scraper/bot)
- An Anthropic API key (reuse an existing one — same key works everywhere)
- A Supabase account (free tier is fine)
- A Discord account

---

## 1. Supabase (Database)

1. Go to [supabase.com](https://supabase.com) and sign in (GitHub or email)
2. Click **New Project**
   - Organization: your personal org (created automatically)
   - Name: `job-agent`
   - Database password: generate a strong one, save it somewhere
   - Region: `us-west-1` (closest to Bay Area)
3. Wait ~2 minutes for provisioning
4. Go to **SQL Editor** (left sidebar) → **New Query**
5. Paste the contents of `supabase/schema.sql` and click **Run**
6. Go to **Settings → API Keys** (left sidebar → gear icon → API Keys)
7. Copy these values:

| Setting | Env var |
|---------|---------|
| Project URL (shown at top of Settings page) | `NEXT_PUBLIC_SUPABASE_URL` |
| Publishable key (`sb_publishable_...`) or anon key | `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Secret key or service_role key (click reveal) | `SUPABASE_SERVICE_ROLE_KEY` |

> **Note:** Supabase is transitioning from "anon"/"service_role" keys to "publishable"/"secret" keys. Either format works — use whichever your dashboard shows. If you see a "Legacy" tab, the new keys are on the main API Keys page.
>
> The secret/service_role key bypasses Row Level Security. Never expose it client-side.

---

## 2. Web UI (.env.local)

```bash
cp .env.local.example .env.local
```

Edit `.env.local` with your values:

```
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
INGEST_API_KEY=<generate: openssl rand -hex 32>
```

Test:

```bash
npm install
npm run dev
# Visit http://localhost:3000
```

---

## 3. Discord Bot

### 3a. Create a Discord server

1. Open Discord (app or browser)
2. Click **+** in the left sidebar → **Create My Own** → **For me and my friends**
3. Name it whatever you like (e.g., "Job Search")
4. Create two text channels:
   - `#job-alerts` — where the scraper posts new matches
   - `#requests` — where you post URLs/PDFs for tailoring

### 3b. Enable Developer Mode (needed to copy IDs)

1. Discord Settings → **Advanced** → toggle **Developer Mode** on
2. Now you can right-click channels, users, and servers to **Copy ID**

### 3c. Create a bot application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it "Job Scout" → Create
3. Go to **Bot** tab (left sidebar):
   - Click **Reset Token** → copy the token → save as `DISCORD_BOT_TOKEN`
   - Under **Privileged Gateway Intents**, enable:
     - **Message Content Intent** (required for reading messages)
     - **Server Members Intent** (optional but useful)
4. Go to **OAuth2** tab → **URL Generator**:
   - Scopes: check `bot`
   - Bot Permissions: check these:
     - Send Messages
     - Read Message History
     - Add Reactions
     - Attach Files
     - Embed Links
     - Use External Emojis
   - Copy the generated URL at the bottom
5. Open that URL in your browser → select your server → Authorize

### 3d. Collect IDs

Right-click each item and select **Copy ID**:

| What to copy | Env var |
|-------------|---------|
| `#job-alerts` channel | `DISCORD_CHANNEL_ID` |
| `#requests` channel | `REQUESTS_CHANNEL_ID` |
| Your own user (click your name) | `DISCORD_USER_ID` |

### 3e. Create a webhook

1. In Discord: right-click `#job-alerts` → **Edit Channel** → **Integrations** → **Webhooks**
2. Click **New Webhook** → name it "Job Scout" → **Copy Webhook URL**
3. Save as `DISCORD_WEBHOOK_URL`

### 3f. Configure the bot

```bash
cd job-scout
cp .env.example .env
```

Edit `job-scout/.env`:

```
DISCORD_BOT_TOKEN=<from step 3c>
DISCORD_WEBHOOK_URL=<from step 3e>
DISCORD_CHANNEL_ID=<from step 3d>
REQUESTS_CHANNEL_ID=<from step 3d>
DISCORD_USER_ID=<from step 3d>
ANTHROPIC_API_KEY=sk-ant-...
INGEST_URL=https://your-vercel-app.vercel.app/api/jobs/ingest
INGEST_API_KEY=<same key as web UI .env.local>
```

### 3g. Test the bot locally

```bash
cd job-scout
uv venv
uv pip install -r requirements.txt
uv run python bot.py
```

You should see "Job Scout bot online as ..." in your terminal and the bot should appear online in your Discord server.

---

## 4. Scraper Setup

The scraper runs independently from the bot. Test it:

```bash
cd job-scout
source venv/bin/activate
python scraper.py
```

For recurring runs, set up a cron job:

```bash
crontab -e
```

Add (every 15 minutes during business hours, hourly otherwise):

```cron
*/15 6-20 * * 1-5 cd /path/to/job-agent/job-scout && /path/to/venv/bin/python scraper.py
0 21-5 * * 1-5 cd /path/to/job-agent/job-scout && /path/to/venv/bin/python scraper.py
0 * * * 0,6 cd /path/to/job-agent/job-scout && /path/to/venv/bin/python scraper.py
```

---

## 5. Vercel Deployment

The web UI auto-deploys on `git push origin master`.

Set these environment variables in the Vercel dashboard (Settings → Environment Variables):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`
- `INGEST_API_KEY`

---

## 6. Verify Everything Works

1. **Web UI**: Visit your Vercel URL or localhost:3000 — kanban board should load (empty)
2. **Bot**: Run `bot.py` — bot appears online in Discord
3. **Scraper**: Run `scraper.py` — check logs for "Scraper run started"
4. **End-to-end**: When scraper finds a match, it should:
   - Post to `#job-alerts` in Discord
   - POST to `/api/jobs/ingest` on your web UI
   - Job appears on the kanban board

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `NEXT_PUBLIC_SUPABASE_URL` not set | Check `.env.local` exists and is not gitignored from loading |
| Bot shows offline in Discord | Check `DISCORD_BOT_TOKEN`, ensure Message Content Intent is enabled |
| Scraper finds 0 results | LinkedIn may be rate-limiting; check `job-scout/jobs.db` for seen count |
| Ingest returns 401 | `INGEST_API_KEY` must match between scraper `.env` and web `.env.local` |
| pdflatex not found (tailor.py) | `brew install basictex` on macOS, or switch to Typst pipeline |
