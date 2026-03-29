-- Closed alpha readiness: unify feedback + memory/profile tables into canonical sql migrations.
-- Depends on: 10_schema_core.sql, 52_schema_recommendations.sql

-- 1) notes
create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  source_id uuid null references public.sources(id) on delete set null,
  chunk_id uuid null references public.chunks(id) on delete set null,
  topic text null,
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_notes_user_created
  on public.notes (user_id, created_at desc);

create index if not exists idx_notes_user_source_created
  on public.notes (user_id, source_id, created_at desc);

comment on table public.notes is
  'User notes used for weekly summary/recommendation personalization.';

-- 2) feedback_events
create table if not exists public.feedback_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  target_type text not null,
  target_id uuid not null,
  action text not null,
  reasons jsonb null,
  comment text null,
  source_id uuid null references public.sources(id) on delete set null,
  week_start date null,
  meta jsonb null,
  client_event_id text null,
  created_at timestamptz not null default now(),

  constraint feedback_events_target_type_check
    check (target_type in ('summary_s1', 'summary_s2', 'recommendation')),
  constraint feedback_events_action_check
    check (action in ('thumbs_up', 'thumbs_down', 'save', 'dismiss', 'open')),
  constraint feedback_events_reasons_is_array_check
    check (reasons is null or jsonb_typeof(reasons) = 'array'),
  constraint feedback_events_meta_is_object_check
    check (meta is null or jsonb_typeof(meta) = 'object'),
  constraint feedback_events_comment_len_check
    check (comment is null or char_length(comment) <= 2000),
  constraint feedback_events_client_event_id_len_check
    check (client_event_id is null or char_length(client_event_id) <= 100)
);

create index if not exists idx_feedback_events_user_created
  on public.feedback_events (user_id, created_at desc);

create index if not exists idx_feedback_events_target_created
  on public.feedback_events (target_type, target_id, created_at desc);

create index if not exists idx_feedback_events_action_created
  on public.feedback_events (action, created_at desc);

create index if not exists idx_feedback_events_week_start
  on public.feedback_events (week_start);

create index if not exists idx_feedback_events_source_id
  on public.feedback_events (source_id);

create unique index if not exists uq_feedback_events_client_event_id
  on public.feedback_events (client_event_id)
  where client_event_id is not null;

comment on table public.feedback_events is
  'User feedback event log for S1/S2 summaries and recommendations.';

-- 3) recommendation_generation_runs
create table if not exists public.recommendation_generation_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  week_start date not null,
  stage text not null default 'stage2',
  keyword_snapshot jsonb not null default '[]'::jsonb,
  candidate_count int not null default 0,
  selected_count int not null default 0,
  query_text text null,
  selected_urls jsonb not null default '[]'::jsonb,
  score_breakdown jsonb not null default '{}'::jsonb,
  stage1_suggestion_ids jsonb not null default '[]'::jsonb,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),

  constraint recommendation_generation_runs_stage_check
    check (stage in ('stage1', 'stage2')),
  constraint recommendation_generation_runs_keyword_snapshot_is_array
    check (jsonb_typeof(keyword_snapshot) = 'array'),
  constraint recommendation_generation_runs_selected_urls_is_array
    check (jsonb_typeof(selected_urls) = 'array'),
  constraint recommendation_generation_runs_score_breakdown_is_object
    check (jsonb_typeof(score_breakdown) = 'object'),
  constraint recommendation_generation_runs_stage1_ids_is_array
    check (jsonb_typeof(stage1_suggestion_ids) = 'array'),
  constraint recommendation_generation_runs_meta_is_object
    check (jsonb_typeof(meta) = 'object')
);

create index if not exists idx_recommendation_runs_user_week_created
  on public.recommendation_generation_runs (user_id, week_start desc, created_at desc);

create index if not exists idx_recommendation_runs_user_stage_created
  on public.recommendation_generation_runs (user_id, stage, created_at desc);

-- 4) user_keywords (keyword-anchored profile)
create table if not exists public.user_keywords (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  keyword text not null,
  weight real not null default 1.0,
  source text not null default 'user_explicit',
  status text not null default 'active',
  parent_keyword_id uuid null references public.user_keywords(id) on delete set null,
  accept_count int not null default 0,
  paper_feedback_up int not null default 0,
  paper_feedback_down int not null default 0,
  last_activity timestamptz not null default now(),
  rejected_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint user_keywords_weight_non_negative check (weight >= 0),
  constraint user_keywords_source_check check (
    source in ('user_explicit', 'stage1_accepted', 'stage1_rejected', 's2_derived')
  ),
  constraint user_keywords_status_check check (
    status in ('active', 'declining', 'archived')
  )
);

create index if not exists idx_user_keywords_user_status_weight
  on public.user_keywords (user_id, status, weight desc, updated_at desc);

create index if not exists idx_user_keywords_user_keyword_lower
  on public.user_keywords (user_id, lower(keyword));

create unique index if not exists uq_user_keywords_user_keyword_active
  on public.user_keywords (user_id, lower(keyword))
  where status in ('active', 'declining');

comment on table public.user_keywords is
  'Keyword-anchored user profile state with weights and feedback counters.';

-- 5) keyword_suggestions (Stage 1 output)
create table if not exists public.keyword_suggestions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  keyword text not null,
  parent_keyword text null,
  suggestion_type text not null default 'derivative',
  reason text null,
  confidence real not null default 0.5,
  status text not null default 'pending',
  responded_at timestamptz null,
  source_run_id uuid null references public.recommendation_generation_runs(id) on delete set null,
  week_start date not null,
  created_at timestamptz not null default now(),

  constraint keyword_suggestions_confidence_range check (confidence >= 0 and confidence <= 1),
  constraint keyword_suggestions_type_check check (
    suggestion_type in ('derivative', 'emerging', 'cross_domain', 'deepening')
  ),
  constraint keyword_suggestions_status_check check (
    status in ('pending', 'accepted', 'rejected')
  )
);

create index if not exists idx_keyword_suggestions_user_created
  on public.keyword_suggestions (user_id, created_at desc);

create index if not exists idx_keyword_suggestions_user_status_created
  on public.keyword_suggestions (user_id, status, created_at desc);

create index if not exists idx_keyword_suggestions_user_week_created
  on public.keyword_suggestions (user_id, week_start desc, created_at desc);

-- 6) optional snapshot table (not required by current runtime, but referenced in docs)
create table if not exists public.user_interest_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  snapshot_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint user_interest_profiles_snapshot_is_object check (jsonb_typeof(snapshot_json) = 'object')
);

create index if not exists idx_user_interest_profiles_user_created
  on public.user_interest_profiles (user_id, created_at desc);

