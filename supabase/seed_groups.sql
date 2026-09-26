insert into groups (key, display_name, search_patterns, is_regex) values
  ('illit', 'ILLIT', '["ILLIT"]', false),
  ('le-sserafim', 'LE SSERAFIM', '["LE SSERAFIM", "LE-SSERAFIM", "LESSERAFIM"]', false),
  ('katseye', 'KATSEYE', '["KATSEYE"]', false),
  ('ive', 'IVE', '["\\bIVE\\b"]', true),
  ('stray-kids', 'Stray Kids', '["Stray Kids", "\\bSKZ\\b"]', true),
  ('txt', 'TXT', '["Tomorrow X Together", "\\bTXT\\b"]', true),
  ('hearts2hearts', 'Hearts2Hearts', '["Hearts2Hearts", "Hearts 2 Hearts", "\\bH:TS\\b"]', true),
  ('babymonster', 'BABYMONSTER', '["BABYMONSTER", "Baby Monster"]', false)
on conflict (key) do nothing;
