"""Viral scorecard with fail-closed verification gates.

A score is only a pass when every required category was actually measured.
Missing evidence, --assume-voice, unavailable packaging analysis, or an
unmeasured topic can never become a free pass by disappearing from the
 denominator.
"""
import argparse
import json
import sys
from pathlib import Path

from config import ROOT, fix_console, load_settings
from analyzer.media import analyze as media_analyze
from analyzer.speech import transcribe

CATEGORIES = {
    "Hook": 25,
    "Thumbnail": 20,
    "Title": 15,
    "Retention engineering": 20,
    "Technical": 10,
    "Topic momentum": 10,
}


def load_benchmarks() -> dict | None:
    p = ROOT / "reports" / "benchmarks.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def gate_value(gate: dict, benchmarks: dict | None, metric: str, fallback):
    if benchmarks and metric in benchmarks:
        return benchmarks[metric].get("p50", fallback)
    return fallback


def _check(category, weight, ident, ok, severity, detail, fix, verified=True):
    """Create a check. `verified=False` is always a failed gate in strict mode."""
    return {
        "category": category,
        "weight": weight,
        "id": ident,
        "ok": bool(ok) if verified else False,
        "verified": bool(verified),
        "severity": severity,
        "detail": detail,
        "fix": fix,
    }


def score_video(video: str, title: str | None, assume_voice: bool = False) -> dict:
    settings = load_settings()
    gate = settings["analyzer"]["gate"]
    benches = load_benchmarks()
    media = media_analyze(video)
    speech = {} if assume_voice else transcribe(video, settings)
    dur = media.get("duration_sec", 0) or speech.get("duration_sec", 0)
    checks = []

    # Hook: no bypass. If voice was not verified, Hook is failed, not removed.
    if assume_voice:
        checks.append(_check(
            "Hook", CATEGORIES["Hook"], "HOOK_ASSUMED", False, "FATAL",
            "Voice/narration was assumed rather than measured; hook verification is mandatory.",
            {"type": "manual", "instruction": "Mux narration, then run the scorecard without --assume-voice."},
            verified=False,
        ))
    else:
        promise_target = gate_value(gate, benches, "hook_promise_sec", gate["payoff_promise_sec"])
        checks.append(_check("Hook", CATEGORIES["Hook"], "HOOK_PROMISE",
                             speech.get("hook_promise_sec", 9999) <= promise_target, "high",
                             f"Payoff promise at {speech.get('hook_promise_sec', 'unknown')}s; target <= {promise_target}s",
                             {"type": "script_rewrite", "target": "hook", "instruction": f"State the payoff promise by {promise_target}s in sentence 1-2."}))
        checks.append(_check("Hook", CATEGORIES["Hook"], "HOOK_PACE",
                             speech.get("wpm", 0) >= gate["min_wpm"], "med",
                             f"Words/min = {speech.get('wpm', 'unknown')} (target >= {gate['min_wpm']})",
                             {"type": "props_patch", "path": "script", "op": "trim", "instruction": "Tighten first 30s: cut filler, raise speech pace."}))

    # Retention engineering.
    sc = media.get("scenes", {})
    if sc:
        cpm = sc.get("cuts_per_min", 0)
        lo = gate_value(gate, benches, "cuts_per_min", gate["cuts_per_min_min"])
        hi = gate_value(gate, benches, "cuts_per_min_max", gate["cuts_per_min_max"])
        checks.append(_check("Retention engineering", CATEGORIES["Retention engineering"], "PACING",
                             lo <= cpm <= hi, "med", f"{cpm} cuts/min (target {lo}-{hi})",
                             {"type": "props_patch", "path": "scenes[*].durationInFrames", "op": "scale", "value": round((lo + hi) / 2 / max(cpm, 0.1), 2)}))
        static = sc.get("longest_static_shot", 0)
        checks.append(_check("Retention engineering", CATEGORIES["Retention engineering"], "STATIC_SHOT",
                             static <= gate["max_static_shot_sec"], "high", f"Longest static shot {static}s; max {gate['max_static_shot_sec']}s",
                             {"type": "props_patch", "path": "scenes", "op": "add_motion", "instruction": "Add a meaningful visual change or B-roll to the static scene."}))
    else:
        checks.append(_check("Retention engineering", CATEGORIES["Retention engineering"], "RETENTION_UNMEASURED", False, "FATAL",
                             "Scene/cut analysis is unavailable; retention quality cannot be inferred.",
                             {"type": "analysis", "instruction": "Run media analysis successfully before scoring."}, verified=False))

    # Technical.
    lufs = media.get("loudness", {}).get("integrated_lufs")
    if lufs is not None and not assume_voice:
        checks.append(_check("Technical", CATEGORIES["Technical"], "LOUDNESS",
                             gate["loudness_lufs_min"] <= lufs <= gate["loudness_lufs_max"], "med",
                             f"Integrated loudness {lufs} LUFS (target -14 +/- 1)",
                             {"type": "props_patch", "path": "audio", "op": "normalize", "instruction": "Normalize audio to the configured loudness range."}))
    else:
        checks.append(_check("Technical", CATEGORIES["Technical"], "LOUDNESS_UNVERIFIED", False, "FATAL",
                             "Loudness could not be verified.",
                             {"type": "analysis", "instruction": "Provide a real audio track and run analysis without --assume-voice."}, verified=False))

    height = media.get("height", 0)
    checks.append(_check("Technical", CATEGORIES["Technical"], "RESOLUTION", height >= 1080, "low",
                         f"Resolution {media.get('width', 0)}x{height} (need >=1080p)",
                         {"type": "props_patch", "path": "composition", "op": "set", "instruction": "Render at 1080p or higher."}))

    # Packaging is required evidence, not optional bonus points.
    if title:
        from miner.llm import title_stats
        ts = title_stats(title)
        checks.append(_check("Title", CATEGORIES["Title"], "TITLE_LEN", ts["len"] <= 60, "med",
                             f"Title {ts['len']} chars (max 60)", {"type": "text", "instruction": "Shorten title to <=60 chars."}))
        checks.append(_check("Title", CATEGORIES["Title"], "TITLE_NUMBER", ts["number_is_specific"], "med",
                             f"Specific number in title: {ts['number_is_specific']}", {"type": "text", "instruction": "Use a specific, defensible number when the title needs one."}))
    else:
        checks.append(_check("Title", CATEGORIES["Title"], "TITLE_MISSING", False, "FATAL",
                             "No candidate title was supplied, so packaging cannot be verified.",
                             {"type": "input", "instruction": "Supply --title before treating the score as publishable."}, verified=False))

    # Thumbnail/topic analysis is not implemented in this MVP. Missing analysis
    # is therefore an explicit failure, never a removed denominator.
    checks.append(_check("Thumbnail", CATEGORIES["Thumbnail"], "THUMB_UNMEASURED", False, "FATAL",
                         "Thumbnail analysis is unavailable; this category cannot be declared good.",
                         {"type": "analysis", "instruction": "Run thumbnail analysis before publish-gating."}, verified=False))
    checks.append(_check("Topic momentum", CATEGORIES["Topic momentum"], "TOPIC_UNMEASURED", False, "FATAL",
                         "Topic momentum analysis is unavailable; this category cannot be declared good.",
                         {"type": "analysis", "instruction": "Run the hot-cluster/topic-demand analysis before publish-gating."}, verified=False))

    # FAIL CLOSED: every category remains in the denominator.
    earned = sum(c["weight"] for c in checks if c["ok"])
    score = round(earned / sum(CATEGORIES.values()) * 100)
    issues = [c for c in checks if not c["ok"]]
    cat_scores = {}
    for category, weight in CATEGORIES.items():
        rows = [c for c in checks if c["category"] == category]
        earned_cat = sum(c["weight"] for c in rows if c["ok"])
        cat_scores[category] = round(earned_cat / weight * 100)

    pass_cfg = settings["analyzer"]["pass"]
    gates = {
        f"overall >= {pass_cfg['overall_min']}": score >= pass_cfg["overall_min"],
        f"hook >= {pass_cfg['hook_min']}": cat_scores["Hook"] >= pass_cfg["hook_min"],
        f"retention >= {pass_cfg['retention_min']}": cat_scores["Retention engineering"] >= pass_cfg["retention_min"],
        f"packaging >= {pass_cfg['packaging_min']}": (cat_scores["Thumbnail"] + cat_scores["Title"]) / 2 >= pass_cfg["packaging_min"],
        "all_required_categories_verified": all(c["verified"] for c in checks),
        "no_unverified_or_failed_checks": not issues,
    }
    verdict = "PASS" if all(gates.values()) else "FIX_REQUIRED"

    return {
        "score": score,
        "verdict": verdict,
        "gates": gates,
        "category_scores": cat_scores,
        "packaging_score": round((cat_scores["Thumbnail"] + cat_scores["Title"]) / 2),
        "issues": issues,
        "checks": checks,
        "verification": {"complete": all(c["verified"] for c in checks), "failed_checks": len(issues)},
        "duration_sec": dur,
    }


def _json_default(o):
    item = getattr(o, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")


def main():
    fix_console()
    ap = argparse.ArgumentParser(description="VIRALFORGE fail-closed viral scorecard")
    ap.add_argument("video")
    ap.add_argument("--title", required=False)
    ap.add_argument("--assume-voice", action="store_true", help="legacy pre-mux mode; NEVER publish-passable")
    ap.add_argument("--out")
    args = ap.parse_args()
    if not Path(args.video).exists():
        print(f"ERROR: {args.video} not found", file=sys.stderr)
        sys.exit(1)
    sc = score_video(args.video, args.title, assume_voice=args.assume_voice)
    print(json.dumps(sc, indent=2, ensure_ascii=False, default=_json_default))
    out = Path(args.out) if args.out else Path(args.video).with_name("scorecard.json")
    out.write_text(json.dumps(sc, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")
    print(f"\n[scorecard] {sc['verdict']} — {sc['score']}/100 -> {out}")
    if sc["verdict"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
