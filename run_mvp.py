"""VIRALFORGE full pipeline — PLAN.md Sections 5/10, one command.

Steps (each skips gracefully when its inputs are missing):
  M1:  1. API crawl (seeds -> DB)                            [needs API key]
  M3:  2. Top-50 outliers -> data/outliers.json
       3. yt-dlp deep pass (heatmaps/subs/thumbs)            [throttled]
       4. Title + hook classification + hook library export
       5. Heatmap peak/dip mining
       6. Thumbnail mining (OpenCV + EasyOCR)
       7. Topic clustering (TF-IDF + KMeans)
       8. Pacing mining (360p sample, deleted after)         [optional --pacing]
       9. Patterns report + benchmarks.json
  M4: 10. Optional: score one of your rendered videos
  M6: 11. Optional: packaging candidates (3 titles + 3 thumbnails)

Usage:
  python run_mvp.py                          # steps 1-9
  python run_mvp.py --video out/video.mp4 --title "My Title"
  python run_mvp.py --pacing 8               # include pacing sample (slow)
  python run_mvp.py --thumbs                 # thumbnail mining (needs OCR models)
  python run_mvp.py --candidates --topic "McDonald's"   # M6 titles/thumbs
"""
import argparse
import subprocess
import sys

STEPS = [
    ("M1  API crawl (seeds -> DB)", ["-m", "harvester.api_crawl", "--once"]),
    ("M3  Top-50 outliers", ["-m", "miner.outliers", "--top", "50"]),
    ("M3  yt-dlp deep pass (heatmaps/subs/thumbs)", ["-m", "harvester.deep_crawl", "--top", "50"]),
    ("M3  Title + hook classification", ["-m", "miner.titles"]),
    ("M3  Hook library export", ["-m", "miner.hooks", "--export"]),
    ("M3  Heatmap peak/dip mining", ["-m", "miner.heatmaps"]),
    ("M3  Topic clustering", ["-m", "miner.topics"]),
    ("M3  Patterns report + benchmarks", ["-m", "miner.report"]),
]


def run(py: str, args: list[str]) -> bool:
    print(f"\n=== {' '.join(args[1:])} ===", flush=True)
    r = subprocess.run([py, *args])
    if r.returncode != 0:
        print(f"!!! step failed ({r.returncode}); continuing", file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="VIRALFORGE full pipeline")
    ap.add_argument("--video", help="score one of your rendered videos")
    ap.add_argument("--title", help="title candidate to score alongside --video")
    ap.add_argument("--pacing", type=int, default=0, help="include pacing mining on N outliers (slow)")
    ap.add_argument("--thumbs", action="store_true", help="include thumbnail mining (OpenCV+OCR)")
    ap.add_argument("--candidates", action="store_true", help="emit M6 packaging candidates")
    ap.add_argument("--topic", help="topic for --candidates")
    ap.add_argument("--dry", help="M6 loop dry-run: --dry project=... composition=... video=...")
    args = ap.parse_args()

    py = sys.executable
    if args.video:
        run(py, ["-m", "analyzer.score", args.video] + (["--title", args.title] if args.title else []))
        return
    if args.candidates:
        node = subprocess.run(["node", "autofix/candidates.mjs", "--topic", args.topic or "finance story"],
                              shell=False)
        return

    for label, cmd in STEPS:
        print(f"\n########## {label} ##########", flush=True)
        run(py, cmd)
    if args.thumbs:
        run(py, ["-m", "miner.thumbs"])
    if args.pacing:
        run(py, ["-m", "miner.pacing", "--limit", str(args.pacing)])
    run(py, ["-m", "miner.report"])

    print("\nPipeline done. To score your video:  python run_mvp.py --video out/video.mp4 --title \"...\"")


if __name__ == "__main__":
    main()