"""
One-off utility: append each group's member names to its
search_patterns, so Soompi's title-matching also catches articles that
mention a member by name without mentioning the group name itself.
(Google/Bing News matching is unaffected -- those query on display_name
only.) Safe to re-run -- names already present aren't duplicated.
"""

import os

import requests

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Note: for groups with is_regex=true, each pattern is used as a raw
# regex fragment (not auto-escaped), so any regex-special characters in
# a name must be pre-escaped here. Only "I.N" (Stray Kids) needs it --
# the "." would otherwise match any character.
MEMBERS = {
    "illit": ["Yunah", "Minju", "Moka", "Wonhee", "Iroha"],
    "le-sserafim": ["Sakura", "Chaewon", "Yunjin", "Kazuha", "Eunchae"],
    "katseye": ["Daniela", "Lara", "Manon", "Megan", "Sophia", "Yoonchae"],
    "ive": ["Gaeul", "Yujin", "Rei", "Liz", "Leeseo", "Wonyoung"],
    "stray-kids": ["Bang Chan", "Lee Know", "Changbin", "Hyunjin", "Han", "Felix", "Seungmin", "I\\.N"],
    "txt": ["Soobin", "Yeonjun", "Beomgyu", "Taehyun", "Huening Kai"],
    "hearts2hearts": ["Carmen", "Jiwoo", "Yuha", "Stella", "Juun", "A-na", "Ian", "Ye-on"],
    "babymonster": ["Ruka", "Pharita", "Asa", "Ahyeon", "Rami", "Rora", "Chiquita"],
    "nmixx": ["Lily", "Haewon", "Sullyoon", "Bae", "Jiwoo", "Kyujin"],
    "aespa": ["Karina", "Giselle", "Winter", "Ningning"],
    "twice": ["Nayeon", "Jeongyeon", "Momo", "Sana", "Jihyo", "Mina", "Dahyun", "Chaeyoung", "Tzuyu"],
    "itzy": ["Yeji", "Lia", "Ryujin", "Chaeryeong", "Yuna"],
}


def fetch_groups():
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/groups", headers=HEADERS, params={"select": "*"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


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
    groups = {g["key"]: g for g in fetch_groups()}

    for key, members in MEMBERS.items():
        group = groups.get(key)
        if not group:
            print(f"  SKIP {key}: no such group in database")
            continue

        existing = group["search_patterns"] or []
        existing_lower = {p.lower() for p in existing}
        new_members = [m for m in members if m.lower() not in existing_lower]

        if not new_members:
            print(f"  {key}: already up to date")
            continue

        updated = existing + new_members
        update_patterns(key, updated)
        print(f"  {key}: added {new_members}")

    print("Done.")


if __name__ == "__main__":
    main()
