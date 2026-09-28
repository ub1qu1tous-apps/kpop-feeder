-- 008: public feedback / group-request board, linked from the top of the
-- main page. Anonymous, no accounts -- anyone can post and everyone sees
-- the same public list. Admin (on admin.html) can mark an entry Done or
-- delete it. Safe to run more than once.

create table if not exists feedback (
  id bigint generated always as identity primary key,
  message text not null check (char_length(message) between 1 and 2000),
  status text not null default 'open' check (status in ('open', 'done')),
  created_at timestamptz not null default now()
);

alter table feedback enable row level security;

drop policy if exists "public read feedback" on feedback;
create policy "public read feedback" on feedback for select using (true);

-- Anonymous visitors can post, but only ever as a fresh "open" entry --
-- they can't set status directly.
drop policy if exists "public insert feedback" on feedback;
create policy "public insert feedback" on feedback
  for insert with check (status = 'open');

drop policy if exists "authenticated update feedback" on feedback;
create policy "authenticated update feedback" on feedback
  for update to authenticated using (true) with check (true);

drop policy if exists "authenticated delete feedback" on feedback;
create policy "authenticated delete feedback" on feedback
  for delete to authenticated using (true);

-- Keep at most 20 entries: after each insert, drop everything past the
-- 20 most recent. Runs as the table owner so it can delete rows the
-- anonymous inserter itself has no delete permission on.
create or replace function enforce_feedback_limit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  delete from feedback
  where id in (
    select id from feedback order by created_at desc, id desc offset 20
  );
  return null;
end $$;

drop trigger if exists feedback_limit on feedback;
create trigger feedback_limit
  after insert on feedback
  for each statement execute function enforce_feedback_limit();
