-- Analytics: run this once in Supabase (SQL Editor > New query > paste > Run).
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
