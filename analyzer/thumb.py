"""M4 thumbnail scoring (PLAN.md Section 5, M5 Thumbnail category).

Scores candidate thumbnails (your Remotion stills) against the M3
outlier benchmarks (reports/benchmarks.json or video_features medians):

  - word count <= 4           (from EasyOCR)
  - contrast >= benchmark p50
  - saturation >= benchmark p50
  - face present or strong focal object

Usage:
  python -m analyzer.thumb still-hook.png still-title.png ...
  python -m analyzer.thumb "C:\\videogen\\video\\out\\*.png" --json out.json
"""
import argparse
import json
import sys
from pathlib import Path

from config import ROOT, fix_console, load_settings
from miner.thumbs import analyze, load_image  # reuse M3 metrics
from db import get_connection

DEFAULT_BENCH = {"thumb_contrast": 60.0, "thumb_saturation": 90.0}


def benchmarks() -> dict:
    """p50 per metric from benchmarks.json if present, else DB medians."""
    b = ROOT / "reports" / "benchmarks.json"
    if b.exists():
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
            vals = {m: [] for m in ("thumb_contrast", "thumb_saturation")}
            for niche in data.values():
                for fmt in niche.values():
                    for k in vals:
                        if k in fmt and "p50" in fmt[k]:
                            vals[k].append(fmt[k]["p50"])
            if vals["thumb_contrast"]:
                return {k: sum(v) / len(v) for k, v in vals.items()}
        except (ValueError, TypeError):
            pass
    conn = get_connection()
    row = conn.execute(
        "SELECT AVG(thumb_contrast) c, AVG(thumb_saturation) s FROM video_features"
    ).fetchone()
    if row["c"]:
        return {"thumb_contrast": row["c"], "thumb_saturation": row["s"]}
    return DEFAULT_BENCH


def score_thumb(path: Path, bench: dict) -> dict:
    img = load_image(path)
    if img is None:
        return {"file": str(path), "error": "cannot decode"}
    m = analyze(path)  # includes OCR
    issues = []
    if m.get("thumb_word_count") is not None and m["thumb_word_count"] > 4:
        issues.append(f"{m['thumb_word_count']} words on thumbnail; <=4 target")
    if m.get("thumb_contrast", 0) < bench["thumb_contrast"]:
        issues.append(f"contrast {m['thumb_contrast']:.0f} < benchmark p50 {bench['thumb_contrast']:.0f}")
    if m.get("thumb_saturation", 0) < bench["thumb_saturation"]:
        issues.append(f"saturation {m['thumb_saturation']:.0f} < benchmark p50 {bench['thumb_saturation']:.0f}")
    if not m.get("thumb_has_face"):
        issues.append("no face detected (faces lift CTR 25-50% in this niche)")
    ok = len(issues) == 0
    return {
        "file": str(path),
        "score": round(100 * (1 - len(issues) / max(len(issues) + (1 if ok else 0), 1))),
        "pass": ok,
        "metrics": {k: m.get(k) for k in ("thumb_word_count", "thumb_contrast", "thumb_saturation", "thumb_has_face")},
        "issues": issues,
    }


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("images", nargs="+", help="thumbnail files or glob patterns")
    ap.add_argument("--json", help="output path")
    args = ap.parse_args()

    files = []
    for g in args.images:
        if "*" in g or "?" in g:
            files += list(Path(Path.cwd()).glob(g))
        else:
            files.append(Path(g))
    files = [f for f in dict.fromkeys(files) if f.exists()]
    if not files:
        print("ERROR: no images found", file=sys.stderr)
        sys.exit(1)

    bench = benchmarks()
    results = [score_thumb(f, bench) for f in files]
    for r in results:
        flag = "PASS" if r.get("pass") else "FAIL"
        print(f"[{flag}] {Path(r['file']).name}  score={r.get('score')}")
        for i in r.get("issues", []):
            print(f"       - {i}")

    out = Path(args.json) if args.json else None
    if out:
        out.write_text(json.dumps({"benchmarks": bench, "results": results}, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"\n[thumb] written {out}")


if __name__ == "__main__":
    main()