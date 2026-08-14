"""M1 discovery — search.list for new finance channels (PLAN.md Section 5, M1).

search.list costs 100 units per call, so it runs ONCE per day max.
Finds channels by niche keywords; prints candidates for manual approval
(you add the good ones to config/seeds.yaml yourself).

Usage:
  python -m harvester.discovery --keywords "business documentary channel" "money stories"
  python -m harvester.discovery --limit 15
"""
import argparse
import sys
import time

from config import api_key, fix_console, load_settings
from db import get_connection

BASE = "https://www.googleapis.com/youtube/v3"


def http_get(url, params):
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def search_channels(key: str, keyword: str, limit: int) -> list[dict]:
    import json
    raw = http_get(f"{BASE}/search", {
        "part": "snippet", "type": "channel", "q": keyword,
        "regionCode": "US", "relevanceLanguage": "en",
        "maxResults": min(limit, 50), "key": key,
    })
    data = json.loads(raw)
    return [{"id": i["snippet"].get("channelId"),
             "title": i["snippet"]["title"],
             "subs": None} for i in data.get("items", [])]


def enrich_channels(key: str, ids: list[str]) -> dict:
    import json
    if not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        raw = http_get(f"{BASE}/channels", {
            "part": "snippet,statistics", "id": ",".join(batch), "key": key,
        })
        for c in json.loads(raw).get("items", []):
            st = c["statistics"]
            out[c["id"]] = {"title": c["snippet"]["title"], "subs": int(st.get("subscriberCount", 0)),
                            "total_views": int(st.get("viewCount", 0)),
                            "video_count": int(st.get("videoCount", 0))}
        time.sleep(0.2)
    return out


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keywords", nargs="+", default=["business documentary", "finance explained", "scam investigation"])
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    key = api_key(load_settings())
    if not key:
        print("no API key (config.api_key or YOUTUBE_API_KEY)", file=sys.stderr)
        sys.exit(1)

    seen = {}
    for kw in args.keywords:
        print(f"[discovery] searching '{kw}' ({args.limit} results, 100 units)")
        for c in search_channels(key, kw, args.limit):
            seen.setdefault(c["id"], c)
        time.sleep(0.5)

    ids = list(seen)
    enriched = enrich_channels(key, ids)
    print(f"\n[discovery] {len(ids)} candidate channels (add to config/seeds.yaml if good):")
    for cid, c in seen.items():
        e = enriched.get(cid, {})
        subs = e.get("subs")
        print(f"  {cid}  {c['title'][:40]:40s} subs={subs if subs is not None else '?'}")
    conn = get_connection()
    tracked = {r["channel_id"] for r in conn.execute("SELECT channel_id FROM channels")}
    new = [cid for cid in ids if cid not in tracked]
    print(f"\n[discovery] {len(new)} not already tracked")


if __name__ == "__main__":
    main()