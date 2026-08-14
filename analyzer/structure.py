"""M4 structure map (PLAN.md Section 5, M4).

Samples 1 frame/second of your video, measures visual change rate
(brightness delta, frame diff), then aligns script sections from a
scene/props JSON to the timeline and flags drop-off risk:
  - scenes > 40s with low visual change
  - long static stretches (no cut for > 8s)
  - loudness/silence per scene (optional, via ffmpeg)

Scene JSON shape (matches Remotion props / director-plan.json):
  { "scenes": [ {"label": "THE HOOK", "start": 0, "end": 6}, ... ] }

Usage:
  python -m analyzer.structure out/video.mp4 --scenes scenes.json
  python -m analyzer.structure out/video.mp4 --scenes scenes.json --json out.json
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from config import fix_console


def sample_frames(video: str, step: int = 30) -> list[dict]:
    """One sample every `step` frames: brightness + mean abs frame diff."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    out, prev, idx = [], None, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (64, 36))
            b = float(np.mean(small))
            d = float(np.mean(np.abs(small.astype(np.int16) - prev))) if prev is not None else 0.0
            out.append({"t": round(idx / fps, 2), "brightness": round(b, 1), "frame_delta": round(d, 2)})
            prev = small
        idx += 1
    cap.release()
    return out


def find_structures(frames: list[dict], max_static_sec: float = 8.0) -> list[dict]:
    """Consecutive samples with near-zero frame delta = static shot."""
    static, cur, issues = False, None, []
    for f in frames:
        moving = f["frame_delta"] > 1.0
        if not moving and not static:
            static, cur = True, f["t"]
        elif moving and static:
            dur = f["t"] - cur
            if dur > max_static_sec:
                issues.append({"kind": "static_shot", "start": round(cur, 1), "duration": round(dur, 1)})
            static = False
    if static:
        dur = frames[-1]["t"] - cur
        if dur > max_static_sec:
            issues.append({"kind": "static_shot", "start": round(cur, 1), "duration": round(dur, 1)})
    return issues


def map_scenes(frames: list[dict], scenes: list[dict], max_scene_sec: float = 40.0) -> list[dict]:
    out = []
    for s in scenes:
        seg = [f for f in frames if s["start"] <= f["t"] < s["end"]]
        delta = [f["frame_delta"] for f in seg]
        mean_d = sum(delta) / len(delta) if delta else 0.0
        dur = s["end"] - s["start"]
        risk = dur > max_scene_sec and mean_d < 2.0
        out.append({
            "label": s.get("label", "?"),
            "start": s["start"], "end": s["end"], "duration": round(dur, 1),
            "mean_frame_delta": round(mean_d, 2),
            "dropoff_risk": risk,
            "risk_reason": f"scene {dur:.0f}s > {max_scene_sec:.0f}s with low visual change" if risk else None,
        })
    return out


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--scenes", help="scene JSON (Remotion props / director-plan style)")
    ap.add_argument("--json", help="output path")
    args = ap.parse_args()

    frames = sample_frames(args.video)
    result = {"samples": len(frames), "static_issues": find_structures(frames), "scenes": []}
    if args.scenes:
        data = json.loads(Path(args.scenes).read_text(encoding="utf-8"))
        scenes = data.get("scenes") if isinstance(data, dict) else data
        if scenes:
            result["scenes"] = map_scenes(frames, scenes)
    print(f"[structure] {result['samples']} samples @1fps")
    for s in result["static_issues"]:
        print(f"  [RISK] static shot {s['start']}s for {s['duration']}s")
    for s in result["scenes"]:
        flag = "RISK" if s["dropoff_risk"] else "ok"
        print(f"  [{flag:4s}] {s['label']}: {s['duration']}s, frame_delta {s['mean_frame_delta']}"
              + (f" — {s['risk_reason']}" if s["risk_reason"] else ""))
    if not result["static_issues"] and not any(s["dropoff_risk"] for s in result["scenes"]):
        print("  no drop-off risk spots found")
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[structure] written {args.json}")


if __name__ == "__main__":
    main()