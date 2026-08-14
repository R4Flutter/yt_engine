"""M1 Harvester â€” yt-dlp deep pass (PLAN.md Section 5, M1).

Pulls info JSON (with the `heatmap` "Most Replayed" retention curve), auto-subs,
and thumbnails for outlier videos. Runs from your home IP, throttled.

Usage:
  python -m harvester.deep_crawl --top 50        # deep-crawl top outliers
  python -m harvester.deep_crawl --video VIDEO_ID
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from config import fix_console, load_settings, resolve_path
from db import get_connection, init_db

YTDlp = [sys.executable, "-m", "yt_dlp"]


def ytdlp(info_json_path: str, video_id: str, settings: dict) -> None:
    cmd = [
        *YTDlp,
        "--skip-download",
        "--write-info-json",
        "--write-thumbnail",
        "--write-auto-subs",
        "--sub-langs", settings["deep_crawl"]["sub_lang"],
        "--sub-format", "vtt",
        "--sleep-requests", str(settings["deep_crawl"]["sleep_requests"]),
        "--retries", "5",
        "-o", info_json_path,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    cookies = settings["deep_crawl"].get("cookies_from_browser")
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [deep] yt-dlp failed for {video_id}:\n{r.stderr[:500]}", file=sys.stderr)


def _ts_sec(ts: str) -> float:
    h, mi, s, ms = (int(g) for g in re.match(r"(\d+):(\d+):(\d+)\.(\d+)", ts).groups())
    return h * 3600 + mi * 60 + s + ms / 1000.0


def parse_vtt(vtt: str) -> list[dict]:
    """Parse YouTube auto-sub VTT -> word list. YouTube emits each cue twice
    (word-tagged + plain-text) and re-emits previous words at cue boundaries;
    only tag-bearing lines are real content, and consecutive duplicates drop."""
    words, cue_start = [], None
    for line in vtt.splitlines():
        if "-->" in line:
            cue_start = _ts_sec(line)
        elif cue_start is not None and "<" in line and line.strip() \
                and not line.startswith(("WEBVTT", "Kind:", "Language:")):
            ts = cue_start
            for token in re.split(r"(<[^>]*>)", line):
                m = re.fullmatch(r"<(\d{2}:\d{2}:\d{2}\.\d{3})>", token)
                if m:
                    ts = _ts_sec(m.group(1))
                elif token.strip() and not token.startswith("<"):
                    w = token.strip()
                    if w and not (words and words[-1]["text"] == w):
                        words.append({"start": round(ts, 2), "text": w})
    return words


def store(video_id: str, raw_dir: Path, thumbs_dir: Path, conn) -> None:
    files = list(raw_dir.glob(f"{video_id}.*"))
    info = next((f for f in files if f.suffix == ".json"), None)
    vtt = next((f for f in files if f.suffix == ".vtt"), None)
    if not info:
        return
    data = json.loads(info.read_text(encoding="utf-8"))
    heat = data.get("heatmap") or []
    if heat:
        conn.execute(
            "INSERT OR REPLACE INTO heatmaps (video_id, points_json) VALUES (?,?)",
            (video_id, json.dumps(heat)),
        )
    if vtt:
        words = parse_vtt(vtt.read_text(encoding="utf-8", errors="ignore"))
        full = " ".join(w["text"] for w in words)
        hook = " ".join(w["text"] for w in words if w["start"] < 30)
        conn.execute(
            """INSERT OR REPLACE INTO transcripts (video_id, full_text, hook_text, words_json, source)
               VALUES (?,?,?,?,?)""",
            (video_id, full, hook, json.dumps(words), "auto_subs"),
        )
    if data.get("thumbnail"):
        thumb = next((f for f in files if f.suffix in (".jpg", ".webp", ".png", ".jpeg")), None)
        if thumb:
            dest = thumbs_dir / f"{video_id}{thumb.suffix}"
            if not dest.exists():
                dest.write_bytes(thumb.read_bytes())
            conn.execute("UPDATE videos SET thumb_path=? WHERE video_id=?", (str(dest), video_id))
    conn.commit()


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M1 yt-dlp deep pass")
    ap.add_argument("--top", type=int, help="deep-crawl the N highest-scoring outliers")
    ap.add_argument("--video", help="deep-crawl a single video ID")
    args = ap.parse_args()

    settings = load_settings()
    raw_dir = resolve_path(settings["paths"]["raw"])
    thumbs_dir = resolve_path(settings["paths"]["thumbs"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)

    if args.video:
        targets = [args.video]
    elif args.top:
        # Guarded by channel size: outlier_score is views/channel-median, so a
        # mis-resolved handle pointing at a 48-subscriber channel manufactures
        # scores in the 60s and would soak up hours of this crawl. Skipping
        # videos already carrying a heatmap makes reruns resumable.
        rows = conn.execute(
            """SELECT v.video_id FROM videos v JOIN channels c USING(channel_id)
               WHERE v.outlier_score IS NOT NULL AND v.views >= ?
                 AND COALESCE(c.subs, 0) >= ?
                 AND v.video_id NOT IN (SELECT video_id FROM heatmaps)
               ORDER BY v.outlier_score DESC LIMIT ?""",
            (settings["outliers"]["min_views"],
             settings["outliers"].get("min_channel_subs", 0), args.top),
        ).fetchall()
        targets = [r["video_id"] for r in rows]
    else:
        ap.print_help()
        return

    done = {r["video_id"] for r in conn.execute("SELECT video_id FROM heatmaps").fetchall()}
    for vid in targets:
        if vid in done:
            print(f"  [deep] {vid}: already done, skipping")
            continue
        print(f"  [deep] {vid}")
        ytdlp(str(raw_dir / f"{vid}.%(ext)s"), vid, settings)
        store(vid, raw_dir, thumbs_dir, conn)
    print(f"[deep] finished {len(targets)} videos")


if __name__ == "__main__":
    main()
