-- Interest threads + per-thread keyword weights (global user_keywords pool, junction weights).
-- Depends: 10_schema_core.sql, 53_schema_alpha_feedback_memory.sql (user_keywords), 52_schema_recommendations.sql

-- 1) Threads per user (one row with is_default = true per user)
create table if not exists public.interest_threads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  name text not null,
  description text null,
  is_default boolean not null default false,
  archived_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_interest_threads_user_default
  on public.interest_threads (user_id)
  where (is_default = true);

create index if not exists idx_interest_threads_user_created
  on public.interest_threads (user_id, created_at desc);

comment on table public.interest_threads is
  'User-defined research threads; default thread holds legacy unscoped content.';

-- 2) Per-thread activation / multiplier over global user_keywords
create table if not exists public.thread_keyword_weights (
  id uuid primary key default gen_random_uuid(),
  thread_id uuid not null references public.interest_threads(id) on delete cascade,
  user_keyword_id uuid not null references public.user_keywords(id) on delete cascade,
  weight_multiplier real not null default 1.0,
  activation real not null default 1.0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint thread_keyword_weights_activation_range check (activation >= 0 and activation <= 1),
  constraint thread_keyword_weights_multiplier_positive check (weight_multiplier > 0)
);

create unique index if not exists uq_thread_keyword_weights_thread_kw
  on public.thread_keyword_weights (thread_id, user_keyword_id);

create index if not exists idx_thread_keyword_weights_keyword
  on public.thread_keyword_weights (user_keyword_id);

-- 3) Optional FK from sources / notes / suggestions / recommendations
alter table public.sources add column if not exists thread_id uuid null
  references public.interest_threads(id) on delete set null;

create index if not exists idx_sources_user_thread_created
  on public.sources (user_id, thread_id, created_at desc);

alter table public.notes add column if not exists thread_id uuid null
  references public.interest_threads(id) on delete set null;

alter table public.keyword_suggestions add column if not exists thread_id uuid null
  references public.interest_threads(id) on delete set null;

alter table public.recommendations add column if not exists thread_id uuid null
  references public.interest_threads(id) on delete set null;

create index if not exists idx_recommendations_user_thread_created
  on public.recommendations (user_id, thread_id, created_at desc);

-- 4) Backfill: one default thread per user, attach legacy rows
insert into public.interest_threads (user_id, name, description, is_default, archived_at)
select u.id, 'General', 'Default research thread', true, null
from public.users u
where not exists (
  select 1 from public.interest_threads t
  where t.user_id = u.id and t.is_default = true
);

update public.sources s
set thread_id = t.id
from public.interest_threads t
where s.thread_id is null
  and s.user_id = t.user_id
  and t.is_default = true;

update public.summaries sm
set extra = coalesce(sm.extra, '{}'::jsonb) || jsonb_build_object('thread_id', t.id::text)
from public.interest_threads t
where sm.user_id = t.user_id
  and sm.scope = 'topic'
  and sm.kind = 'S2'
  and t.is_default = true
  and (sm.extra->>'thread_id' is null or trim(sm.extra->>>'thread_id') = '');

update public.recommendations r
set thread_id = t.id
from public.interest_threads t
where r.thread_id is null
  and r.user_id = t.user_id
  and t.is_default = true;
