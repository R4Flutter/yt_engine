"""M5 Viral Scorecard (PLAN.md Section 5, M5 + Section 6 gate).

Combines M4 media + speech metrics against the Section 6 gate thresholds
(absolute), or benchmark percentiles when reports/benchmarks.json exists.

Usage:
  python -m analyzer.score path/to/video.mp4 [--title "TITLE"] [--out scorecard.json]
"""
import argparse
import json
import sys
from pathlib import Path

from config import ROOT, fix_console, load_settings, resolve_path
from analyzer.media import analyze as media_analyze
from analyzer.speech import transcribe

CATEGORIES = {"Hook": 25, "Thumbnail": 20, "Title": 15,
              "Retention engineering": 20, "Technical": 10, "Topic momentum": 10}


def load_benchmarks() -> dict | None:
    p = ROOT / "reports" / "benchmarks.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def gate_value(gate: dict, benchmarks: dict | None, metric: str, fallback):
    if benchmarks and metric in benchmarks:
        return benchmarks[metric].get("p50", fallback)
    return fallback


def score_video(video: str, title: str | None, assume_voice: bool = False) -> dict:
    settings = load_settings()
    gate = settings["analyzer"]["gate"]
    benches = load_benchmarks()

    media = media_analyze(video)
    speech = transcribe(video, settings) if not assume_voice else {}
    dur = media.get("duration_sec", 0) or speech.get("duration_sec", 0)

    checks = []
    # --- Hook (25)
    if assume_voice:
        checks.append({
            "category": "Hook", "weight": CATEGORIES["Hook"],
            "id": "HOOK_ASSUMED", "ok": None, "severity": "low",
            "detail": "Voice/narration assumed present (--assume-voice); whisper hook checks skipped",
            "fix": {"type": "manual",
                    "instruction": "Mux narration, then re-run without --assume-voice to verify the hook."},
        })
    else:
        promise_target = gate_value(gate, benches, "hook_promise_sec", gate["payoff_promise_sec"])
        ok = speech["hook_promise_sec"] <= promise_target
        checks.append({
            "category": "Hook", "weight": CATEGORIES["Hook"],
            "id": "HOOK_PROMISE", "ok": ok, "severity": "high",
            "detail": f"Payoff promise at {speech['hook_promise_sec']}s; target <= {promise_target}s",
            "fix": {"type": "script_rewrite", "target": "hook",
                    "instruction": f"State the payoff promise by {promise_target}s in sentence 1-2."},
        })
        checks.append({
            "category": "Hook", "weight": CATEGORIES["Hook"],
            "id": "HOOK_PACE", "ok": speech["wpm"] >= gate["min_wpm"], "severity": "med",
            "detail": f"Words/min = {speech['wpm']} (target >= {gate['min_wpm']})",
            "fix": {"type": "props_patch", "path": "script", "op": "trim",
                    "instruction": "Tighten first 30s: cut filler, raise speech pace."},
        })

    # --- Retention engineering (20)
    sc = media.get("scenes", {})
    if sc:
        cpm = sc.get("cuts_per_min", 0)
        lo, hi = gate_value(gate, benches, "cuts_per_min", gate["cuts_per_min_min"]), \
                 gate_value(gate, benches, "cuts_per_min_max", gate["cuts_per_min_max"])
        checks.append({
            "category": "Retention engineering", "weight": CATEGORIES["Retention engineering"],
            "id": "PACING", "ok": lo <= cpm <= hi, "severity": "med",
            "detail": f"{cpm} cuts/min (outlier target {lo}-{hi})",
            "fix": {"type": "props_patch", "path": "scenes[*].durationInFrames", "op": "scale",
                    "value": round((lo + hi) / 2 / max(cpm, 0.1), 2)},
        })
        static = sc.get("longest_static_shot", 0)
        checks.append({
            "category": "Retention engineering", "weight": CATEGORIES["Retention engineering"],
            "id": "STATIC_SHOT", "ok": static <= gate["max_static_shot_sec"], "severity": "high",
            "detail": f"Longest static shot {static}s; max {gate['max_static_shot_sec']}s",
            "fix": {"type": "props_patch", "path": "scenes", "op": "add_motion",
                    "instruction": "Add camera move/b-roll to the static scene."},
        })

# --- Technical (10)
    lufs = media.get("loudness", {}).get("integrated_lufs")
    if lufs is not None and not assume_voice:
        checks.append({
            "category": "Technical", "weight": CATEGORIES["Technical"],
            "id": "LOUDNESS", "ok": gate["loudness_lufs_min"] <= lufs <= gate["loudness_lufs_max"],
            "severity": "med",
            "detail": f"Integrated loudness {lufs} LUFS (target -14 +/- 1)",
            "fix": {"type": "props_patch", "path": "audio", "op": "normalize",
                    "instruction": "Normalize audio to -14 LUFS"},
        })
    checks.append({
        "category": "Technical", "weight": CATEGORIES["Technical"],
        "id": "RESOLUTION", "ok": media.get("height", 0) >= 1080, "severity": "low",
        "detail": f"Resolution {media.get('width', 0)}x{media.get('height', 0)} (need >= 1080p)",
        "fix": {"type": "props_patch", "path": "composition", "op": "set",
                "instruction": "Render at 1080p or higher."},
    })

    # --- Title (15) â€” only if a title was provided
    if title:
        from miner.llm import title_stats
        ts = title_stats(title)
        checks.append({
            "category": "Title", "weight": CATEGORIES["Title"],
            "id": "TITLE_LEN", "ok": ts["len"] <= 60, "severity": "med",
            "detail": f"Title {ts['len']} chars (max 60)",
            "fix": {"type": "text", "instruction": "Shorten title to <= 60 chars."},
        })
        checks.append({
            "category": "Title", "weight": CATEGORIES["Title"],
            "id": "TITLE_NUMBER", "ok": ts["number_is_specific"], "severity": "med",
            "detail": f"Specific number in title: {ts['number_is_specific']}",
            "fix": {"type": "text", "instruction": "Use a specific odd number ($10,427 beats $10,000)."},
        })

    # --- Thumbnail (20) / Topic (10): not measured in MVP
    checks.append({"category": "Thumbnail", "weight": CATEGORIES["Thumbnail"], "id": "THUMB_NA",
                   "ok": None, "severity": "low", "detail": "Thumbnail analysis not available in MVP cut",
                   "fix": {"type": "manual", "instruction": "Run M3 thumbnail mining or check visually: <=4 words, high contrast, strong face."}})
    checks.append({"category": "Topic", "weight": CATEGORIES["Topic momentum"], "id": "TOPIC_NA",
                   "ok": None, "severity": "low", "detail": "Topic momentum needs hot-cluster list (M3)",
                   "fix": {"type": "manual", "instruction": "Check the topic against the weekly patterns report hot list."}})

    scored = [c for c in checks if c["ok"] is not None]
    earned = sum(c["weight"] for c in scored if c["ok"])
    total = sum(c["weight"] for c in scored)
    score = round(earned / total * 100) if total else 0
    issues = [c for c in checks if c["ok"] is False]

    # per-category scores (unmeasured checks don't count against you)
    cat_totals: dict[str, list] = {}
    for c in scored:
        e, t = cat_totals.get(c["category"], [0, 0])
        cat_totals[c["category"]] = [e + (c["weight"] if c["ok"] else 0), t + c["weight"]]
    cat_scores = {k: round(v[0] / v[1] * 100) if v[1] else None for k, v in cat_totals.items()}

    def _packaging() -> int | None:
        e = sum(cat_totals[k][0] for k in ("Thumbnail", "Title") if k in cat_totals)
        t = sum(cat_totals[k][1] for k in ("Thumbnail", "Title") if k in cat_totals)
        return round(e / t * 100) if t else None

    pass_cfg = settings["analyzer"]["pass"]
    hook = cat_scores.get("Hook")
    retention = cat_scores.get("Retention engineering")
    packaging = _packaging()
    gates = {f"overall >= {pass_cfg['overall_min']}": score >= pass_cfg["overall_min"]}
    if hook is not None:
        gates[f"hook >= {pass_cfg['hook_min']}"] = hook >= pass_cfg["hook_min"]
    if retention is not None:
        gates[f"retention >= {pass_cfg['retention_min']}"] = retention >= pass_cfg["retention_min"]
    if packaging is not None:
        gates[f"packaging >= {pass_cfg['packaging_min']}"] = packaging >= pass_cfg["packaging_min"]
    verdict = "PASS" if all(gates.values()) else "FIX_REQUIRED"

    return {
        "score": score,
        "verdict": verdict,
        "gates": gates,
        "category_scores": cat_scores,
        "packaging_score": packaging,
        "issues": issues,
        "checks": checks,
    }


def _json_default(o):
    item = getattr(o, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="M5 viral scorecard")
    ap.add_argument("video", help="path to your rendered Remotion output (.mp4)")
    ap.add_argument("--title", help="your candidate title (scored against title rules)")
    ap.add_argument("--assume-voice", action="store_true",
                    help="skip whisper/loudness checks (narration not yet muxed)")
    ap.add_argument("--out", help="output path (default: alongside video as scorecard.json)")
    args = ap.parse_args()

    if not Path(args.video).exists():
        print(f"ERROR: {args.video} not found", file=sys.stderr)
        sys.exit(1)
    sc = score_video(args.video, args.title, assume_voice=args.assume_voice)
    print(json.dumps(sc, indent=2, ensure_ascii=False, default=_json_default))
    out = Path(args.out) if args.out else Path(args.video).with_name("scorecard.json")
    out.write_text(json.dumps(sc, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    print(f"\n[scorecard] {sc['verdict']} — {sc['score']}/100 -> {out}")


if __name__ == "__main__":
    main()
