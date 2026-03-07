-- Weekly Recommendation: store arXiv title + abstract + original link (no ingest until user taps Process)
-- Depends: 10_schema_core.sql (users)

create table if not exists public.recommendations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  topic_name text not null,
  week_start date not null,
  title text not null,
  abstract text,
  url text not null,
  source text not null default 'arXiv',
  score float,
  created_at timestamptz default now()
);

create index if not exists idx_recommendations_user_created
  on public.recommendations (user_id, created_at desc);

comment on table public.recommendations is 'Weekly arXiv recommendations (title+abstract+url). Ingest only when user taps Process.';
comment on column public.recommendations.url is 'Original article link (e.g. arxiv.org/abs/...). Shown on card; used for ingest (backend converts abs→pdf if needed).';
