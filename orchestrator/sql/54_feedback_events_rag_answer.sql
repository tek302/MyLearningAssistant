-- Extend feedback_events to support RAG answer feedback target type.
-- Safe additive migration for existing alpha environments.

alter table if exists public.feedback_events
  drop constraint if exists feedback_events_target_type_check;

alter table if exists public.feedback_events
  add constraint feedback_events_target_type_check
  check (target_type in ('summary_s1', 'summary_s2', 'recommendation', 'rag_answer'));

comment on table public.feedback_events is
  'User feedback event log for S1/S2 summaries, recommendations, and RAG answers.';
