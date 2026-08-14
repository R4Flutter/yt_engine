"""Tests for miner.hook_retrieval — weighted retrieval + embeddings."""
import pickle
import sqlite3

import numpy as np
import pytest

from miner.hook_retrieval import (VEC_PARAMS, _dna_sim, build_embedder,
                                  cosine, embed, retrieve)


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE hook_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT, hook_text TEXT, niche_tag TEXT,
            outlier_score REAL, opening_device TEXT,
            curiosity_mechanism TEXT, emotional_mechanism TEXT,
            stakes_type TEXT, promise_type TEXT, narrative_structure TEXT,
            retention_3s REAL, retention_10s REAL, embedding BLOB,
            channel TEXT);
    """)
    rows = [
        ("v1", "This company was worth 40 billion dollars then it collapsed.",
         "finance", 30.0, "shocking_fact", "contradiction", "surprise",
         "money", "explanation", "MagnatesMedia"),
        ("v2", "Why does Planet Fitness keep charging you every month?",
         "consumer", 8.0, "direct_question", "unanswered_why", "curiosity",
         "money", "answer", "Andrei Jikh"),
        ("v3", "Everyone thinks Netflix is profitable. It is not.",
         "finance", 15.0, "contrarian_claim", "contradiction", "surprise",
         "money", "reveal", "Slidebean"),
        ("v4", "The banana industry is a psychological trap for shoppers.",
         "consumer", 5.0, "shocking_fact", "information_gap", "curiosity",
         "none", "none", "Mark Tilbury"),
        ("v5", "This other company was worth 40 billion dollars then it collapsed.",
         "finance", 12.0, "shocking_fact", "contradiction", "surprise",
         "money", "explanation", "MagnatesMedia"),
    ]
    vec = build_embedder([r[1] for r in rows])
    for video_id, text, niche, out, opening, cur, emo, stakes, prom, ch in rows:
        conn.execute(
            "INSERT INTO hook_library (video_id, hook_text, niche_tag, "
            "outlier_score, opening_device, curiosity_mechanism, "
            "emotional_mechanism, stakes_type, promise_type, "
            "narrative_structure, retention_3s, retention_10s, embedding, channel) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (video_id, text, niche, out, opening, cur, emo, stakes, prom,
             "STATE → REVERSAL", 0.5, 1.2, embed(vec, text), ch))
    conn.commit()
    return conn


def test_build_embedder_deterministic():
    texts = ["a b c", "d e f", "a b d"]
    v1 = build_embedder(texts)
    v2 = build_embedder(texts)
    assert pickle.dumps(v1.vocabulary_) == pickle.dumps(v2.vocabulary_)


def test_cosine_same_text_is_one():
    vec = build_embedder(["hello world example"])
    e = embed(vec, "hello world example")
    assert cosine(e, e) == pytest.approx(1.0)


def test_cosine_dissimilar_is_low():
    vec = build_embedder(["apple pie recipe", "quantum physics paper"])
    a = embed(vec, "apple pie recipe")
    b = embed(vec, "quantum physics paper")
    assert cosine(a, b) < 0.4


def test_cosine_empty_vectors_zero():
    vec = build_embedder(["alpha beta"])
    e = embed(vec, "alpha beta")
    empty = pickle.dumps(vec.transform([""]))
    assert cosine(empty, e) == 0.0


def test_embed_returns_pickled_sparse():
    vec = build_embedder(["hello world"])
    blob = embed(vec, "hello world")
    m = pickle.loads(blob)
    assert hasattr(m, "multiply")


def test_retrieve_returns_sorted_top_k(conn):
    out = retrieve(conn, "why is the stock market crashing", top_k=3)
    assert 1 <= len(out) <= 3
    scores = [r["retrieval_score"] for r in out]
    assert scores == sorted(scores, reverse=True)
    assert all({"video_id", "hook_text", "retrieval_score"} <= set(r.keys())
               for r in out)


def test_retrieve_semantic_similarity_ranks_first(conn):
    # query closely matches the Netflix text
    out = retrieve(conn, "everyone thinks netflix is profitable but it is not",
                   top_k=4)
    assert out[0]["video_id"] == "v3"


def test_retrieve_niche_boost(conn):
    out_all = retrieve(conn, "shopping trap", top_k=4)
    out_fin = retrieve(conn, "shopping trap", niche="finance", top_k=4)
    # finance niche boost should pull finance rows up
    fin_ids = [r["video_id"] for r in out_fin[:2]]
    assert any(v in {"v1", "v3"} for v in fin_ids)


def test_retrieve_empty_library_returns_empty():
    conn2 = sqlite3.connect(":memory:")
    conn2.row_factory = sqlite3.Row
    conn2.executescript("""
        CREATE TABLE hook_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT, hook_text TEXT, niche_tag TEXT,
            outlier_score REAL, opening_device TEXT,
            curiosity_mechanism TEXT, emotional_mechanism TEXT,
            stakes_type TEXT, promise_type TEXT, narrative_structure TEXT,
            retention_3s REAL, retention_10s REAL, embedding BLOB,
            channel TEXT);
    """)
    assert retrieve(conn2, "anything") == []


def test_retrieve_channel_balanced(conn):
    # 5 rows across 4 channels (MagnatesMedia has 2). top_k=5 ->
    # max_per_channel = ceil(5/4) = 2 -> MagnatesMedia can contribute at most 2
    out = retrieve(conn, "company worth billions collapsed", top_k=5)
    from collections import Counter
    ch = Counter(r["channel"] for r in out)
    assert ch.get("MagnatesMedia", 0) <= 2
    # and at least one non-MagnatesMedia channel appears
    assert any(r["channel"] != "MagnatesMedia" for r in out)


def test_retrieve_drops_near_duplicates(conn):
    # v1 and v5 are near-duplicates (differ by one word)
    out = retrieve(conn, "company worth 40 billion dollars collapsed", top_k=5)
    texts = [r["hook_text"] for r in out]
    assert sum("worth 40 billion dollars" in t for t in texts) <= 1


def test_dna_sim_counts_overlapping_dimensions():
    a = {"opening_device": "direct_question", "curiosity_mechanism": "why",
         "emotional_mechanism": "curiosity", "stakes_type": "money",
         "promise_type": "answer"}
    b = {"opening_device": "direct_question", "curiosity_mechanism": "why",
         "emotional_mechanism": "fear", "stakes_type": "time",
         "promise_type": "answer"}
    assert _dna_sim(a, b) == pytest.approx(3 / 5)


def test_retrieve_handles_missing_embeddings(conn):
    conn.execute("UPDATE hook_library SET embedding = NULL WHERE video_id='v2'")
    conn.commit()
    out = retrieve(conn, "netflix profitable", top_k=4)
    assert len(out) >= 1  # must not crash on NULL embedding

def test_vectorizer_params_are_char_ngrams():
    assert VEC_PARAMS["analyzer"] == "char_wb"
    assert VEC_PARAMS["ngram_range"][0] == 2