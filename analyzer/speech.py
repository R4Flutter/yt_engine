"""M4 Self-Analyzer Ã¢â‚¬â€ speech metrics (PLAN.md Section 5, M4).

faster-whisper word-level transcription: hook text, WPM, hook_promise_sec.

Usage:
  python -m analyzer.speech path/to/video.mp4 [--json out.json]
"""
import argparse
import json
import re
import sys

from faster_whisper import WhisperModel

from config import fix_console, load_settings


def transcribe(path: str, settings: dict) -> dict:
    model = WhisperModel(settings["analyzer"]["whisper_model"],
                         device=settings["analyzer"].get("device", "cpu"))
    segments, info = model.transcribe(path, word_timestamps=True, vad_filter=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"start": round(w.start, 2), "end": round(w.end, 2), "text": w.word})
    dur = info.duration or 0
    full = " ".join(w["text"].strip() for w in words)
    hook_words = [w for w in words if w["start"] < 30]
    hook_text = " ".join(w["text"].strip() for w in hook_words)

    payoff = re.compile(
        r"(today|in this video|by the end|you\'?ll|you will|let me show|the truth about|"
        r"how .{3,30} (lost|made|built|became|destroyed|collapsed)|the (real|actual|inside) story)"
    )
    m = payoff.search(hook_text.lower())
    hook_promise_sec = 30.0
    if m:
        t = next((w["start"] for w in hook_words if m.start() < hook_text.find(w["text"]) + len(w["text"])), None)
        hook_promise_sec = min(30.0, t if t is not None else 15.0)

    return {
        "duration_sec": round(dur, 2),
        "full_text": full,
        "hook_text": hook_text,
        "hook_promise_sec": round(hook_promise_sec, 2),
        "wpm": round(len(words) / max(dur / 60, 0.1)),
        "words": words,
        "word_count": len(words),
    }


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M4 speech metrics")
    ap.add_argument("video")
    ap.add_argument("--json", help="output path for speech JSON")
    args = ap.parse_args()
    settings = load_settings()
    out = transcribe(args.video, settings)
    print(json.dumps({k: v for k, v in out.items() if k != "words"}, indent=2))
    if args.json:
        json.dump(out, open(args.json, "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()
