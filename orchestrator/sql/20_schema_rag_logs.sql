-- Optional RAG run and event logging tables
-- These tables are optional; the RAG service will fall back to application logging
-- if these tables don't exist.

-- RAG runs: tracks each RAG query execution
create table if not exists rag_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  query text not null,
  top_k int not null,
  topic text,
  lang text,
  status text not null default 'running',  -- 'running', 'completed', 'error'
  latency_ms int,
  error_message text,
  created_at timestamptz default now(),
  completed_at timestamptz
);

-- RAG events: tracks events within a run (retrieve, synthesize, etc.)
create table if not exists rag_events (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references rag_runs(id) on delete cascade,
  event_type text not null,  -- 'retrieve', 'synthesize', etc.
  data jsonb,
  created_at timestamptz default now()
);

-- Indexes for common queries
create index if not exists idx_rag_runs_user_id on rag_runs(user_id);
create index if not exists idx_rag_runs_status on rag_runs(status);
create index if not exists idx_rag_runs_created_at on rag_runs(created_at);
create index if not exists idx_rag_events_run_id on rag_events(run_id);

