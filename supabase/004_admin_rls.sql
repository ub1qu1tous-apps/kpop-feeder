-- Lets the logged-in admin edit/delete groups and delete individual
-- articles from the frontend. Anonymous visitors still only get the
-- public read policies already in schema.sql.
create policy "authenticated update groups" on groups
  for update to authenticated using (true) with check (true);

create policy "authenticated delete groups" on groups
  for delete to authenticated using (true);

create policy "authenticated delete articles" on articles
  for delete to authenticated using (true);
