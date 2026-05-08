-- Job Agent Schema
-- Apply this in Supabase Dashboard → SQL Editor → New Query

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  company text not null,
  url text,
  description text,
  source text,
  status text not null default 'new' check (status in ('new','saved','applied','interviewing','offer','rejected')),
  -- Pipeline watermark: highest stage reached (never downgrades)
  stage text default 'new' check (stage in ('new','ready','applied','acked','screened','interviewed','offered')),
  -- Disposition: current outcome state
  outcome text default 'active' check (outcome in ('active','ghosted','rejected','withdrawn','closed','accepted','declined')),
  haiku_score integer,
  ras_fit integer,
  fit_explanation text,
  ras_interest integer,
  relevance_explanation text,
  salary_min integer,
  salary_max integer,
  bonus_or_commission_est integer,
  equity_est integer,
  location text,
  remote_days integer,
  posted_at timestamptz,
  applicant_count integer,
  rejection_reason text,
  notes text,
  last_refreshed_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists profiles (
  id uuid primary key default gen_random_uuid(),
  resume_text text,
  skills text,
  preferences text,
  created_at timestamptz not null default now()
);

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references jobs(id) on delete cascade,
  messages jsonb not null default '[]',
  created_at timestamptz not null default now()
);

-- Enable RLS with permissive policies (single-user, no auth yet)
-- Anon key gets full access; tighten when auth is added
alter table jobs enable row level security;
alter table profiles enable row level security;
alter table conversations enable row level security;

-- Jobs: anon can read, service_role can write (API routes use service_role)
create policy "jobs_read" on jobs for select using (true);
create policy "jobs_insert" on jobs for insert with check (true);
create policy "jobs_update" on jobs for update using (true);
create policy "jobs_delete" on jobs for delete using (true);

-- Profiles: same
create policy "profiles_read" on profiles for select using (true);
create policy "profiles_insert" on profiles for insert with check (true);
create policy "profiles_update" on profiles for update using (true);

-- Conversations: same
create policy "conversations_read" on conversations for select using (true);
create policy "conversations_insert" on conversations for insert with check (true);
create policy "conversations_update" on conversations for update using (true);

-- Migration: add last_refreshed_at column (2026-05-03)
-- alter table jobs add column if not exists last_refreshed_at timestamptz;

-- Migration: add stage + outcome columns (2026-05-02)
-- Run these if upgrading an existing database:
-- alter table jobs add column if not exists stage text default 'new' check (stage in ('new','ready','applied','acked','screened','interviewed','offered'));
-- alter table jobs add column if not exists outcome text default 'active' check (outcome in ('active','ghosted','rejected','withdrawn','closed','accepted','declined'));
-- update jobs set stage = case status when 'applied' then 'applied' when 'interviewing' then 'interviewed' when 'offer' then 'offered' else 'new' end where stage is null or stage = 'new';
-- update jobs set outcome = case status when 'rejected' then 'rejected' else 'active' end where outcome is null or outcome = 'active';

-- Seed default profile (upsert so re-running schema is safe)
insert into profiles (id, resume_text, skills, preferences) values (
  '00000000-0000-0000-0000-000000000001',
  'MIT BS/MS Computer Science and Electrical Engineering.

Experience:
- Engineering Manager, Wells Fargo Bank, San Francisco (2004-2025)
  Envisioned and led AuthHub, cloud-native enterprise authentication platform. Scaled teams 0→20+. $2MM+ annual fraud savings. 25% per-project cost reduction via data-driven engineering. Created code generation tools and quality pipelines (SonarQube, mutation testing).

- Consulting Principal Engineer, Lexicon Branding / ShockProof / CarMagic (2025-present)
  Platform modernization, AI-enhanced tools, architectural evaluation.

- Director of Software Development, Round1, San Francisco
  Fintech platform for institutional investors. International patent filed.

- Senior Engineer, Samsung Advanced Media Laboratory
  11 US patents. Simulation platform reducing dev cycles by 6 months.

Key narrative: "I develop whole engineers who take ownership beyond code — engineers who lead projects, mentor others, drive quality improvements, and own their systems in production."',

  'Java, Python, Shell scripting, C++, SpringBoot, OpenShift, RESTful APIs, MongoDB, Microservices, CI/CD, OAuth/JWT, API Design, Integration Architecture, Cloud-native Platforms, Authentication/Identity Systems, Fraud Detection, SonarQube, Mutation Testing, Code Generation, Data Warehouses & Analytics',

  'Target roles: Engineering Manager, Senior EM, Director of Engineering, Head of Engineering.
Location: Piedmont/Bay Area — SF, Oakland, Berkeley preferred. Remote OK. South Bay acceptable.
Target comp: $200k+ total compensation baseline.
Industries: Fintech, authentication/identity, platform engineering, AI/ML, developer tools.
Values: Meaningful mission, strong people development culture, collaborative technical decision-making.
Cover letter style: Direct, substantive, technically confident but people-focused. Lead with specific impact, not generic enthusiasm.'
) on conflict (id) do nothing;
