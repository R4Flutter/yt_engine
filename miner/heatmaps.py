"""M3 heatmap mining (PLAN.md Section 5, M3 step 4).

For every outlier with a yt-dlp "Most Replayed" curve:
  - normalize to 100 buckets
  - detect peaks (money moments) and dips (interest killers)
  - store peak_moments_json / dip_moments_json back into heatmaps
  - print an aggregated view: where do outlier viewers replay / drop off?

Usage:
  python -m miner.heatmaps            # full pass
  python -m miner.heatmaps --top 5    # show top 5 peak moments per video
"""
import argparse
import json
import sys

from config import fix_console
from db import get_connection

N_BUCKETS = 100
SMOOTH = 5


def normalize(points: list[dict], n: int = N_BUCKETS) -> list[float]:
    """Resample variable-length heat curve to n buckets, 0..1 values."""
    if not points:
        return []
    out = []
    for i in range(n):
        idx = min(int(i * len(points) / n), len(points) - 1)
        out.append(float(points[idx].get("value", 0)))
    return out


def smooth(curve: list[float], k: int = SMOOTH) -> list[float]:
    """Moving average to kill single-bucket noise."""
    if len(curve) < k:
        return curve
    return [sum(curve[max(0, i - k // 2): min(len(curve), i + k // 2 + 1)])
            / (min(len(curve), i + k // 2 + 1) - max(0, i - k // 2))
            for i in range(len(curve))]


def peaks_dips(curve: list[float], n: int = 3) -> tuple[list[dict], list[dict]]:
    """Local extrema ranked by magnitude; positions as 0..1 normalized time."""
    s = smooth(curve)
    peaks, dips = [], []
    for i in range(1, len(s) - 1):
        if s[i] > s[i - 1] and s[i] >= s[i + 1]:
            peaks.append({"t": round(i / len(s), 3), "v": round(s[i], 3)})
        if s[i] < s[i - 1] and s[i] <= s[i + 1]:
            dips.append({"t": round(i / len(s), 3), "v": round(s[i], 3)})
    peaks.sort(key=lambda p: -p["v"])
    dips.sort(key=lambda p: p["v"])
    return peaks[:n], dips[:n]


def mine(conn, top: int = 0):
    rows = conn.execute(
        """SELECT h.video_id, v.title, v.outlier_score, h.points_json
           FROM heatmaps h JOIN videos v ON v.video_id = h.video_id
           WHERE v.outlier_score >= 5"""
    ).fetchall()
    if not rows:
        print("[heatmaps] no outlier heatmaps — run deep_crawl first")
        return

    curves, per_video = [], []
    for r in rows:
        try:
            pts = json.loads(r["points_json"])
            if not isinstance(pts, list) or len(pts) < 20:
                continue
        except (TypeError, ValueError):
            continue
        curve = normalize(pts)
        p, d = peaks_dips(curve)
        conn.execute(
            "UPDATE heatmaps SET peak_moments_json=?, dip_moments_json=? WHERE video_id=?",
            (json.dumps(p), json.dumps(d), r["video_id"]),
        )
        curves.append(curve)
        per_video.append((r["video_id"], r["title"], r["outlier_score"], p, d))
    conn.commit()

    avg = [sum(c[i] for c in curves) / len(curves) for i in range(N_BUCKETS)]
    p, d = peaks_dips(avg)
    print(f"[heatmaps] {len(per_video)} outlier curves analyzed")
    print(f"[heatmaps] aggregate peak at {int(p[0]['t']*100)}% of video (v={p[0]['v']}), "
          f"dip at {int(d[0]['t']*100)}% (v={d[0]['v']})")
    print(f"[heatmaps] top peaks: " + ", ".join(f"{int(x['t']*100)}%" for x in p))
    print(f"[heatmaps] top dips:   " + ", ".join(f"{int(x['t']*100)}%" for x in d))
    if top:
        for vid, title, score, p_, d_ in sorted(per_video, key=lambda x: -x[2])[:top]:
            ps = ", ".join(f"{int(x['t']*100)}%({x['v']})" for x in p_)
            ds = ", ".join(f"{int(x['t']*100)}%" for x in d_)
            print(f"  {title[:60]:60s} score {score:6.1f}x  peaks: {ps}  dips: {ds}")


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=0, help="print top N outlier per-video peaks")
    args = ap.parse_args()
    mine(get_connection(), top=args.top)


if __name__ == "__main__":
    main()