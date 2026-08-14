"""M3 Hook beats — temporal analysis of the opening (PLAN §4, Phase 2).

Do NOT treat the first 30 seconds as one block. Break the hook into beats
using the SAME empirical segmentation as alignment.py (0.80 s gap, MIN_WORDS /
MAX_WORDS guards) — YouTube auto-captions carry no reliable punctuation, so
pause length is the only honest boundary.

Extracts: beat boundaries, per-beat DNA tags, WPM, and the first-occurrence
timestamps that hook_library needs (first number/entity/stakes/curiosity,
promise timestamp).
"""

from __future__ import annotations

import json

from miner.alignment import sentences_from_words
from miner.hook_dna import (CURIOSITY, EMOTIONS, NUMBER, PROMISES, STAKES,
                            extract_dna)

HOOK_WINDOW = 30.0  # seconds of the opening we call "the hook"
GAP = 0.80          # alignment.py's empirical sentence gap


def beat_dna(beat: dict) -> dict:
    """Which DNA markers are present in this beat (for beat typing)."""
    t = beat["text"]
    return {
        "curiosity": [n for n, rx in CURIOSITY if rx.search(t)],
        "emotions": [n for n, rx in EMOTIONS if rx.search(t)],
        "stakes": [n for n, rx in STAKES if rx.search(t)],
        "promise": [n for n, rx in PROMISES if rx.search(t)],
        "has_number": bool(NUMBER.search(t)),
    }


def first_sec(beats: list[dict], predicate) -> float | None:
    for b in beats:
        if predicate(b):
            return b["t_start"]
    return None


def analyze_opening(words: list[dict], duration: float,
                    window: float = HOOK_WINDOW, gap: float = GAP) -> dict:
    """Beat-level analysis of a video's opening.

    words: word-timestamped transcript (yt-dlp auto-caption format).
    duration: full video length in seconds.
    """
    sents = sentences_from_words(words, gap)
    opening = [s for s in sents if s["t_start"] < window]
    beats = []
    for s in opening:
        dur = max(0.3, s["t_end"] - s["t_start"])
        b = {
            "t_start": s["t_start"],
            "t_end": s["t_end"],
            "text": s["text"],
            "word_count": s["word_count"],
            "wpm": round(s["word_count"] / dur * 60, 1),
        }
        b.update(beat_dna(b))
        beats.append(b)

    if not beats:
        return {"beats": [], "hook_start": None, "hook_end": None}

    full_text = " ".join(b["text"] for b in beats)
    dna = extract_dna(full_text)

    return {
        "beats": beats,
        "hook_start": beats[0]["t_start"],
        "hook_end": beats[-1]["t_end"],
        "word_count": sum(b["word_count"] for b in beats),
        "duration": beats[-1]["t_end"] - beats[0]["t_start"],
        "wpm": round(sum(b["wpm"] for b in beats) / len(beats), 1),
        "beat_count": len(beats),
        "beats_json": json.dumps(beats, ensure_ascii=False),
        "first_number_sec": first_sec(beats, lambda b: b["has_number"]),
        "first_entity_sec": _first_entity_sec(beats),
        "first_stakes_sec": first_sec(beats, lambda b: bool(b["stakes"])),
        "first_curiosity_sec": first_sec(beats, lambda b: bool(b["curiosity"])),
        "promise_sec": first_sec(beats, lambda b: bool(b["promise"])),
    }


def _first_entity_sec(beats: list[dict]) -> float | None:
    from miner.hook_dna import PROPER, STOP_CAPS
    for b in beats:
        t = b["text"]
        m = PROPER.search(t)
        if m and m.group(1) not in STOP_CAPS:
            return b["t_start"]
    return None


# Backwards-compatible alias used by hooks.py
analyze_hook = analyze_opening