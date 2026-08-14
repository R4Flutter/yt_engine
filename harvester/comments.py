"""M1 comments mining — commentThreads.list for top outliers (PLAN.md Section 5, M1).

Top comments reveal what viewers loved/hated — feature them in future scripts.
1 unit per 50 comments.

Usage:
  python -m harvester.comments --top 5            # top 5 outliers by score
  python -m harvester.comments --video VIDEO_ID
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

from config import api_key, fix_console, load_settings
from db import get_connection

BASE = "https://www.googleapis.com/youtube/v3"


def fetch_comments(key: str, video_id: str, max_results: int = 20) -> list[dict]:
    q = urllib.parse.urlencode({
        "part": "snippet", "videoId": video_id, "maxResults": max_results, "key": key,
    })
    with urllib.request.urlopen(f"{BASE}/commentThreads?{q}", timeout=30) as resp:
        data = json.loads(resp.read())
    out = []
    for i in data.get("items", []):
        sn = i["snippet"]["topLevelComment"]["snippet"]
        out.append({"author": sn.get("authorDisplayName"), "text": sn.get("textDisplay", ""),
                    "likes": int(sn.get("likeCount", 0)), "replies": int(i["snippet"].get("totalReplyCount", 0))})
    return out


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--video", help="specific video id")
    ap.add_argument("--max", type=int, default=15, help="comments per video")
    args = ap.parse_args()
    key = api_key(load_settings())
    if not key:
        print("no API key", file=sys.stderr)
        sys.exit(1)
    conn = get_connection()
    if args.video:
        vids = [args.video]
    else:
        vids = [r["video_id"] for r in conn.execute(
            "SELECT video_id FROM videos WHERE outlier_score >= 5 ORDER BY outlier_score DESC LIMIT ?",
            (args.top,)).fetchall()]
    for vid in vids:
        title = conn.execute("SELECT title FROM videos WHERE video_id=?", (vid,)).fetchone()
        print(f"\n[comments] {vid} — {title['title'][:70] if title else '?'}")
        try:
            for c in fetch_comments(key, vid, args.max)[:args.max]:
                print(f"  +{c['likes']:>4}  {c['text'][:110]}")
        except urllib.error.HTTPError as e:
            print(f"  (comments disabled or error {e.code})")
        time.sleep(0.3)


if __name__ == "__main__":
    main()