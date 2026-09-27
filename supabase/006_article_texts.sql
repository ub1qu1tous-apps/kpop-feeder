-- 006: full article text, for keyword search and for filing an article
-- under every group whose name appears in it.
--
-- article_texts holds each article's text ONCE, keyed by link_key (the
-- real publisher link, or the stable Google News link), no matter how
-- many groups the article is filed under. A row here also means "already
-- read" -- the fetch job never reads the same link twice.

create table if not exists article_texts (
  link_key text primary key,
  resolved_url text,
  status text not null check (status in ('text', 'summary', 'failed')),
  body text,                       -- full article text (status = 'text')
  summary text,                    -- short description, fallback for search
  read_at timestamptz not null default now()
);

alter table article_texts enable row level security;
drop policy if exists "public read article_texts" on article_texts;
create policy "public read article_texts" on article_texts for select using (true);
grant select on article_texts to anon, authenticated;

alter table articles add column if not exists link_key text;
-- true = filed here because the group is named in the article text
-- (not in the title / not from this group's own news search)
alter table articles add column if not exists via_text boolean not null default false;
create index if not exists articles_link_key_idx on articles (link_key);

-- What the group page queries: every article plus one searchable blob of
-- title + summary + full text. security_invoker so the normal public-read
-- policies on both tables apply.
create or replace view articles_search with (security_invoker = true) as
select
  a.id, a.group_key, a.source, a.title, a.url, a.publisher,
  a.published_at, a.fetched_at, a.link_key, a.via_text,
  a.title || ' ' || coalesce(t.summary, '') || ' ' || coalesce(t.body, '') as search_text
from articles a
left join article_texts t on t.link_key = a.link_key;

grant select on articles_search to anon, authenticated;
