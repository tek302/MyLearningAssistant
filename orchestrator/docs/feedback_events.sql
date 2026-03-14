-- Supabase SQL editor용 feedback_events 초기 스키마
-- Copy & paste into SQL editor.

create extension if not exists pgcrypto;

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

comment on column public.feedback_events.target_type is
    'summary_s1 | summary_s2 | recommendation';

comment on column public.feedback_events.action is
    'thumbs_up | thumbs_down | save | dismiss | open';

comment on column public.feedback_events.reasons is
    'JSON array of reason strings selected by the user.';

comment on column public.feedback_events.meta is
    'Snapshot metadata: title, url, topic_name, source, model, prompt_version, etc.';

