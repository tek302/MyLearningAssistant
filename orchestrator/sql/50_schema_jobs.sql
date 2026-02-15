-- Week6: jobs table for single-process async ingest; sources status standardization

-- Optional: ensure sources has updated_at and unique (user_id, url) for upsert
alter table sources add column if not exists updated_at timestamptz default now();
-- Allow upsert on (user_id, url). Multiple (user_id, NULL) allowed (NULLs distinct in unique index).
create unique index if not exists idx_sources_user_id_url on sources (user_id, url);

-- jobs: one row per async ingest job
create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  job_type text not null,
  state text not null default 'queued',
  progress int not null default 0,
  source_id uuid references sources(id) on delete set null,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_jobs_user_created on jobs (user_id, created_at desc);
create index if not exists idx_jobs_state_updated on jobs (state, updated_at desc);

comment on table public.jobs is 'Week6: async ingest jobs (queued|running|done|failed)';
