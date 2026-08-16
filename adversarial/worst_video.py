"""Generate an intentionally terrible video for analyzer stress testing.

The output is a 45-second, 1080x1920 black video with no narration, no music,
no cuts, no text, and no visual information. It is deliberately not a useful
video; it exists to prove that the QC stack rejects pathological renders.

Usage:
  python adversarial/worst_video.py
  python -m analyzer.score adversarial/worst_video.mp4 --assume-voice
"""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "adversarial" / "worst_video.mp4"

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg:
    raise SystemExit("ffmpeg is required")

cmd = [
    ffmpeg, "-y",
    "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30",
    "-t", "45",
    "-an",
    "-c:v", "libx264", "-pix_fmt", "yuv420p",
    str(OUT),
]
subprocess.run(cmd, check=True)
print(f"WROTE {OUT}")
