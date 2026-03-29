-- Extend feedback_events action check for exact recommendation action tracking.
-- Adds process/remove actions to avoid KPI proxy estimation.

alter table if exists public.feedback_events
  drop constraint if exists feedback_events_action_check;

alter table if exists public.feedback_events
  add constraint feedback_events_action_check
  check (action in ('thumbs_up', 'thumbs_down', 'save', 'dismiss', 'open', 'process', 'remove'));
