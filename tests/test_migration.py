"""Tests for db migrations — additive, idempotent, non-destructive.

Runs init_db against a throwaway temp DB (not the real one).
"""
import sqlite3
from pathlib import Path

import pytest

from db import SCHEMA_PATH, init_db
from config import ROOT, load_settings


@pytest.fixture()
def fresh_db(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    yield conn, db
    conn.close()


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# ------------------------------------------------------------------ schema

def test_schema_sql_has_hook_tables():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS hook_library" in sql
    assert "CREATE TABLE IF NOT EXISTS hook_generations" in sql
    assert "hook_dna_json" in sql


def test_init_db_creates_hook_tables(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"hook_library", "hook_generations"} <= tables
    assert "hook_dna_json" in _columns(conn, "video_features")


def test_hook_library_columns(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    cols = _columns(conn, "hook_library")
    for needed in ("video_id", "hook_text", "archetype", "opening_device",
                   "curiosity_mechanism", "emotional_mechanism", "stakes_type",
                   "promise_type", "narrative_structure", "retention_10s",
                   "embedding", "niche_tag", "channel", "factuality",
                   "hook_score", "analyzed_at"):
        assert needed in cols


def test_hook_library_video_id_unique_index(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    conn.execute(
        "INSERT INTO hook_library (video_id, hook_text) VALUES ('a', 'hook one')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO hook_library (video_id, hook_text) VALUES ('a', 'dup')")
    conn.rollback()


def test_hook_generations_columns(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    cols = _columns(conn, "hook_generations")
    assert {"id", "topic", "mode", "duration_target", "hooks_json",
            "my_video_id", "selected_hook_text", "actual_ctr",
            "actual_avd_pct"} <= cols


# ------------------------------------------------------------ idempotence

def test_init_db_idempotent(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    init_db(conn)
    init_db(conn)  # repeated runs must not raise
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "hook_library" in tables


def test_existing_data_survives_reinit(fresh_db):
    conn, db = fresh_db
    init_db(conn)
    conn.execute("INSERT INTO channels (channel_id, title) VALUES ('c1', 'Test')")
    conn.commit()
    init_db(conn)  # re-run migration over existing data
    assert conn.execute(
        "SELECT COUNT(*) FROM channels WHERE channel_id='c1'").fetchone()[0] == 1


# ---------------------------------------------------- pre-existing schema

def test_migration_on_legacy_db_without_hook_tables(fresh_db):
    """Simulate a DB created before the hook feature: no hook tables, no
    hook_dna_json column. init_db must add everything without failing."""
    conn, db = fresh_db
    conn.executescript("""
        CREATE TABLE channels (channel_id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, title TEXT, channel TEXT,
            published_at TEXT, duration_sec REAL, view_count INTEGER,
            outlier_score REAL);
        CREATE TABLE video_features (
            video_id TEXT PRIMARY KEY, outlier_score REAL);
        CREATE TABLE heatmaps (video_id TEXT PRIMARY KEY, points_json TEXT);
    """)
    conn.commit()
    init_db(conn)  # must not raise
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "hook_library" in tables
    assert "hook_dna_json" in _columns(conn, "video_features")


def test_migration_preserves_legacy_hook_index(fresh_db):
    """The unique index migration drops a non-unique index of the same name
    and recreates it as unique — must work when the old one exists."""
    conn, db = fresh_db
    conn.executescript("""
        CREATE TABLE hook_library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT, title TEXT, channel TEXT, niche_tag TEXT,
            outlier_score REAL, hook_text TEXT, hook_start REAL,
            hook_end REAL, word_count INTEGER, duration REAL, wpm REAL,
            archetype TEXT, opening_device TEXT, curiosity_mechanism TEXT,
            emotional_mechanism TEXT, stakes_type TEXT, promise_type TEXT,
            narrative_structure TEXT, first_number_sec REAL,
            first_entity_sec REAL, first_stakes_sec REAL,
            first_curiosity_sec REAL, promise_sec REAL,
            retention_1s REAL, retention_3s REAL, retention_5s REAL,
            retention_10s REAL, retention_15s REAL, retention_20s REAL,
            retention_30s REAL, early_retention REAL, retention_slope REAL,
            retention_drop REAL, retention_recovery REAL, peak_retention REAL,
            peak_sec REAL, volatility REAL, hook_score REAL, embedding BLOB,
            factuality TEXT, analyzed_at TEXT);
        CREATE INDEX idx_hook_library_video ON hook_library(video_id);
    """)
    conn.commit()
    init_db(conn)
    idx = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND name='idx_hook_library_video'").fetchone()[0]
    assert "UNIQUE" in idx.upper()


def test_schema_path_exists():
    assert SCHEMA_PATH.exists()