-- Single-row status of the scheduled (all-groups) fetch, so a silent
-- failure (RSS format change, translation API down, etc.) is visible
-- on the site instead of only in GitHub Actions history.
create table if not exists fetch_status (
  id int primary key default 1,
  last_run_at timestamptz,
  last_run_ok boolean,
  last_error text,
  constraint fetch_status_singleton check (id = 1)
);
insert into fetch_status (id) values (1) on conflict (id) do nothing;

alter table fetch_status enable row level security;
create policy "public read fetch_status" on fetch_status for select using (true);

-- Publisher name parsed from the article title (e.g. "Forbes",
-- "YouTube", "Soompi") -- used by the frontend to color-code articles
-- by source reliability.
alter table articles add column if not exists publisher text;
