-- Run this once in Supabase: SQL Editor > New query > paste > Run
create table if not exists subscriptions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  user_name text,
  email text not null,
  whatsapp text,
  label text,
  topics jsonb not null default '[]',
  format text not null,
  channel text not null,
  freq_type text not null,
  interval_days int,
  weekday int,
  hour int not null default 8,
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  active boolean not null default true,
  covered_ids jsonb not null default '[]'
);

create table if not exists deliveries (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  subscription_id uuid,
  email text not null,
  channel text,
  format text,
  topics jsonb,
  trigger text,
  status text,
  detail text,
  content text
);

-- Nobody can read these tables with the public key. Only the secret key used by the app can.
alter table subscriptions enable row level security;
alter table deliveries enable row level security;

-- Make sure the app (secret key = service_role) can always read and write both tables
grant usage on schema public to service_role;
grant all on table subscriptions to service_role;
grant all on table deliveries to service_role;
-- Analytics table (also in supabase_analytics.sql)
-- Stores every answer and briefing together with its evaluation.
create table if not exists interactions (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  email text,
  kind text not null,              -- 'chat' or 'delivery'
  question text,
  answer text,
  cited_ids jsonb not null default '[]',
  topics jsonb not null default '[]',
  format text,
  channel text,
  model text,
  latency_ms int,
  answer_words int,
  n_citations int,
  not_covered boolean default false,
  rating int,                      -- 1 to 5 stars from the reader
  tags jsonb not null default '[]',
  comment text,
  auto_score int,                  -- 1 to 5 groundedness score from the automatic check
  auto_reason text
);
alter table interactions enable row level security;
grant all on table interactions to service_role;
