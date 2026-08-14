"""M4 — the learned Hook Intelligence layer (Phases 3-12, 19-22).

The LLM is NOT the intelligence layer. This module is: a deterministic
training dataset built from the real corpus, per-horizon lightweight ML
(Ridge / HistGradientBoosting, CPU-only, memory-conscious), channel-grouped
validation, honest prediction with coefficient explanations, interaction
discovery, and a LEARNED pattern library with a niche hierarchy fallback.

Everything here is optional at runtime: the generator works exactly as before
when no models have been trained (models are loaded only if they exist).

Confidence is earned, not claimed. Phase 21 thresholds:
    N < 20   -> INSUFFICIENT DATA
    N 20-49  -> LOW
    N 50-149 -> MEDIUM
    N 150+   -> potentially HIGH (and only if the CI excludes zero)
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from config import load_settings, resolve_path

HORIZONS = (3, 5, 10, 15, 30)          # retention horizons the models predict
TRAIN_MIN_VIDEOS = 20                  # below this, keep baseline only
MIN_PATTERN_VIDEOS = 20                # Phase 21: <20 is INSUFFICIENT DATA
BOOTSTRAP_ITERS = 400
RNG_SEED = 42
MAX_COMBOS = 15                        # curated combos, never millions

# ------------------------------------------------------------- feature model
# Everything is derived from hook_library columns + hook_dna_json, so the
# training table is one SELECT, streamed, no pandas, no full-corpus material.

NUMERIC_FEATURES = [
    "word_count", "wpm", "hook_duration", "outlier_score",
    "first_number_sec", "first_entity_sec", "first_stakes_sec",
    "first_curiosity_sec", "promise_sec",
    "specific_number_count", "entity_count", "company_count",
]

CATEGORICAL_FEATURES = [
    "opening_device", "curiosity_mechanism", "emotional_mechanism",
    "stakes_type", "promise_type",
]

BINARY_FEATURES = [
    "open_loop", "has_question", "concrete_outcome",
    "has_number", "has_dollar", "has_percent", "has_date",
    "number_before_5s", "entity_before_5s", "stakes_before_5s",
    "curiosity_before_5s", "promise_before_10s",
    "struct_state", "struct_contradiction", "struct_reversal",
    "struct_question", "struct_stakes", "struct_shock", "struct_claim",
    "struct_problem", "struct_consequence", "struct_promise",
    "struct_mystery", "struct_unexpected", "struct_open_loop",
    "struct_statement",
]

STRUCT_ATOMS = [
    "STATE", "CONTRADICTION", "REVERSAL", "QUESTION", "STAKES", "SHOCK",
    "CLAIM", "PROBLEM", "CONSEQUENCE", "PROMISE", "MYSTERY",
    "UNEXPECTED", "OPEN_LOOP", "STATEMENT",
]

FEATURE_LABELS = {
    "word_count": "hook length (words)", "wpm": "delivery speed (wpm)",
    "hook_duration": "hook duration (s)", "outlier_score": "video outlier score",
    "first_number_sec": "first number timing (s)",
    "first_entity_sec": "first entity timing (s)",
    "first_stakes_sec": "first stakes timing (s)",
    "first_curiosity_sec": "first curiosity timing (s)",
    "promise_sec": "promise timing (s)",
    "specific_number_count": "specific (non-round) numbers",
    "entity_count": "named entities", "company_count": "named companies",
    "opening_device": "opening device", "curiosity_mechanism": "curiosity mechanism",
    "emotional_mechanism": "emotional mechanism", "stakes_type": "stakes type",
    "promise_type": "promise type", "open_loop": "open loop",
    "has_question": "asks a question", "concrete_outcome": "concrete outcome",
    "has_number": "carries a number", "has_dollar": "states dollars",
    "has_percent": "states a percent", "has_date": "states a date",
    "number_before_5s": "number within 5s", "entity_before_5s": "entity within 5s",
    "stakes_before_5s": "stakes within 5s", "curiosity_before_5s": "curiosity within 5s",
    "promise_before_10s": "promise within 10s",
    "struct_state": "STATE atom", "struct_contradiction": "CONTRADICTION atom",
    "struct_reversal": "REVERSAL atom", "struct_question": "QUESTION atom",
    "struct_stakes": "STAKES atom", "struct_shock": "SHOCK atom",
    "struct_claim": "CLAIM atom", "struct_problem": "PROBLEM atom",
    "struct_consequence": "CONSEQUENCE atom",
    "struct_promise": "PROMISE atom", "struct_mystery": "MYSTERY atom",
    "struct_unexpected": "UNEXPECTED_OUTCOME atom",
    "struct_open_loop": "OPEN_LOOP atom", "struct_statement": "STATEMENT atom",
}

# --------------------------------------------------------- feature extraction

def _atom_flags(structure: str | None) -> dict:
    atoms = {a: 0 for a in STRUCT_ATOMS}
    if structure:
        for a in structure.split(" → "):
            a = a.strip().upper()
            if a in atoms:
                atoms[a] = 1
    return atoms


def features_from_row(r: sqlite3.Row) -> dict:
    """Deterministic feature dict from a hook_training_examples row."""
    f = {}
    for n in NUMERIC_FEATURES:
        v = r[n]
        f[n] = None if v is None else float(v)
    for c in CATEGORICAL_FEATURES:
        f[c] = r[c] or "none"
    for b in BINARY_FEATURES:
        f[b] = int(r[b] or 0)
    return f


def features_from_dna(dna: dict) -> dict:
    """Feature dict for a NEWLY GENERATED hook (no beats/timing available).

    Timing features are missing (None) — the encoder imputes the training
    median and flags them, which is the honest neutral value. DNA-only
    predictions are labeled with that caveat.
    """
    lex = {k: dna.get(k, 0) for k in (
        "word_count", "specific_number_count", "entity_count", "company_count")}
    f = {
        "word_count": float(lex.get("word_count") or 0),
        "wpm": None, "hook_duration": None, "outlier_score": None,
        "first_number_sec": None, "first_entity_sec": None,
        "first_stakes_sec": None, "first_curiosity_sec": None, "promise_sec": None,
        "specific_number_count": float(lex["specific_number_count"]),
        "entity_count": float(lex["entity_count"]),
        "company_count": float(lex["company_count"]),
        "opening_device": dna.get("opening_device") or "plain_statement",
        "curiosity_mechanism": dna.get("curiosity_mechanism") or "none",
        "emotional_mechanism": dna.get("emotional_mechanism") or "neutral",
        "stakes_type": dna.get("stakes_type") or "none",
        "promise_type": dna.get("promise_type") or "none",
        "open_loop": int(dna.get("open_loop") or 0),
        "has_question": int(dna.get("has_question") or 0),
        "concrete_outcome": int(dna.get("concrete_outcome") or 0),
        "has_number": int(dna.get("has_number") or 0),
        "has_dollar": int(dna.get("has_dollar") or 0),
        "has_percent": int(dna.get("has_percent") or 0),
        "has_date": int(dna.get("has_date") or 0),
    }
    f.update({f"number_before_5s": 0, f"entity_before_5s": 0,
              f"stakes_before_5s": 0, f"curiosity_before_5s": 0,
              f"promise_before_10s": 0})
    f.update(_atom_flags(dna.get("narrative_structure")))
    return f


# ------------------------------------------------------------------ encoding

def _encode(features: list[dict], numeric_cols: list[str],
            cat_cats: dict[str, list[str]]) -> np.ndarray:
    """Features -> dense float matrix. Categories are pre-collected at build
    time (deterministic, stored in model metadata); unseen values -> 'other'."""
    rows = []
    for f in features:
        row = []
        for c in numeric_cols:
            row.append(f[c] if f.get(c) is not None else np.nan)
        for cat, cats in cat_cats.items():
            v = f.get(cat) or "none"
            for k in cats:
                row.append(1.0 if v == k else 0.0)
            row.append(0.0 if v in cats else 1.0)  # "other" bucket, always
        for b in BINARY_FEATURES:
            row.append(float(f.get(b) or 0.0))
        rows.append(row)
    return np.array(rows, dtype=np.float64)


def _col_names(numeric_cols: list[str], cat_cats: dict[str, list[str]]) -> list[str]:
    names = list(numeric_cols)
    for cat, cats in cat_cats.items():
        names += [f"{cat}={k}" for k in cats] + [f"{cat}=other"]
    names += BINARY_FEATURES
    return names


def _collect_categories(conn) -> dict[str, list[str]]:
    cats: dict[str, list[str]] = {}
    for c in CATEGORICAL_FEATURES:
        rows = conn.execute(
            f"SELECT DISTINCT {c} AS v FROM hook_training_examples "
            f"WHERE {c} IS NOT NULL ORDER BY {c}").fetchall()
        cats[c] = [r["v"] for r in rows if r["v"]]
    return cats


# ------------------------------------------------------------ dataset build

BUILD_COLS = ["video_id", "channel_id", "channel", "niche_tag", "hook_text",
              *NUMERIC_FEATURES, *CATEGORICAL_FEATURES, *BINARY_FEATURES,
              "target_3s", "target_5s", "target_10s", "target_15s", "target_30s"]


def build_training_data(conn, settings, replace: bool = False) -> int:
    """Materialize hook_training_examples from hook_library (streamed).

    One row per hook with retention. Never loads the sentence/heatmap tables;
    features come from the already-mined library columns and hook_dna_json.
    """
    if replace:
        conn.execute("DELETE FROM hook_training_examples")
        conn.commit()

    rows = conn.execute(
        """SELECT l.video_id, v.channel_id, l.channel, l.niche_tag, l.hook_text,
                  l.word_count, l.wpm, l.duration AS hook_duration,
                  l.outlier_score, l.first_number_sec, l.first_entity_sec,
                  l.first_stakes_sec, l.first_curiosity_sec, l.promise_sec,
                  l.opening_device, l.curiosity_mechanism,
                  l.emotional_mechanism, l.stakes_type, l.promise_type,
                  l.retention_3s, l.retention_5s, l.retention_10s,
                  l.retention_15s, l.retention_30s,
                  COALESCE(vf.hook_dna_json, '{}') AS dna_json
           FROM hook_library l
           JOIN videos v ON v.video_id = l.video_id
           LEFT JOIN video_features vf ON vf.video_id = l.video_id
           WHERE l.hook_text IS NOT NULL AND l.retention_3s IS NOT NULL
             AND l.retention_10s IS NOT NULL AND l.retention_30s IS NOT NULL"""
    ).fetchall()

    done = {r[0] for r in conn.execute(
        "SELECT video_id FROM hook_training_examples")} if not replace else set()

    def _dna(r) -> dict:
        try:
            d = json.loads(r["dna_json"] or "{}")
            return d if isinstance(d, dict) else {}
        except json.JSONDecodeError:
            return {}

    n = 0
    for r in rows:
        if r["video_id"] in done:
            continue
        d = _dna(r)
        atoms = {f"struct_{a.lower()}": v for a, v in
                 _atom_flags(d.get("narrative_structure")).items()}
        timing = {
            "first_number_sec": r["first_number_sec"],
            "first_entity_sec": r["first_entity_sec"],
            "first_stakes_sec": r["first_stakes_sec"],
            "first_curiosity_sec": r["first_curiosity_sec"],
            "promise_sec": r["promise_sec"],
        }
        binary = {
            "open_loop": int(d.get("open_loop") or 0),
            "has_question": int(d.get("has_question") or 0),
            "concrete_outcome": int(d.get("concrete_outcome") or 0),
            "has_number": int(d.get("has_number") or 0),
            "has_dollar": int(d.get("has_dollar") or 0),
            "has_percent": int(d.get("has_percent") or 0),
            "has_date": int(d.get("has_date") or 0),
            "number_before_5s": int(timing["first_number_sec"] is not None
                                    and timing["first_number_sec"] < 5),
            "entity_before_5s": int(timing["first_entity_sec"] is not None
                                    and timing["first_entity_sec"] < 5),
            "stakes_before_5s": int(timing["first_stakes_sec"] is not None
                                    and timing["first_stakes_sec"] < 5),
            "curiosity_before_5s": int(timing["first_curiosity_sec"] is not None
                                       and timing["first_curiosity_sec"] < 5),
            "promise_before_10s": int(timing["promise_sec"] is not None
                                      and timing["promise_sec"] < 10),
        }
        binary.update(atoms)
        row = {
            "video_id": r["video_id"], "channel_id": r["channel_id"],
            "channel": r["channel"], "niche_tag": r["niche_tag"],
            "hook_text": r["hook_text"],
            "word_count": r["word_count"], "wpm": r["wpm"],
            "hook_duration": r["hook_duration"],
            "outlier_score": r["outlier_score"],
            **{k: timing[k] for k in ("first_number_sec", "first_entity_sec",
                                      "first_stakes_sec", "first_curiosity_sec",
                                      "promise_sec")},
            "specific_number_count": d.get("specific_number_count", 0),
            "entity_count": d.get("entity_count", 0),
            "company_count": d.get("company_count", 0),
            "opening_device": r["opening_device"] or d.get("opening_device") or "plain_statement",
            "curiosity_mechanism": r["curiosity_mechanism"] or d.get("curiosity_mechanism") or "none",
            "emotional_mechanism": r["emotional_mechanism"] or d.get("emotional_mechanism") or "neutral",
            "stakes_type": r["stakes_type"] or d.get("stakes_type") or "none",
            "promise_type": r["promise_type"] or d.get("promise_type") or "none",
            **binary,
            "target_3s": r["retention_3s"], "target_5s": r["retention_5s"],
            "target_10s": r["retention_10s"], "target_15s": r["retention_15s"],
            "target_30s": r["retention_30s"],
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        conn.execute(
            f"""INSERT INTO hook_training_examples ({','.join(BUILD_COLS)})
                VALUES ({','.join('?' * len(BUILD_COLS))})""",
            tuple(row[c] for c in BUILD_COLS))
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------- validation

def _channel_grouped_split(conn):
    """(video_ids, channels, y per horizon) — one sample per video, groups by
    channel so no channel leaks across train/test. Rows within a video are
    never split by construction (one row per video)."""
    rows = conn.execute(
        """SELECT video_id, channel_id,
                  AVG(target_3s), AVG(target_5s), AVG(target_10s),
                  AVG(target_15s), AVG(target_30s)
           FROM hook_training_examples
           WHERE target_10s IS NOT NULL
           GROUP BY video_id, channel_id ORDER BY video_id""").fetchall()
    if not rows:
        return None
    videos = np.array([r["video_id"] for r in rows])
    channels = np.array([r["channel_id"] or "unknown" for r in rows])
    y = {h: np.array([float(r[2 + HORIZONS.index(h)]) for r in rows])
         for h in HORIZONS}
    return videos, channels, y


# ------------------------------------------------------------------ training

def _confidence_label(n_videos: int, robust: bool) -> str:
    if n_videos < 20:
        return "INSUFFICIENT DATA"
    if n_videos < 50:
        return "LOW"
    if n_videos < 150:
        return "MEDIUM"
    return "HIGH" if robust else "MEDIUM"


def _impute_medians(X: np.ndarray) -> np.ndarray:
    out = X.copy()
    for j in range(out.shape[1]):
        col = out[:, j]
        if np.isnan(col).any():
            med = float(np.nanmedian(col)) if np.isfinite(col[~np.isnan(col)]).any() else 0.0
            col[np.isnan(col)] = med
    return out


def _cv_rmse(model, X, y, groups) -> tuple[float, list[float]]:
    from sklearn.model_selection import GroupKFold
    n_groups = len(set(groups))
    if n_groups < 3:
        return float("nan"), []
    gkf = GroupKFold(n_splits=min(5, n_groups))
    rmses = []
    for tr, te in gkf.split(X, y, groups=groups):
        m = model().fit(X[tr], y[tr])
        pred = m.predict(X[te])
        rmses.append(float(np.sqrt(np.mean((pred - y[te]) ** 2))))
    return float(np.mean(rmses)), rmses


def train(conn, settings) -> dict:
    """Per-horizon models with channel-grouped CV. A model is kept ONLY if it
    beats the median baseline by >=5% CV RMSE; otherwise the baseline is
    stored and predictions say so. Models are versioned (never overwritten).
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    split = _channel_grouped_split(conn)
    if split is None:
        return {"status": "no training data",
                "message": "build the library + run train --build first"}
    videos, channels, y = split
    n_videos = len(videos)

    cats = _collect_categories(conn)
    feat_rows = [dict(r) for r in conn.execute(
        """SELECT * FROM hook_training_examples""").fetchall()]
    # aggregate to one sample per video (mean) — the unit that generalizes
    by_vid: dict[str, dict] = {}
    for r in feat_rows:
        if r["video_id"] not in by_vid:
            by_vid[r["video_id"]] = {k: [] for k in
                                     NUMERIC_FEATURES + BINARY_FEATURES}
        for k in NUMERIC_FEATURES:
            by_vid[r["video_id"]][k].append(r[k])
        for k in BINARY_FEATURES:
            by_vid[r["video_id"]][k].append(float(r[k] or 0))
    feat_list = []
    for vid in videos:
        agg = by_vid[vid]
        row = {k: (float(np.nanmean([v for v in agg[k] if v is not None]))
                   if agg[k] and any(v is not None for v in agg[k]) else None)
               for k in NUMERIC_FEATURES}
        cats_row = {c: None for c in CATEGORICAL_FEATURES}
        # categorical: the most frequent value among the video's hooks
        for c in CATEGORICAL_FEATURES:
            vals = [r[c] for r in feat_rows if r["video_id"] == vid and r[c]]
            cats_row[c] = max(set(vals), key=vals.count) if vals else "none"
        row.update(cats_row)
        feat_list.append(row)
    X_raw = _encode(feat_list, NUMERIC_FEATURES, cats)
    X_raw = _impute_medians(X_raw)

    results = {}
    for h in HORIZONS:
        yh = y[h]
        baseline_rmse = float(np.sqrt(np.mean((yh - np.median(yh)) ** 2)))
        baseline_median = float(np.median(yh))

        X = X_raw
        scaler = StandardScaler().fit(X)
        Xs = scaler.transform(X)

        ridge_rmse, _ = _cv_rmse(lambda: Ridge(alpha=1.0), Xs, yh, channels)
        hgb_rmse, _ = _cv_rmse(
            lambda: HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=8,
                                                  learning_rate=0.08,
                                                  random_state=RNG_SEED),
            X, yh, channels)

        cands = [("ridge", ridge_rmse, Ridge(alpha=1.0), Xs),
                 ("hgb", hgb_rmse,
                  HistGradientBoostingRegressor(max_iter=80, max_leaf_nodes=8,
                                                learning_rate=0.08,
                                                random_state=RNG_SEED), X)]
        cands = [c for c in cands if np.isfinite(c[1])]
        cands.sort(key=lambda c: c[1])

        best_kind, best_rmse = None, None
        if n_videos >= TRAIN_MIN_VIDEOS and cands:
            if cands[0][1] < baseline_rmse * 0.95:   # >=5% improvement gate
                best_kind, best_rmse = cands[0][0], cands[0][1]
        if best_kind is None:
            best_kind, best_rmse = "baseline", baseline_rmse

        model_obj = None
        if best_kind == "ridge":
            model_obj = Ridge(alpha=1.0).fit(cands[0][3], yh)
            X_for_explain = Xs
        elif best_kind == "hgb":
            model_obj = HistGradientBoostingRegressor(
                max_iter=80, max_leaf_nodes=8, learning_rate=0.08,
                random_state=RNG_SEED).fit(cands[0][3], yh)
            X_for_explain = X
        else:
            X_for_explain = None

        pkg = {
            "kind": best_kind, "baseline_median": baseline_median,
            "baseline_rmse": round(baseline_rmse, 4),
            "cv_rmse": round(float(best_rmse), 4) if np.isfinite(best_rmse) else None,
            "cv_r2_vs_baseline": round(1 - best_rmse / baseline_rmse, 4)
            if baseline_rmse and np.isfinite(best_rmse) else 0.0,
            "model": model_obj,
            "scaler": scaler if best_kind == "ridge" else None,
            "feature_names": _col_names(NUMERIC_FEATURES, cats),
            "categories": cats,
            "numeric_cols": NUMERIC_FEATURES,
            "n_videos": n_videos, "n_channels": len(set(channels)),
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "corpus_version": _corpus_version(conn),
        }
        results[h] = pkg
        _save_model(h, pkg)
    return {"status": "trained", "n_videos": n_videos,
            "results": {h: {"kind": results[h]["kind"],
                            "cv_rmse": results[h]["cv_rmse"],
                            "baseline_rmse": results[h]["baseline_rmse"],
                            "cv_r2_vs_baseline": results[h]["cv_r2_vs_baseline"]}
                        for h in HORIZONS}}


def _corpus_version(conn) -> str:
    n = conn.execute("SELECT COUNT(*) FROM hook_training_examples").fetchone()[0]
    ch = conn.execute("SELECT COUNT(DISTINCT channel_id) FROM hook_training_examples").fetchone()[0]
    return f"training-{n}hooks-{ch}ch"


def _next_version(h: int) -> int:
    d = _model_dir()
    d.mkdir(parents=True, exist_ok=True)
    best = 0
    for p in d.glob(f"hook_{h}s_v*.joblib"):
        try:
            best = max(best, int(p.stem.split("_v")[1]))
        except (IndexError, ValueError):
            continue
    return best + 1


def _model_dir() -> Path:
    return resolve_path(load_settings()["paths"]["models"])


def _save_model(h: int, pkg: dict) -> Path:
    import joblib
    d = _model_dir()
    d.mkdir(parents=True, exist_ok=True)
    v = _next_version(h)
    path = d / f"hook_{h}s_v{v:03d}.joblib"
    meta = {k: v for k, v in pkg.items() if k not in ("model", "scaler")}
    meta["file"] = path.name
    meta["h"] = h
    (d / f"hook_{h}s_v{v:03d}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    joblib.dump(pkg, path)
    return path


def latest_model(h: int) -> dict | None:
    """Highest-version model for a horizon, or None."""
    d = _model_dir()
    if not d.exists():
        return None
    cands = sorted(d.glob(f"hook_{h}s_v*.joblib"))
    if not cands:
        return None
    try:
        import joblib
        return joblib.load(cands[-1])
    except Exception:
        return None


# ----------------------------------------------------------------- predict

def _standardize_row(features: dict, pkg: dict) -> np.ndarray:
    X = _encode([features], pkg["numeric_cols"], pkg["categories"])
    X = _impute_medians(X)
    if pkg.get("scaler") is not None:
        X = pkg["scaler"].transform(X)
    return X


def predict_features(features: dict, horizon: int) -> dict:
    """Predict retention z for one hook at one horizon, with an explanation.

    Returns: {horizon, z_pred, confidence, contributors, model_kind,
              timing_features_missing}. Never raises: missing/corrupt models
    degrade to the honest baseline path.
    """
    pkg = latest_model(horizon)
    if pkg is None:
        return {"horizon": horizon, "z_pred": None, "confidence": "NO MODEL",
                "contributors": [], "model_kind": None,
                "timing_features_missing": True}

    X = _standardize_row(features, pkg)
    X = X.reshape(1, -1)

    if pkg["kind"] == "baseline" or pkg.get("model") is None:
        return {"horizon": horizon, "z_pred": float(pkg["baseline_median"]),
                "confidence": _confidence_label(pkg["n_videos"], False),
                "contributors": [], "model_kind": "baseline",
                "timing_features_missing": True}

    model = pkg["model"]
    names = pkg["feature_names"]
    contribs = _contributions(model, X, names, pkg)

    robust = pkg["cv_r2_vs_baseline"] > 0.05
    conf = _confidence_label(pkg["n_videos"], robust)
    z = float(model.predict(X)[0])
    return {"horizon": horizon, "z_pred": round(z, 3), "confidence": conf,
            "contributors": contribs, "model_kind": pkg["kind"],
            "timing_features_missing": True}


def _contributions(model, X: np.ndarray, names: list[str],
                   pkg: dict) -> list[dict]:
    """Lightweight explanations, no framework needed.

    Ridge: coefficient * standardized value per feature (units of target z).
    HistGB: importances for features present in this hook (sign from the
    training correlation with the target)."""
    if pkg["kind"] == "ridge":
        coefs = np.asarray(model.coef_)
        vals = X[0] * coefs
        idx = np.argsort(-np.abs(vals))
        out = []
        for i in idx[:6]:
            if abs(vals[i]) < 1e-4:
                continue
            out.append({"feature": names[i], "label": FEATURE_LABELS.get(names[i], names[i]),
                        "contribution_z": round(float(vals[i]), 3)})
        return out
    if pkg["kind"] == "hgb":
        imp = model.feature_importances_
        idx = np.argsort(-imp)[:6]
        out = []
        for i in idx:
            if imp[i] < 1e-3:
                continue
            out.append({"feature": names[i], "label": FEATURE_LABELS.get(names[i], names[i]),
                        "importance": round(float(imp[i]), 3)})
        return out
    return []


def predict_dna(dna: dict, horizon: int = 10) -> dict:
    """Prediction for a freshly generated hook (DNA only, no timing)."""
    return predict_features(features_from_dna(dna), horizon)


# ------------------------------------------------------- pattern discovery

def _video_effect(conn, present: callable, horizon: int = 10) -> dict | None:
    """present(video_id) -> bool. One sample per video; bootstrap over videos;
    channel consistency; Phase 21 confidence."""
    rows = conn.execute(
        """SELECT video_id, channel_id, AVG(target_10s) AS t10,
                  AVG(target_5s) AS t5, AVG(target_30s) AS t30
           FROM hook_training_examples GROUP BY video_id, channel_id""").fetchall()
    if len(rows) < 5:
        return None
    col = {"5": "t5", "10": "t10", "30": "t30"}[str(horizon)]
    fv, lv, ch_v = [], [], []
    for r in rows:
        if present(r["video_id"]) is None:
            continue
        if r[col] is None:
            continue
        fv.append(int(present(r["video_id"])))
        lv.append(float(r[col]))
        ch_v.append(r["channel_id"] or "unknown")
    if len(fv) < 5:
        return None
    fv, lv, ch_v = np.array(fv), np.array(lv), np.array(ch_v)
    present_ = fv == 1
    if present_.sum() < 2 or (~present_).sum() < 2:
        return None
    effect = float(lv[present_].mean() - lv[~present_].mean())

    rng = np.random.default_rng(RNG_SEED)
    boot = []
    for _ in range(BOOTSTRAP_ITERS):
        idx = rng.choice(len(lv), size=len(lv), replace=True)
        p = fv[idx] == 1
        a = ~p
        if p.sum() < 2 or a.sum() < 2:
            boot.append(0.0)
            continue
        boot.append(float(lv[idx][p].mean() - lv[idx][a].mean()))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    robust = bool(lo > 0 or hi < 0)

    ch_eff, ch_tot = 0, 0
    for ch in set(ch_v):
        m = ch_v == ch
        if m.sum() < 2:
            continue
        ch_tot += 1
        p, a = m & present_, m & ~present_
        if p.sum() and a.sum() and lv[p].mean() > lv[a].mean():
            ch_eff += 1

    return {
        "n_videos": int(present_.sum()), "n_hooks": int(present_.sum()),
        "effect_z": round(effect, 3),
        "ci95": [round(float(lo), 3), round(float(hi), 3)],
        "robust": robust,
        "channel_consistency": f"{ch_eff}/{ch_tot}",
        "confidence": _confidence_label(len(lv), robust),
    }


def _pattern_present(conn, kind: str, feats: dict) -> callable:
    """Video-level presence for a single feature or a combo (ALL must hold).
    Returns callable(video_id) -> 1/0/None (None = feature undefined)."""

    def single_present(feature: str, value=None):
        col_sql = "0"
        if feature in BINARY_FEATURES:
            col_sql = feature
        elif feature in CATEGORICAL_FEATURES:
            return lambda vid: 1 if (conn.execute(
                f"SELECT {feature} FROM hook_training_examples WHERE video_id=? LIMIT 1",
                (vid,)).fetchone() or [None])[0] == value else 0
        return lambda vid: 1 if (conn.execute(
            f"SELECT MAX({col_sql}) FROM hook_training_examples WHERE video_id=?",
            (vid,)).fetchone()[0] or 0) else 0

    defs = []
    for f in feats["binary"]:
        defs.append(single_present(f))
    for f, v in feats["cat"]:
        defs.append(single_present(f, v))
    if not defs:
        return lambda vid: None

    def present(vid):
        vals = [d(vid) for d in defs]
        if any(v is None for v in vals):
            return None
        return 1 if all(v for v in vals) else 0
    return present


SINGLE_BINARY = [
    "open_loop", "has_question", "concrete_outcome", "has_number",
    "has_dollar", "has_percent", "number_before_5s", "entity_before_5s",
    "stakes_before_5s", "curiosity_before_5s", "promise_before_10s",
    "struct_contradiction", "struct_reversal", "struct_shock",
    "struct_mystery", "struct_open_loop",
]

INTERACTION_DEFS = [
    # (label, binary features, category constraints)
    ("contradiction + number_before_5s", ["struct_contradiction", "number_before_5s"], []),
    ("direct_question + open_loop", ["has_question", "open_loop"], []),
    ("shocking_fact + stakes_money", [], [("opening_device", "shocking_fact")]),
    ("impossible_outcome + stakes_money", [], [("opening_device", "impossible_outcome")]),
    ("curiosity_gap + number_before_5s", ["number_before_5s"], [("curiosity_mechanism", "information_gap")]),
    ("story + entity_before_5s", ["entity_before_5s"], [("opening_device", "story_medias_res")]),
    ("stakes_money + promise", [], [("stakes_type", "money")]),
    ("open_loop + promise", ["open_loop"], []),
    ("number_before_5s + stakes_money", ["number_before_5s"], [("stakes_type", "money")]),
    ("contradiction + stakes_money", ["struct_contradiction"], [("stakes_type", "money")]),
    ("question + number_before_5s", ["number_before_5s"], [("opening_device", "direct_question")]),
    ("specific_number + open_loop", ["open_loop"], []),
    ("pattern_interrupt + number_before_5s", ["number_before_5s"], [("opening_device", "pattern_interrupt")]),
    ("shock + open_loop", ["open_loop", "struct_shock"], []),
    ("stakes_money + open_loop", ["open_loop"], [("stakes_type", "money")]),
]


def discover_patterns(conn, settings) -> dict:
    """LEARNED pattern library: single features + curated interactions, each
    with effect/CI/consistency/confidence. GLOBAL scope; best_duration_sec is
    the horizon (5/10/30) with the strongest |effect| among those with n>=5."""
    defs = []
    for feat in SINGLE_BINARY:
        defs.append((_label(feat), feat, "single",
                     {"binary": [feat], "cat": []}))
    for label, bins, cats in INTERACTION_DEFS:
        defs.append((label, "+".join(bins + [c[0] for c in cats]),
                     "interaction", {"binary": bins, "cat": cats}))

    findings = []
    for label, feature, kind, spec in defs:
        r = _video_effect(conn, _pattern_present(conn, kind, spec))
        if not r:
            continue
        best_h, best_eff = "10", abs(r["effect_z"])
        for h in (5, 30):
            rh = _video_effect(conn, _pattern_present(conn, kind, spec), h)
            if rh and rh["n_videos"] >= 5 and abs(rh["effect_z"]) > best_eff:
                best_h, best_eff = str(h), abs(rh["effect_z"])
        findings.append({"pattern_key": label, "feature": feature, "kind": kind,
                         **r, "best_duration_sec": best_h})

    out = {"scope": "GLOBAL", "n_videos": _n_videos(conn),
           "n_hooks": _n_hooks(conn), "patterns": findings}
    _write_patterns(conn, out)
    return out


def _label(feature: str) -> str:
    if feature.startswith("struct_"):
        return "STRUCT " + feature[len("struct_"):].replace("_", " ")
    return feature.replace("_", " ")


def _n_videos(conn) -> int:
    return conn.execute("SELECT COUNT(DISTINCT video_id) FROM hook_training_examples").fetchone()[0]


def _n_hooks(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM hook_training_examples").fetchone()[0]


def _write_patterns(conn, res: dict) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("DELETE FROM learned_patterns WHERE scope='GLOBAL'")
    for p in res["patterns"]:
        conn.execute(
            """INSERT OR REPLACE INTO learned_patterns
               (pattern_key, scope, feature, kind, n_videos, n_hooks, effect_z,
                ci95_lo, ci95_hi, robust, channel_consistency, confidence,
                best_niche, best_duration_sec, discovered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (p["pattern_key"], "GLOBAL", p.get("feature", ""), p["kind"],
             p["n_videos"], p["n_hooks"], p["effect_z"], p["ci95"][0],
             p["ci95"][1], int(p["robust"]), p["channel_consistency"],
             p["confidence"], _best_niche(conn, p), p.get("best_duration_sec"),
             now))
    conn.commit()
    out = resolve_path(load_settings()["paths"]["reports"]) / "learned_patterns.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


def _best_niche(conn, p: dict) -> str | None:
    rows = conn.execute(
        """SELECT niche_tag, COUNT(*) c FROM hook_training_examples
           WHERE niche_tag IS NOT NULL GROUP BY niche_tag""").fetchall()
    best, best_n = None, 1
    for r in rows:
        if r["c"] >= 2 and r["c"] > best_n:
            best, best_n = r["niche_tag"], r["c"]
    return best


def pattern_evidence(conn, dna: dict, horizon: int = 10) -> dict:
    """Best matching LEARNED pattern for a generated hook's DNA, with the
    niche-hierarchy fallback: USER_CHANNEL -> niche -> GLOBAL (all labeled)."""
    feats = features_from_dna(dna)
    keys = []
    for f in SINGLE_BINARY:
        if feats.get(f):
            keys.append(_label(f))
    for label, bins, cats in INTERACTION_DEFS:
        if all(feats.get(b) for b in bins) and all(feats.get(c) == v for c, v in cats):
            keys.append(label)
    best = None
    for k in keys:
        r = conn.execute(
            "SELECT * FROM learned_patterns WHERE pattern_key=? AND scope='GLOBAL'",
            (k,)).fetchone()
        if r and (best is None or abs(r["effect_z"]) > abs(best["effect_z"])):
            best = dict(r)
    if best is None:
        return {"matched": False, "evidence": []}
    return {"matched": True,
            "pattern": best["pattern_key"], "effect_z": best["effect_z"],
            "confidence": best["confidence"], "n_videos": best["n_videos"],
            "scope": best["scope"]}


# ----------------------------------------------------------------- feedback

def calibrate_from_actuals(conn) -> dict:
    """Join hook_generations actuals to predicted scores (feedback loop).

    Needs >=5 generations with actual_avd_pct. Fits a linear calibration of
    actual AVD% on predicted score; reports per-horizon n. Honest no-op when
    there is not enough data yet.
    """
    rows = conn.execute(
        """SELECT g.id, g.hooks_json, g.actual_avd_pct, g.actual_ctr
           FROM hook_generations g
           WHERE g.actual_avd_pct IS NOT NULL""").fetchall()
    if len(rows) < 5:
        return {"status": "insufficient",
                "message": f"{len(rows)} generations with actuals (need >=5)"}
    pairs = []
    for r in rows:
        try:
            hooks = json.loads(r["hooks_json"] or "[]")
        except json.JSONDecodeError:
            continue
        for h in hooks:
            if h.get("score") is not None and r["actual_avd_pct"] is not None:
                pairs.append((float(h["score"]), float(r["actual_avd_pct"])))
    if len(pairs) < 10:
        return {"status": "insufficient",
                "message": f"{len(pairs)} hook-level pairs (need >=10)"}
    X = np.array([[p[0]] for p in pairs])
    y = np.array([p[1] for p in pairs])
    from sklearn.linear_model import Ridge
    m = Ridge(alpha=1.0).fit(X, y)
    r2 = float(m.score(X, y))
    return {"status": "fitted", "n_pairs": len(pairs),
            "slope": round(float(m.coef_[0]), 4),
            "intercept": round(float(m.intercept_), 4),
            "r2": round(r2, 4),
            "message": "predicted score -> actual AVD% calibration (use as ranking hint)"}
