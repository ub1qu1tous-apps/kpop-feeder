-- Separate from search_patterns (which mixes in aliases/regex helpers
-- used only for matching, e.g. "\bTXT\b", "Tomorrow X Together"). This
-- column is purely the clean member list for display beside the name.
alter table groups add column if not exists members jsonb;
