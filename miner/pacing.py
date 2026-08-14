"""M3 pacing mining (PLAN.md Section 5, M3 step 5).

Downloads a 360p sample of outlier videos, runs scene detection,
stores cuts_per_min / avg_shot_sec into video_features, then deletes
the downloads (analysis-only copies, no redistribution).

Usage:
  python -m miner.pacing --limit 8        # process up to 8 outliers
  python -m miner.pacing --limit 8 --force  # re-process already-measured
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import ROOT, fix_console, load_settings
from db import get_connection
from analyzer.media import scenes as detect_scenes


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    settings = load_settings()
    conn = get_connection()

    rows = conn.execute(
        """SELECT v.video_id, v.outlier_score
           FROM videos v LEFT JOIN video_features vf ON vf.video_id = v.video_id
           WHERE v.outlier_score >= 5 AND v.duration_sec BETWEEN 120 AND 3600
             AND (? OR vf.cuts_per_min IS NULL)
           ORDER BY v.outlier_score DESC LIMIT ?""",
        (1 if args.force else 0, args.limit),
    ).fetchall()
    if not rows:
        print("[pacing] no unmeasured outliers to sample")
        return

    tmp = Path(tempfile.mkdtemp(prefix="vf_pacing_"))
    done = 0
    try:
        for r in rows:
            out = tmp / f"{r['video_id']}.%(ext)s"
            url = f"https://www.youtube.com/watch?v={r['video_id']}"
            print(f"[pacing] downloading 360p {r['video_id']} (score {r['outlier_score']:.1f}x)...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "yt_dlp",
                     "--js-runtimes", "node", "--remote-components", "ejs:github",
                     "-f", "bv*[height<=360]+ba/b[height<=360]",
                     "--sleep-requests", "2", "--retries", "3", "-o", str(out), url],
                    check=True, capture_output=True, timeout=900,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                tail = (e.stdout or b"")[-400:] if isinstance(getattr(e, "stdout", None), bytes) else str(getattr(e, "stdout", ""))[-400:]
                print(f"  [pacing] download failed: {e}\n{tail}")
                continue
            if not out.exists():
                matches = list(tmp.glob(f"{r['video_id']}.*"))
                if not matches:
                    continue
                out = matches[0]
            cuts = detect_scenes(str(out))
            if cuts and cuts.get("cuts_per_min", 0) > 0:
                conn.execute(
                    """INSERT INTO video_features (video_id, cuts_per_min, avg_shot_sec)
                       VALUES (?, ?, ?)
                       ON CONFLICT(video_id) DO UPDATE SET
                         cuts_per_min=excluded.cuts_per_min, avg_shot_sec=excluded.avg_shot_sec""",
                    (r["video_id"], cuts["cuts_per_min"], cuts["longest_static_shot"]),
                )
                conn.commit()
                print(f"  [pacing] {r['video_id']}: {cuts['cuts_per_min']} cuts/min, "
                      f"longest static shot {cuts['longest_static_shot']}s")
                done += 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    med = conn.execute(
        """SELECT AVG(cuts_per_min), AVG(avg_shot_sec) FROM video_features WHERE cuts_per_min IS NOT NULL"""
    ).fetchone()
    print(f"[pacing] done {done}; median cuts/min={med[0]:.1f}, longest static shot={med[1]:.1f}s" if med[0] else
          "[pacing] no cuts measured")


if __name__ == "__main__":
    main()