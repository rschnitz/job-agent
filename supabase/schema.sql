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
  notes text,
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

-- Disable RLS (single-user app, no auth needed)
alter table jobs disable row level security;
alter table profiles disable row level security;
alter table conversations disable row level security;

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
