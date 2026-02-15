-- users (firebase_uid로 매핑)
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  firebase_uid text unique not null,
  email text,
  display_name text,
  created_at timestamptz default now()
);

-- sources: 기사/논문/웹 문서
create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  url text,
  title text,
  authors text[],
  published_at timestamptz,
  lang text,
  meta jsonb,
  hash text unique,
  created_at timestamptz default now()
);

-- chunks & embeddings
create table if not exists chunks (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id) on delete cascade,
  ord int,
  text text
);

create table if not exists embeddings (
  chunk_id uuid primary key references chunks(id) on delete cascade,
  embedding vector(1536)
);

-- summaries (S1/S2)
create table if not exists summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  scope text not null,  -- 'doc' or 'topic'
  kind text not null,  -- 'S1' or 'S2'
  source_id uuid references sources(id) on delete cascade,
  tldr text,
  bullets jsonb,
  extra jsonb,
  created_at timestamptz default now()
);

-- indexing for vector search
create index if not exists idx_embeddings_cosine
  on embeddings using ivfflat (embedding vector_cosine_ops);

-- Indexes for common queries
create index if not exists idx_sources_user_id on sources(user_id);
create index if not exists idx_chunks_source_id on chunks(source_id);
create index if not exists idx_summaries_user_id on summaries(user_id);
create index if not exists idx_summaries_source_id on summaries(source_id);
create index if not exists idx_summaries_scope_kind on summaries(scope, kind);

