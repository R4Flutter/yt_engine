"""Export corpus standardization moments for the retention ridge model.

The coefficients in reports/retention_coefficients.json were fitted on
StandardScaler-transformed features over the sentence corpus. Predicting on a
new script in the model's own units requires those moments; they were never
exported with the coefficients. This recomputes them from the exact same
subset the fit used (sentences.heat_z IS NOT NULL) and writes them beside the
coefficients, so tools/retention-score.mjs can predict in corpus units.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "viralforge.db"

FEATURES = ["has_dollar", "has_number", "number_specific", "has_percent",
            "is_question", "is_contrast", "is_consequence", "names_person",
            "names_org", "new_entity", "abstract_subj", "sec_since_entity",
            "sec_since_number", "word_count", "wpm", "len_delta"]

conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT " + ",".join(FEATURES) + " FROM sentences WHERE heat_z IS NOT NULL"
).fetchall()
conn.close()

cols = list(zip(*rows)) if rows else []
moments = {}
for name, vals in zip(FEATURES, cols):
    vals = [float(v) for v in vals]
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n  # ddof=0, matches sklearn StandardScaler
    moments[name] = {"mean": round(mean, 6), "std": round(var ** 0.5, 6)}

out = {
    "n_sentences": len(rows),
    "features": moments,
    "note": "Corpus moments (ddof=0) over sentences.heat_z IS NOT NULL — the same subset the ridge was fitted on.",
}
path = ROOT / "reports" / "retention_moments.json"
path.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"n={len(rows)}  wrote {path}")
for name in FEATURES:
    m = moments[name]
    print(f"  {name:>18}  mean={m['mean']:>10.4f}  std={m['std']:>10.4f}")
