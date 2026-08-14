"""Tests for miner.hook_gen — scoring, novelty, mutation, factuality,
multi-length fitting, and the full generation pipeline.

The pipeline needs a DB connection (reads evidence). Tests use an in-memory
sqlite DB with the hook_library schema so generate() runs end-to-end.
"""
import sqlite3

import pytest

from miner.hook_gen import (FACT_PATTERNS, PATTERNS, _dedup, _quality_filter,
                            fit_length, generate, hook_score, mutate,
                            nominal_topic, tag_factuality)
from miner.hook_dna import extract_dna


# ------------------------------------------------------------------ fixtures

def _mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT, channel TEXT,
            published_at TEXT, duration_sec REAL, view_count INTEGER,
            niche_tag TEXT, outlier_score REAL, transcript TEXT,
            hook TEXT, hook_dna_json TEXT);
        CREATE TABLE heatmaps (
            video_id TEXT PRIMARY KEY, points_json TEXT, fetched_at TEXT);
        CREATE TABLE hook_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE, hook_text TEXT, archetype TEXT,
            opening_device TEXT, curiosity_mechanism TEXT,
            emotional_mechanism TEXT, stakes_type TEXT, promise_type TEXT,
            narrative_structure TEXT, word_count INTEGER,
            first_number_sec REAL, first_stakes_sec REAL, promise_sec REAL,
            retention_1s REAL, retention_3s REAL, retention_5s REAL,
            retention_10s REAL, retention_15s REAL, retention_20s REAL,
            retention_30s REAL, early_retention REAL, retention_slope REAL,
            retention_drop REAL, retention_recovery REAL, peak_retention REAL,
            peak_sec REAL, volatility REAL, outlier_score REAL,
            first_entity_sec REAL, first_curiosity_sec REAL,
            first_promise_sec REAL, first_question_sec REAL,
            embedding BLOB, niche_tag TEXT, channel TEXT, title TEXT,
            factuality_label TEXT, verified TEXT, created_at TEXT);
        CREATE TABLE hook_generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, mode TEXT,
            duration_target INTEGER, hooks_json TEXT, my_video_id TEXT,
            created_at TEXT);
    """)
    conn.execute(
        "INSERT INTO videos (video_id, title, channel, duration_sec, "
        "view_count, outlier_score) VALUES (?, ?, ?, ?, ?, ?)",
        ("vid1", "Why Ikea traps shoppers", "MagnatesMedia", 480.0, 5_000_000,
         30.0))
    conn.execute(
        "INSERT INTO hook_library (video_id, hook_text, opening_device, "
        "curiosity_mechanism, stakes_type, outlier_score, retention_10s) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("vid1", "When an innocent customer walks into Ikea they walk into a "
         "psychological trap designed to make them overspend on furniture.",
         "shocking_fact", "information_gap", "money", 30.0, 3.5))
    conn.commit()
    return conn


CONN = None


@pytest.fixture()
def conn():
    global CONN
    if CONN is None:
        CONN = _mem_conn()
    return CONN


# -------------------------------------------------------------- topic shaping

@pytest.mark.parametrize("topic,expected", [
    ("Why Lamborghini makes so much money", "Lamborghini making so much money"),
    ("Why does Planet Fitness keep charging you", "Planet Fitness charging you"),
    ("Why do software subscriptions keep getting more expensive",
     "software subscriptions getting more expensive"),
    ("How Netflix became profitable", "Netflix becoming profitable"),
    ("Adobe CS6 price hike", "adobe cs6 price hike"),
])
def test_nominal_topic(topic, expected):
    assert nominal_topic(topic) == expected


# ------------------------------------------------------------------ filters

def test_quality_filter_rejects_short():
    ok, _ = _quality_filter("Too short.", [])
    assert not ok


def test_quality_filter_rejects_clickbait():
    ok, _ = _quality_filter("You won't believe this shocking truth about money!",
                            [])
    assert not ok


def test_quality_filter_accepts_concrete_hook():
    ok, _ = _quality_filter(
        "Planet Fitness charged me eleven dollars for a month I did not use.",
        [])
    assert ok


def test_quality_filter_requires_facts_for_numbers():
    ok, _ = _quality_filter("The company lost 500 million dollars last year.",
                            [])
    assert not ok
    ok2, _ = _quality_filter("The company lost 500 million dollars last year.",
                             ["lost 500 million dollars"])
    assert ok2


def test_dedup_removes_near_duplicates():
    texts = ["Everyone thinks Netflix is profitable. It is not.",
             "Everyone thinks Netflix is profitable. It isn't.",
             "This is a totally different hook about something else entirely."]
    assert len(_dedup(texts)) == 2


# ------------------------------------------------------------------- scoring

def test_hook_score_shape_and_range():
    text = "The company was worth 40 billion dollars. Then it collapsed. Why?"
    dna = extract_dna(text)
    out = hook_score(text, dna)
    assert "score" in out and "dims" in out
    assert 0 <= out["score"] <= 100
    assert set(out["dims"]) >= {"curiosity", "specificity", "stakes",
                                "novelty", "clarity", "open_loop",
                                "promise", "pacing"}


def test_hook_score_prefers_question_over_flat():
    q = hook_score("Why does Planet Fitness keep charging you?",
                   extract_dna("Why does Planet Fitness keep charging you?"))
    flat = hook_score("Planet Fitness charges ten dollars a month.",
                      extract_dna("Planet Fitness charges ten dollars a month."))
    assert q["dims"]["open_loop"] > flat["dims"]["open_loop"]
    assert q["score"] > flat["score"]


def test_hook_score_weights_are_configurable():
    text = "The company was worth 40 billion dollars. Then it collapsed. Why?"
    dna = extract_dna(text)
    default = hook_score(text, dna)
    shock = hook_score(text, dna, {"curiosity": 0, "specificity": 100,
                                   "stakes": 0, "novelty": 0, "clarity": 0,
                                   "open_loop": 0, "promise": 0, "pacing": 0})
    assert shock["score"] != default["score"]


# ---------------------------------------------------------------- factuality

def test_tag_factuality_fact_with_user_facts():
    f = tag_factuality("Adobe made 20 billion dollars in 2023.",
                       ["made 20 billion dollars in 2023"], ["Adobe"])
    assert f["label"] == "FACT"
    assert not f["verification_required"]


def test_tag_factuality_creative_framing_without_numbers():
    f = tag_factuality("The company collapsed because of a hidden debt.",
                       [], ["The"])
    assert f["label"] == "CREATIVE_FRAMING"


def test_tag_factuality_inference_unverified_number():
    f = tag_factuality("Adobe made 20 billion dollars last year.",
                       [], ["Adobe"])
    assert f["verification_required"]
    assert f["label"] in {"INFERENCE", "CREATIVE_FRAMING"}


# ------------------------------------------------------------ multi-length

def test_fit_length_shortens_to_word_budget():
    long_hook = ("The company was worth forty billion dollars and then "
                 "everything collapsed in a single quarter and nobody "
                 "saw it coming at all.")
    out = fit_length(long_hook, 8)
    assert len(out.split()) <= 8


def test_fit_length_expands_cleanly():
    short = "Never assume the price is real."
    out = fit_length(short, 30)
    assert len(out.split()) >= 20
    assert out.startswith("Never assume the price is real")


def test_fit_length_no_midword_cuts():
    out = fit_length("One two three four five six seven eight.", 4)
    words = out.split()
    assert len(words) <= 4
    assert all(w in {"One", "two", "three", "four", "five", "six",
                     "seven", "eight"} for w in words)


# ---------------------------------------------------------------- mutation

def test_mutation_prepend_lowercases_following_word():
    out = mutate("Lamborghini making so much money is not an accident.",
                 "shocking")
    assert out.startswith("You are not ready for this. lamborghini")


def test_mutation_aliases():
    assert mutate("x is real.", "more_confrontational") == \
        mutate("x is real.", "confrontational")


def test_mutation_unknown_style_returns_original():
    assert mutate("x is real.", "nonexistent_style") == "x is real."


def test_mutation_append_handles_punctuation():
    out = mutate("This is the truth.", "money")
    assert "real money" in out
    assert ".." not in out


# ------------------------------------------------------------- full pipeline

def test_generate_returns_structured_json(conn):
    out = generate(conn, "Why Lamborghini makes so much money",
                   facts=["Lamborghini made 2.8 billion dollars in 2023"])
    assert out["topic"] == "Why Lamborghini makes so much money"
    assert len(out["hooks"]) >= 1
    h = out["hooks"][0]
    for key in ("rank", "text", "score", "curiosity", "specificity",
                "stakes", "novelty", "clarity", "open_loop", "promise",
                "pattern", "opening_device", "evidence_count", "confidence",
                "factuality", "variants", "why_it_works", "risks"):
        assert key in h
    assert h["variants"]["8"]  # multi-length variants present


def test_generate_fact_patterns_use_facts(conn):
    out = generate(conn, "Adobe CS6 price hike",
                   facts=["raised the price 50 percent"], mode="money")
    assert out["hooks"]
    # every hook must slot the fact or not claim numbers without it
    assert all(h["factuality"] in {"FACT", "CREATIVE_FRAMING"}
               or not h["verification_required"] for h in out["hooks"])


def test_generate_empty_corpus_falls_back(conn):
    out = generate(conn, "Planet Fitness subscriptions", corpus=[])
    assert out["hooks"]


def test_generate_never_returns_duplicate_text(conn):
    out = generate(conn, "Why Netflix raised prices",
                   facts=["raised prices 15 percent in 2025"])
    texts = [h["text"] for h in out["hooks"]]
    assert len(texts) == len(set(texts))


def test_patterns_and_fact_patterns_are_formattable():
    for struct, tags, templates in PATTERNS:
        assert tags  # every family must declare device tags
        for tpl in templates:
            assert "{topic}" in tpl
            tpl.format(topic="test topic")  # must not raise
    for _, templates in FACT_PATTERNS:
        for tpl in templates:
            assert "{fact}" in tpl
            tpl.format(topic="test topic", fact="made 10 billion dollars")