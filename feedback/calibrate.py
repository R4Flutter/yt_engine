"""M7 — recalibrate scorecard weights (PLAN.md Section 5, M7).

After ~10 published videos with real CTR/AVD data, fit a regression of
actual CTR (and AVD%) on the scorecard sub-scores to reweight M5's
CATEGORIES. Prints the new weights; writes them to reports/weights.json.

Usage:
  python -m feedback.calibrate                      # from my_videos actuals
  python -m feedback.calibrate --demo                # synthetic demo data
"""
import argparse
import json
import sys

from config import fix_console, ROOT
from db import get_connection

CATEGORIES = ["Hook", "Thumbnail", "Title", "Retention engineering", "Technical", "Topic momentum"]
DEFAULT = {"Hook": 25, "Thumbnail": 20, "Title": 15, "Retention engineering": 20,
           "Technical": 10, "Topic momentum": 10}


def extract_sub_scores(scorecard_json: str) -> dict:
    sc = json.loads(scorecard_json)
    cats = sc.get("category_scores") or {}
    return {c: cats.get(c, 0) for c in CATEGORIES}


def demo_rows(n: int = 12):
    """Synthetic: CTR driven mostly by Hook, a bit by Title; noise elsewhere."""
    import random
    random.seed(7)
    rows = []
    for i in range(n):
        hook = random.uniform(30, 100)
        title = random.uniform(30, 100)
        rest = {c: random.uniform(30, 90) for c in CATEGORIES if c not in ("Hook", "Title")}
        ctr = 3 + 0.06 * hook + 0.02 * title + random.uniform(-0.4, 0.4)
        rows.append({"subs": {**rest, "Hook": hook, "Title": title}, "ctr": ctr,
                     "avd": 40 + 0.3 * hook + random.uniform(-5, 5)})
    return rows


def fit(rows) -> dict:
    try:
        import numpy as np
    except ImportError:
        print("pip install numpy", file=sys.stderr)
        sys.exit(1)
    X = np.array([[r["subs"][c] for c in CATEGORIES] for r in rows])
    y = np.array([r["ctr"] for r in rows])
    # ridge regression (L2) — robust on small samples
    try:
        from sklearn.linear_model import Ridge
    except ImportError:
        print("pip install scikit-learn", file=sys.stderr)
        sys.exit(1)
    model = Ridge(alpha=1.0).fit(X, y)
    coefs = dict(zip(CATEGORIES, model.coef_))
    # relative importance -> weights summing to 100; clip negatives
    pos = {k: max(v, 0.0) for k, v in coefs.items()}
    total = sum(pos.values()) or 1.0
    weights = {k: round(100 * v / total) for k, v in pos.items()}
    # fix rounding drift so sum == 100
    diff = 100 - sum(weights.values())
    if diff:
        big = max(weights, key=weights.get)
        weights[big] += diff
    return weights, coefs


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--min-rows", type=int, default=5, help="fewer rows than this -> refuse")
    args = ap.parse_args()

    if args.demo:
        rows = demo_rows()
    else:
        conn = get_connection()
        got = conn.execute(
            "SELECT scorecard_json, actual_ctr, actual_avd_pct FROM my_videos "
            "WHERE actual_ctr IS NOT NULL AND scorecard_json IS NOT NULL"
        ).fetchall()
        rows = []
        for r in got:
            subs = extract_sub_scores(r["scorecard_json"])
            if all(subs.values()):
                rows.append({"subs": subs, "ctr": r["actual_ctr"], "avd": r["actual_avd_pct"]})
    if len(rows) < args.min_rows:
        print(f"[calibrate] only {len(rows)} scored videos with actuals (need >= {args.min_rows}); "
              "publish more or run --demo")
        return

    weights, coefs = fit(rows)
    print(f"[calibrate] {len(rows)} videos with real CTR data:")
    for c in CATEGORIES:
        print(f"  {c:<22} weight {weights[c]:>3}  (coef {coefs[c]:+.3f})")
    out = ROOT / "reports" / "weights.json"
    out.write_text(json.dumps({"weights": weights, "coefs": coefs, "n": len(rows)},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[calibrate] written {out} — update analyzer/score.py CATEGORIES with these weights")


if __name__ == "__main__":
    main()