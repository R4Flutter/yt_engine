"""M4 Self-Analyzer â€” media metrics (PLAN.md Section 5, M4).

ffprobe (duration/fps/resolution), PySceneDetect (cuts/min, static shots),
ffmpeg ebur128 (loudness), silence detection. Requires ffmpeg on PATH.

Usage:
  python -m analyzer.media path/to/video.mp4
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from config import fix_console

try:
    from scenedetect import SceneManager, open_video
    from scenedetect.detectors import ContentDetector
    HAVE_SCENEDETECT = True
except ImportError:
    HAVE_SCENEDETECT = False

_WINGET_FFMPEG = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
if not shutil.which("ffmpeg"):
    for p in _WINGET_FFMPEG.glob("*/bin") if _WINGET_FFMPEG.exists() else []:
        os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
        break


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stdout[:800]}")
    return r.stdout


def probe(path: str) -> dict:
    out = json.loads(run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_format", "-show_streams", path]))
    vs = next(s for s in out["streams"] if s["codec_type"] == "video")
    f = out["format"]
    return {
        "duration_sec": float(f.get("duration", 0)),
        "fps": eval(vs.get("avg_frame_rate", "0/1")) if "/" in vs.get("avg_frame_rate", "") else float(vs.get("avg_frame_rate", 0)),
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "bitrate_kbps": int(f.get("bit_rate", 0)) // 1000,
        "audio": any(s["codec_type"] == "audio" for s in out["streams"]),
    }


def loudness(path: str) -> dict:
    out = run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128=peak=true",
               "-f", "null", "-"])
    vals = {}
    i_val = None
    for line in out.splitlines():
        m = line.find("I: ")
        if m >= 0:
            seg = line[m + 3:].strip()
            i_val = float(seg.split()[0])
    if i_val is not None:
        vals["integrated_lufs"] = i_val
    for line in reversed(out.splitlines()):
        if "Summary:" in line:
            break
        if line.strip().startswith("Peak:"):
            vals["true_peak"] = float(line.split("Peak:")[1].strip().split()[0])
            break
    return vals


def scenes(path: str) -> dict:
    if not HAVE_SCENEDETECT:
        print("[media] PySceneDetect not installed; scene metrics skipped", file=sys.stderr)
        return {}
    video = open_video(path)
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=27.0))
    sm.detect_scenes(video=video, show_progress=False)
    scene_list = sm.get_scene_list()
    start_times = sorted(s.get_seconds() for s, _ in scene_list)
    end_times = sorted(e.get_seconds() for _, e in scene_list)
    shots = list(zip(start_times, end_times))
    duration = end_times[-1] if end_times else float(video.duration.get_seconds())
    if not shots:
        return {"cuts": 0, "cuts_per_min": 0.0, "longest_static_shot": round(duration, 2), "shot_lengths": []}
    lengths = [e - s for s, e in shots]
    return {
        "cuts": len(shots),
        "cuts_per_min": round(len(shots) / max(duration, 1) * 60, 2),
        "longest_static_shot": round(max(lengths), 2),
        "shot_lengths": [round(l, 2) for l in lengths],
    }


def silences(path: str, max_silence_sec: float) -> list[dict]:
    out = run(["ffmpeg", "-hide_banner", "-i", path, "-af",
               f"silencedetect=noise=-30dB:d={max_silence_sec}", "-f", "null", "-"])
    sil, cur = [], None
    for line in out.splitlines():
        if "silence_start" in line:
            cur = {"start": float(line.split("silence_start: ")[1].split()[0])}
        elif "silence_end" in line and cur:
            cur["end"] = float(line.split("silence_end: ")[1].split()[0])
            cur["dur"] = cur["end"] - cur["start"]
            sil.append(cur)
            cur = None
    return sil


def analyze(path: str) -> dict:
    p = probe(path)
    p["loudness"] = loudness(path)
    p["scenes"] = scenes(path)
    return p


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M4 media metrics")
    ap.add_argument("video")
    ap.add_argument("--json", help="output path for metrics JSON")
    args = ap.parse_args()
    try:
        m = analyze(args.video)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(m, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(m, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
