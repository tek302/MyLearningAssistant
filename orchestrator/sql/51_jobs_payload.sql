-- S2/Recommendations jobs: optional payload (e.g. week_start for s2)
alter table public.jobs add column if not exists payload jsonb;

comment on column public.jobs.payload is 'Optional job payload (e.g. {"week_start": "2025-02-24"} for s2)';
