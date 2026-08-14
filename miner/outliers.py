"""M3 Miner â€” outlier detection (PLAN.md Section 5, M3.1).

Usage:
  python -m miner.outliers --top 50              # table + data/outliers.json
  python -m miner.outliers --top 50 --json out.json
"""
import argparse
import json

from config import fix_console, load_settings, resolve_path
from db import get_connection, init_db


def top_outliers(conn, top: int, min_views: int, min_subs: int = 0):
    """Top outliers, guarded against mis-resolved channels.

    outlier_score is views / channel median, so a channel with a tiny median
    manufactures enormous scores from nothing: a mis-resolved handle pointing at
    a 48-subscriber channel (median 187 views) scored a 12,832-view video at
    68.6, above a genuine 2.8M-view outlier. Because deep_crawl walks this same
    ordering, an unguarded score does not just skew a report -- it spends hours
    of crawl budget on junk. min_subs is the cheap structural guard.
    """
    return conn.execute(
        """SELECT v.video_id, v.title, v.views, v.outlier_score, v.published_at,
                  c.title AS channel, c.subs, c.niche_tag
           FROM videos v JOIN channels c ON c.channel_id = v.channel_id
           WHERE v.outlier_score IS NOT NULL AND v.views >= ?
             AND COALESCE(c.subs, 0) >= ?
           ORDER BY v.outlier_score DESC LIMIT ?""",
        (min_views, min_subs, top),
    ).fetchall()


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M3 top outliers")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--json", help="also write JSON export path (default data/outliers.json)")
    args = ap.parse_args()

    settings = load_settings()
    conn = get_connection()
    init_db(conn)
    rows = top_outliers(conn, args.top, settings["outliers"]["min_views"],
                        settings["outliers"].get("min_channel_subs", 0))
    print(f"{'#':>3} {'score':>6} {'views':>10}  {'channel':<26} title")
    out = []
    for i, r in enumerate(rows, 1):
        print(f"{i:>3} {r['outlier_score']:>6.1f} {r['views']:>10,}  {r['channel'][:25]:<26} {r['title'][:60]}")
        out.append(dict(r))
    dest = resolve_path(args.json or "data/outliers.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[outliers] {len(out)} written to {dest}")


if __name__ == "__main__":
    main()
