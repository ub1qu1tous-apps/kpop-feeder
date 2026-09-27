"""
One-off fix: for groups with is_regex=true, member names added by
add_member_names.py went in as plain substrings with no word-boundary
protection -- "Han" (Stray Kids) matched inside "Hands", for example.
Re-wraps each known member name in \\b...\\b (and regex-escapes it)
in place, leaving every other existing pattern (aliases like
"Tomorrow X Together", curated ones like "\\bSKZ\\b") untouched.
"""

import os
import re

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Same names as originally appended by add_member_names.py for these
# is_regex=true groups. "I.N" was already escaped as "I\.N" when added.
MEMBERS = {
    "ive": ["Gaeul", "Yujin", "Rei", "Liz", "Leeseo", "Wonyoung"],
    "stray-kids": ["Bang Chan", "Lee Know", "Changbin", "Hyunjin", "Han", "Felix", "Seungmin", "I.N"],
    "txt": ["Soobin", "Yeonjun", "Beomgyu", "Taehyun", "Huening Kai"],
    "hearts2hearts": ["Carmen", "Jiwoo", "Yuha", "Stella", "Juun", "A-na", "Ian", "Ye-on"],
}


def fetch_group(key):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/groups",
        headers=HEADERS,
        params={"key": f"eq.{key}", "select": "search_patterns"},
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0]["search_patterns"] if rows else None


def update_patterns(key, patterns):
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/groups",
        headers={**HEADERS, "Prefer": "return=minimal"},
        params={"key": f"eq.{key}"},
        json={"search_patterns": patterns},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    for key, members in MEMBERS.items():
        patterns = fetch_group(key)
        if patterns is None:
            print(f"  SKIP {key}: no such group")
            continue

        fixed = []
        changed = 0
        for p in patterns:
            unescaped = p.replace("\\.", ".")  # undo the one-off manual escape on "I.N"
            if unescaped in members:
                new_p = rf"\b{re.escape(unescaped)}\b"
                if new_p != p:
                    changed += 1
                fixed.append(new_p)
            else:
                fixed.append(p)

        update_patterns(key, fixed)
        print(f"  {key}: re-wrapped {changed} member pattern(s)")

    print("Done.")


if __name__ == "__main__":
    main()
