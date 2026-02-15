-- Week5: extend sources with source_type, status, pages, size_mb, char_count, fail_code

alter table sources add column if not exists source_type text;
alter table sources add column if not exists status text default 'pending';
alter table sources add column if not exists pages int;
alter table sources add column if not exists size_mb real;
alter table sources add column if not exists char_count int;
alter table sources add column if not exists fail_code text;

create index if not exists idx_sources_user_created on sources(user_id, created_at desc);
