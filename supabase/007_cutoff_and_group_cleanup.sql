-- 007: (1) oldest-article cutoff date, (2) full cleanup when a group is
-- deleted. Safe to run more than once.

-- (1) Articles published before this date are never stored -- matters
-- most when adding a new group, since news search can surface articles
-- years old. Editable by the admin on admin.html.
create table if not exists app_settings (
  id int primary key default 1,
  oldest_article_date date not null default '2026-01-01',
  constraint app_settings_singleton check (id = 1)
);
insert into app_settings (id) values (1) on conflict (id) do nothing;

alter table app_settings enable row level security;
drop policy if exists "public read app_settings" on app_settings;
create policy "public read app_settings" on app_settings for select using (true);
drop policy if exists "authenticated update app_settings" on app_settings;
create policy "authenticated update app_settings" on app_settings
  for update to authenticated using (true) with check (true);

-- (2) Deleting a group already deletes its articles (on delete cascade).
-- This also removes stored article text that no other group uses, so
-- nothing about the group is left behind.
create or replace function cleanup_group_texts() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  delete from article_texts t
  where t.link_key in (
      select link_key from articles where group_key = old.key and link_key is not null
    )
    and not exists (
      select 1 from articles a where a.link_key = t.link_key and a.group_key <> old.key
    );
  return old;
end $$;

drop trigger if exists groups_cleanup_texts on groups;
create trigger groups_cleanup_texts
  before delete on groups
  for each row execute function cleanup_group_texts();
