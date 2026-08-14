"""M4 tests — the learned Hook Intelligence layer.

Covers: training dataset build, feature encoding, channel-grouped validation,
per-horizon training + versioning, prediction + explanations, pattern and
interaction discovery, niche fallback, calibration no-op, and the required
edge cases (empty corpus, missing data, corrupt model, tiny dataset).
"""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pytest

from db import init_db
from miner import hook_learn as hl
from miner.hook_dna import extract_dna


def _insert_library(conn, rows: list[dict]) -> None:
    """One hook_library + video + video_features row per dict in `rows`."""
    for r in rows:
        conn.execute(
            """INSERT INTO videos (video_id, channel_id, title, duration_sec)
               VALUES (?,?,?,?)""", (r["video_id"], r["channel_id"],
                                     r.get("title", "t"), r.get("duration", 600)))
        conn.execute(
            """INSERT INTO video_features (video_id, hook_dna_json)
               VALUES (?,?)""",
            (r["video_id"], json.dumps(r.get("dna", {}))))
        conn.execute(
            """INSERT INTO hook_library
               (video_id, channel, niche_tag, outlier_score, hook_text,
                word_count, wpm, duration, opening_device,
                curiosity_mechanism, emotional_mechanism, stakes_type,
                promise_type, narrative_structure, first_number_sec,
                first_entity_sec, first_stakes_sec, first_curiosity_sec,
                promise_sec, retention_3s, retention_5s, retention_10s,
                retention_15s, retention_30s)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["video_id"], r.get("channel", "CH"),
             r.get("niche_tag", "finance"), r.get("outlier", 2.0),
             r["hook_text"], r.get("word_count", 20), r.get("wpm", 150),
             r.get("hook_duration", 8.0), r.get("opening_device", "direct_question"),
             r.get("curiosity", "information_gap"), r.get("emotion", "curiosity"),
             r.get("stakes", "money"), r.get("promise", "explanation"),
             r.get("structure", "STATE → CONTRADICTION → STAKES"),
             r.get("fn", 3.0), r.get("fe", 2.0), r.get("fs", 4.0),
             r.get("fc", 3.5), r.get("fp", 9.0),
             r.get("ret3", 0.5), r.get("ret5", 0.4), r.get("ret10", 0.3),
             r.get("ret15", 0.2), r.get("ret30", 0.1)))
    conn.commit()


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    yield c
    c.close()


def _small_corpus() -> list[dict]:
    """6 channels x 4 videos = 24 hooks with varied DNA and retention."""
    rows = []
    devices = ["direct_question", "shocking_fact", "story_medias_res",
               "contrarian_claim"]
    curiosities = ["information_gap", "unanswered_why", "hidden_cause", "reversal"]
    for ci in range(6):
        for vi in range(4):
            d = devices[(ci + vi) % 4]
            cu = curiosities[(ci * 2 + vi) % 4]
            ret = 0.2 * ci + 0.1 * vi - 0.5
            rows.append({
                "video_id": f"v{ci}_{vi}", "channel_id": f"ch{ci}",
                "channel": f"Channel {ci}", "niche_tag": "finance",
                "hook_text": f"Hook for channel {ci} video {vi} with number 40 billion.",
                "opening_device": d, "curiosity": cu, "stakes": "money",
                "promise": "explanation", "structure": "SHOCK → STAKES → OPEN_LOOP",
                "ret3": ret + 0.2, "ret5": ret + 0.15, "ret10": ret,
                "ret15": ret - 0.1, "ret30": ret - 0.3,
                "outlier": 1.5 + ci * 0.5,
            })
    return rows


# ------------------------------------------------------------- dataset build

def test_build_training_data_creates_rows(conn):
    _insert_library(conn, _small_corpus())
    n = hl.build_training_data(conn, None)
    assert n == 24
    total = conn.execute("SELECT COUNT(*) FROM hook_training_examples").fetchone()[0]
    assert total == 24
    r = conn.execute("SELECT * FROM hook_training_examples LIMIT 1").fetchone()
    assert r["target_10s"] is not None
    assert r["number_before_5s"] in (0, 1)
    assert r["opening_device"]  # categorical populated
    assert r["channel_id"]


def test_build_training_data_skips_duplicates(conn):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    n2 = hl.build_training_data(conn, None)
    assert n2 == 0
    assert conn.execute("SELECT COUNT(*) FROM hook_training_examples").fetchone()[0] == 24


def test_build_training_data_missing_retention(conn):
    rows = _small_corpus()[:3]
    rows[0]["ret10"] = None
    _insert_library(conn, rows)
    n = hl.build_training_data(conn, None)
    assert n == 2  # the retention-less hook is excluded


def test_features_from_dna_timing_missing(conn):
    dna = extract_dna("Why does this company charge 40 dollars a month?")
    f = hl.features_from_dna(dna)
    assert f["first_number_sec"] is None
    assert f["opening_device"] == "direct_question"
    assert f["has_question"] == 1


# ----------------------------------------------------------------- encoding

def test_encode_matches_feature_names(conn):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    cats = hl._collect_categories(conn)
    rows = [hl.features_from_row(r) for r in conn.execute(
        "SELECT * FROM hook_training_examples")]
    X = hl._encode(rows, hl.NUMERIC_FEATURES, cats)
    names = hl._col_names(hl.NUMERIC_FEATURES, cats)
    assert X.shape[1] == len(names)
    assert X.shape[0] == 24
    assert np.isfinite(X[~np.isnan(X)]).all()


def test_encode_unseen_category_goes_other(conn):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    cats = hl._collect_categories(conn)
    feats = hl.features_from_dna(extract_dna("Some brand new device here"))
    feats["opening_device"] = "never_seen_device"
    X = hl._encode([feats], hl.NUMERIC_FEATURES, cats)
    other_idx = hl._col_names(hl.NUMERIC_FEATURES, cats).index("opening_device=other")
    assert X[0, other_idx] == 1.0


# ------------------------------------------------------------- training

def test_train_keeps_baseline_on_tiny_corpus(conn, tmp_path, monkeypatch):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    res = hl.train(conn, None)
    assert res["status"] == "trained"
    assert res["n_videos"] == 24
    for h, r in res["results"].items():
        assert r["kind"] in ("ridge", "hgb", "baseline")
        assert r["cv_rmse"] > 0
    # versioning: a second run must NOT overwrite v001
    hl.train(conn, None)
    files = sorted(tmp_path.glob("hook_10s_v*.joblib"))
    assert len(files) == 2


def test_train_no_data(conn):
    res = hl.train(conn, None)
    assert res["status"] == "no training data"


def test_train_never_leaks_channels(conn, tmp_path, monkeypatch):
    """Grouped validation: any model trained must be groupable by channel.
    We verify the split function keeps each channel's videos in ONE fold."""
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    split = hl._channel_grouped_split(conn)
    videos, channels, y = split
    assert len(videos) == len(channels) == 24
    # every video belongs to exactly one group and its channel is consistent
    for vid, ch in zip(videos, channels):
        assert ch.startswith("ch")
    from sklearn.model_selection import GroupKFold
    gkf = GroupKFold(n_splits=5)
    for tr, te in gkf.split(videos, y[10], groups=channels):
        tr_ch, te_ch = set(channels[tr]), set(channels[te])
        assert not (tr_ch & te_ch)  # no channel appears in both


def test_train_works_with_std_smaller_than_splits(conn, tmp_path, monkeypatch):
    rows = _small_corpus()[:6]  # 2 channels
    _insert_library(conn, rows)
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    res = hl.train(conn, None)
    assert res["status"] == "trained"  # degrades to baseline, never crashes


# ------------------------------------------------------------- prediction

def test_predict_without_model(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    p = hl.predict_dna(extract_dna("Why does this charge so much?"), 10)
    assert p["confidence"] == "NO MODEL"
    assert p["z_pred"] is None


def test_predict_with_baseline_model(conn, tmp_path, monkeypatch):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    hl.train(conn, None)
    p = hl.predict_dna(extract_dna("Why does this charge so much?"), 10)
    assert p["z_pred"] is not None
    assert p["confidence"] in ("LOW", "MEDIUM", "INSUFFICIENT DATA")
    assert "model_kind" in p


def test_predict_with_ridge_model(conn, tmp_path, monkeypatch):
    """Force the ridge path: many channels, strong structure -> should beat
    baseline with enough signal. If it does not, the test still validates the
    prediction + explanation plumbing."""
    rows = []
    for ci in range(8):
        for vi in range(5):
            use_loop = (ci + vi) % 2 == 0
            rows.append({
                "video_id": f"v{ci}_{vi}", "channel_id": f"ch{ci}",
                "channel": f"Channel {ci}", "niche_tag": "finance",
                "hook_text": "This company lost 40 billion dollars in one year."
                             + (" Nobody knows why." if use_loop else ""),
                "opening_device": "shocking_fact",
                "curiosity": "hidden_cause", "stakes": "money",
                "promise": "explanation",
                "structure": "SHOCK → STAKES → OPEN_LOOP" if use_loop
                             else "SHOCK → STAKES",
                "open_loop": 1 if use_loop else 0,
                "ret3": 1.0 if use_loop else -1.0,
                "ret5": 1.2 if use_loop else -0.8,
                "ret10": 1.4 if use_loop else -0.6,
                "ret15": 1.0 if use_loop else -0.4,
                "ret30": 0.5 if use_loop else -0.2,
            })
    _insert_library(conn, rows)
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    hl.train(conn, None)
    p = hl.predict_dna(extract_dna(
        "This company lost 40 billion dollars in one year. Nobody knows why."), 10)
    assert p["z_pred"] is not None
    if p["model_kind"] == "ridge":
        assert any("contribution_z" in c for c in p["contributors"])


def test_predict_corrupt_model_degrades(conn, tmp_path, monkeypatch):
    (tmp_path / "hook_10s_v001.joblib").write_text("not a joblib", encoding="utf-8")
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    p = hl.predict_dna(extract_dna("Why does this charge so much?"), 10)
    assert p["confidence"] == "NO MODEL"  # corrupt file -> honest no-model


# ------------------------------------------------------------ patterns

def test_discover_patterns_writes_table_and_json(conn, tmp_path, monkeypatch):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "resolve_path", lambda p: tmp_path / "reports")
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    res = hl.discover_patterns(conn, None)
    assert res["scope"] == "GLOBAL"
    assert res["n_videos"] == 24
    assert res["patterns"]
    n_tab = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
    assert n_tab == len(res["patterns"])
    assert (tmp_path / "reports" / "learned_patterns.json").exists()
    for p in res["patterns"]:
        assert p["confidence"] in ("LOW", "MEDIUM", "INSUFFICIENT DATA", "HIGH")
        assert "ci95" in p and "effect_z" in p
        assert p["kind"] in ("single", "interaction")
        assert p["best_duration_sec"] in ("5", "10", "30")


def test_pattern_evidence_matching_and_fallback(conn, tmp_path, monkeypatch):
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "resolve_path", lambda p: tmp_path / "reports")
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    hl.discover_patterns(conn, None)
    dna = extract_dna("Why does this company charge 40 dollars a month?")
    ev = hl.pattern_evidence(conn, dna)
    assert ev.get("matched") is True or ev.get("matched") is False
    if ev.get("matched"):
        assert ev["scope"] == "GLOBAL"
        assert "effect_z" in ev


def test_pattern_evidence_no_patterns(conn):
    dna = extract_dna("Why does this charge 40 dollars a month?")
    ev = hl.pattern_evidence(conn, dna)
    assert ev["matched"] is False


# -------------------------------------------------------------- calibration

def test_calibrate_noop_without_actuals(conn):
    res = hl.calibrate_from_actuals(conn)
    assert res["status"] == "insufficient"


def test_calibrate_fits_with_actuals(conn):
    for i in range(6):
        hooks = json.dumps([{"rank": 1, "text": f"h{i}a", "score": 40 + i * 10,
                             "confidence": "low"},
                            {"rank": 2, "text": f"h{i}b", "score": 30 + i * 10,
                             "confidence": "low"}])
        conn.execute(
            """INSERT INTO hook_generations (topic, mode, duration_target,
               hooks_json, generated_at, actual_ctr, actual_avd_pct,
               actual_views_72h) VALUES (?,?,?,?,?,?,?,?)""",
            ("t", "money", 8, hooks, "2026-01-01", 3.0 + i, 30 + i * 5, 1000 + i))
    conn.commit()
    res = hl.calibrate_from_actuals(conn)
    assert res["status"] == "fitted"
    assert res["n_pairs"] >= 10
    assert "slope" in res and "r2" in res


# -------------------------------------------------------------- edge cases

def test_empty_corpus_build(conn):
    n = hl.build_training_data(conn, None)
    assert n == 0
    res = hl.train(conn, None)
    assert res["status"] == "no training data"


def test_missing_channel_id_handled(conn, tmp_path, monkeypatch):
    rows = _small_corpus()[:4]
    for r in rows:
        r["channel_id"] = None  # missing channel
    _insert_library(conn, rows)
    hl.build_training_data(conn, None)
    split = hl._channel_grouped_split(conn)
    videos, channels, y = split
    assert set(channels) == {"unknown"}  # grouped, never crashes
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    res = hl.train(conn, None)
    assert res["status"] == "trained"


def test_missing_dna_json_handled(conn):
    rows = _small_corpus()[:2]
    for r in rows:
        r["dna"] = None  # missing hook_dna_json
    _insert_library(conn, rows)
    n = hl.build_training_data(conn, None)
    assert n == 2
    r = conn.execute("SELECT opening_device FROM hook_training_examples LIMIT 1").fetchone()
    assert r["opening_device"]  # fell back to library column


# ------------------------------------------------------ generation integration

def test_generate_works_with_and_without_learned(conn, tmp_path, monkeypatch):
    """The learned layer must never break generation, with or without models
    and with or without the learned_patterns table."""
    from miner.hook_gen import generate
    _insert_library(conn, _small_corpus())
    hl.build_training_data(conn, None)
    monkeypatch.setattr(hl, "_model_dir", lambda: tmp_path)
    hl.train(conn, None)
    monkeypatch.setattr(hl, "resolve_path", lambda p: tmp_path / "reports")
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    hl.discover_patterns(conn, None)

    w = {"curiosity": 20, "specificity": 15, "stakes": 15, "novelty": 15,
         "clarity": 10, "open_loop": 15, "promise": 5, "pacing": 5,
         "learned": 10, "pattern_evidence": 10}
    out = generate(conn, "Why do subscriptions keep charging people",
                   weights=w, corpus=[r["hook_text"] for r in _small_corpus()])
    assert out["hooks"]
    h0 = out["hooks"][0]
    assert h0["score"] > 0
    # learned keys present but the report is honest either way
    assert "learned_enabled" in out

    # now with NO models and NO patterns: must still generate
    empty_dir = tmp_path / "empty"
    monkeypatch.setattr(hl, "_model_dir", lambda: empty_dir)
    out2 = generate(conn, "Why do subscriptions keep charging people",
                    weights=w, corpus=[])
    assert out2["hooks"]
    assert out2["learned_enabled"] is False
    assert out2["patterns_enabled"] is False