-- Tracks when a group was last manually refreshed, so the per-group
-- "Refresh" button can enforce a cooldown and show "last updated".
alter table groups add column if not exists last_refreshed_at timestamptz;

-- Lets the logged-in admin (a single Supabase Auth account, no public
-- sign-up) add new groups from the frontend. Anonymous visitors still
-- only get the "public read" policies already in schema.sql.
create policy "authenticated insert groups" on groups
  for insert to authenticated
  with check (true);
