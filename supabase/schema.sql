-- Groups being tracked. Adding a new group later = one INSERT here,
-- no code changes or redeploy needed.
create table if not exists groups (
  key text primary key,               -- url slug, e.g. 'le-sserafim'
  display_name text not null,         -- e.g. 'LE SSERAFIM'
  search_patterns jsonb not null,     -- array of strings matched against titles
  is_regex boolean not null default false,
  created_at timestamptz not null default now()
);

-- One row per article. History accumulates indefinitely (cheap at this
-- scale) so date-range search just works with no separate archive.
create table if not exists articles (
  id bigint generated always as identity primary key,
  group_key text not null references groups(key) on delete cascade,
  source text not null,               -- 'soompi' | 'google_news' | 'bing_news' | ...
  title text not null,
  url text not null,
  published_at timestamptz not null,
  fetched_at timestamptz not null default now(),
  unique (group_key, url)
);

create index if not exists articles_group_published_idx
  on articles (group_key, published_at desc);

alter table groups enable row level security;
alter table articles enable row level security;

-- Site reads are public/anon (no login). Writes are done by the fetch
-- script using the service-role key, which bypasses RLS entirely, so
-- no write policy is needed for the anon/public role.
create policy "public read groups" on groups for select using (true);
create policy "public read articles" on articles for select using (true);
