"""M1 Harvester â€” YouTube Data API crawl (PLAN.md Section 5, M1).

Usage:
  python -m harvester.api_crawl --once         # full crawl (resolve + uploads + stats)
  python -m harvester.api_crawl --resolve-only # just resolve seed handles -> channels
  python -m harvester.api_crawl --snapshots    # snapshot poll for videos < 7 days old

Requires a YouTube Data API v3 key:
  $env:YOUTUBE_API_KEY="..."   (or set api.key in config/settings.yaml)
"""
import argparse
import datetime as dt
import json
import sys
import time
from statistics import median

import requests

from config import ROOT, api_key, fix_console, load_seeds, load_settings, resolve_path
from db import get_connection, init_db

API = "https://www.googleapis.com/youtube/v3"

UNITS = {"channels": 1, "playlistItems": 1, "videos": 1, "search": 100}


def _get(session, path, params, settings, attempts=3):
    key = api_key(settings)
    params = dict(params, key=key)
    for a in range(attempts):
        r = session.get(f"{API}/{path}", params=params, timeout=30)
        if r.status_code == 403 and a < attempts - 1:
            print(f"  [retry] {path} 403, backing off", file=sys.stderr)
            time.sleep(5 * (a + 1))
            continue
        r.raise_for_status()
        return r.json()


def resolve_channels(conn, session, settings, seeds):
    """channels?forHandle= per seed; inserts rows into channels."""
    by_handle = [s for s in seeds if s.get("handle")]
    by_id = [s for s in seeds if s.get("channel_id")]
    ids = [(s["channel_id"], None) for s in by_id]
    for seed in by_handle:
        items = _get(
            session,
            "channels",
            {"part": "contentDetails,snippet,statistics", "forHandle": seed["handle"], "maxResults": 1},
            settings,
        ).get("items", [])
        ids.append((items[0]["id"], seed["handle"]) if items else (None, seed["handle"]))
    print(f"[resolve] {len(ids)} candidate channels")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    n = 0
    for cid, handle in ids:
        if not cid:
            print(f"  [resolve] FAILED to resolve {handle} â€” paste its channel_id into config/seeds.yaml")
            continue
        seed = next((s for s in seeds if s.get("handle") == handle), {})
        ch = _get(
            session,
            "channels",
            {"part": "contentDetails,snippet,statistics", "id": cid, "maxResults": 1},
            settings,
        ).get("items", [{}])[0]
        stats = ch.get("statistics", {})
        conn.execute(
            """INSERT INTO channels (channel_id, title, subs, total_views, video_count,
                                    country, niche_tag, uploads_playlist, last_crawled)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(channel_id) DO UPDATE SET
                 title=excluded.title, subs=excluded.subs, total_views=excluded.total_views,
                 video_count=excluded.video_count, country=excluded.country,
                 niche_tag=COALESCE(channels.niche_tag, excluded.niche_tag),
                 uploads_playlist=excluded.uploads_playlist,
                 last_crawled=excluded.last_crawled""",
            (
                cid,
                ch.get("snippet", {}).get("title"),
                int(stats.get("subscriberCount", 0)),
                int(stats.get("viewCount", 0)),
                int(stats.get("videoCount", 0)),
                ch.get("snippet", {}).get("country"),
                seed.get("niche"),
                ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
                now,
            ),
        )
        n += 1
    conn.commit()
    return n


def crawl_uploads(conn, session, settings, channel_id, niche_tag):
    """playlistItems on the channel's uploads playlist -> newest video ids."""
    items, page = [], None
    playlist_id = conn.execute(
        "SELECT uploads_playlist FROM channels WHERE channel_id=?", (channel_id,)
    ).fetchone()["uploads_playlist"]
    if not playlist_id:
        playlist_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else "UU" + channel_id
    while True:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, settings["crawl"]["playlist_max_results"]),
        }
        if page:
            params["pageToken"] = page
        try:
            data = _get(session, "playlistItems", params, settings)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  [warn] uploads playlist not found for {channel_id}; skipping", file=sys.stderr)
                return []
            raise
        items += data.get("items", [])
        page = data.get("nextPageToken")
        if not page or len(items) >= settings["crawl"]["playlist_max_results"]:
            break
    return [i["contentDetails"]["videoId"] for i in items]


def fetch_stats(conn, session, settings, video_ids):
    """videos.list stats+snippet in batches of 50 (1 unit per batch)."""
    B = settings["api"]["max_videos_per_call"]
    for i in range(0, len(video_ids), B):
        batch = video_ids[i : i + B]
        data = _get(
            session,
            "videos",
            {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(batch),
                "maxResults": B,
            },
            settings,
        )
        for v in data.get("items", []):
            yield v


def iso_to_dur(dur: str) -> int:
    """PT1H2M3S -> seconds."""
    if not dur:
        return 0
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def upsert_videos(conn, session, settings, videos, crawled_at):
    rows = [dict(v) for v in videos]
    if rows:
        conn.executemany(
            """INSERT INTO videos (video_id, channel_id, title, description, published_at,
                                  duration_sec, is_short, category_id, tags_json,
                                  views, likes, comments, crawled_at)
               VALUES (:video_id, :channel_id, :title, :description, :published_at,
                       :duration_sec, :is_short, :category_id, :tags_json,
                       :views, :likes, :comments, :crawled_at)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title, description=excluded.description,
                 published_at=excluded.published_at, duration_sec=excluded.duration_sec,
                 is_short=excluded.is_short, category_id=excluded.category_id,
                 tags_json=excluded.tags_json, views=excluded.views,
                 likes=excluded.likes, comments=excluded.comments,
                 crawled_at=excluded.crawled_at""",
            rows,
        )


def compute_outliers(conn):
    """outlier_score = views / channel median of last-30-upload views (PLAN M3.1)."""
    chans = conn.execute("SELECT channel_id FROM channels").fetchall()
    for c in chans:
        ch = c["channel_id"]
        recent = conn.execute(
            """SELECT views FROM videos WHERE channel_id=? AND views IS NOT NULL
               ORDER BY published_at DESC LIMIT 30""",
            (ch,),
        ).fetchall()
        if not recent:
            continue
        med = median(v["views"] for v in recent)
        conn.execute("UPDATE channels SET median_views_30=? WHERE channel_id=?", (med, ch))
        conn.execute(
            """UPDATE videos SET outlier_score=ROUND(views*1.0/?, 2) WHERE channel_id=?""",
            (med, ch),
        )
    conn.commit()


def snapshot_recent(conn, settings):
    """Append-only views snapshots for videos published within the window (velocity)."""
    window = dt.timedelta(days=settings["crawl"]["snapshot_window_days"])
    min_interval = dt.timedelta(hours=settings["crawl"]["snapshot_min_interval_h"])
    cutoff = (dt.datetime.now(dt.timezone.utc) - window).isoformat()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = conn.execute(
        """SELECT video_id, views, likes, comments FROM videos
           WHERE published_at > ?""",
        (cutoff,),
    ).fetchall()
    n = 0
    for v in rows:
        last = conn.execute(
            "SELECT captured_at FROM snapshots WHERE video_id=? ORDER BY captured_at DESC LIMIT 1",
            (v["video_id"],),
        ).fetchone()
        if last and (dt.datetime.fromisoformat(now) - dt.datetime.fromisoformat(last["captured_at"])) < min_interval:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?)",
            (v["video_id"], now, v["views"], v["likes"], v["comments"]),
        )
        n += 1
    conn.commit()
    return n


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M1 harvester")
    ap.add_argument("--once", action="store_true", help="full crawl")
    ap.add_argument("--resolve-only", action="store_true")
    ap.add_argument("--snapshots", action="store_true")
    args = ap.parse_args()

    settings = load_settings()
    key = api_key(settings)
    if not key:
        print(
            "ERROR: no YouTube API key.\n"
            'Set it:  $env:YOUTUBE_API_KEY="your-key"\n'
            "Get one free: console.cloud.google.com -> enable 'YouTube Data API v3' -> Credentials -> API key",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = get_connection()
    init_db(conn)
    session = requests.Session()
    units = 0

    if args.resolve_only or args.once:
        seeds = load_seeds()
        n = resolve_channels(conn, session, settings, seeds)
        units += n + (1 if any(s.get("handle") for s in seeds) else 0)
        print(f"[resolve] {n} channels upserted ({units} units)")

    if args.once:
        # prune channels no longer in seeds (resolved this run have fresh last_crawled)
        stale_before = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        conn.execute("DELETE FROM channels WHERE last_crawled < ?", (stale_before,))
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        channels = conn.execute("SELECT channel_id, niche_tag FROM channels").fetchall()
        total_vids = 0
        for c in channels:
            vids = crawl_uploads(conn, session, settings, c["channel_id"], c["niche_tag"])
            rows = []
            for v in fetch_stats(conn, session, settings, vids):
                sn = v["snippet"]
                dur = iso_to_dur(v.get("contentDetails", {}).get("duration", ""))
                st = v.get("statistics", {})
                rows.append(
                    {
                        "video_id": v["id"],
                        "channel_id": c["channel_id"],
                        "title": sn.get("title", ""),
                        "description": sn.get("description", ""),
                        "published_at": sn.get("publishedAt", ""),
                        "duration_sec": dur,
                        "is_short": 1 if dur <= 180 else 0,
                        "category_id": sn.get("categoryId"),
                        "tags_json": json.dumps(sn.get("tags", []), ensure_ascii=False),
                        "views": int(st.get("viewCount", 0)),
                        "likes": int(st.get("likeCount", 0)),
                        "comments": int(st.get("commentCount", 0)),
                        "crawled_at": now,
                    }
                )
            units += (len(vids) + 49) // 50
            upsert_videos(conn, session, settings, rows, now)
            total_vids += len(rows)
            print(f"  {c['channel_id']}: {len(rows)} videos")
        compute_outliers(conn)
        print(f"[crawl] {total_vids} videos upserted, outliers computed ({units} units total)")

    if args.snapshots:
        n = snapshot_recent(conn, settings)
        print(f"[snapshots] {n} rows appended")

    if not (args.once or args.resolve_only or args.snapshots):
        ap.print_help()


if __name__ == "__main__":
    main()
