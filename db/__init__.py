import sqlite3
from pathlib import Path

from config import ROOT, load_settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def db_path() -> Path:
    return ROOT / load_settings()["paths"]["db"]


def get_connection(db: Path | None = None) -> sqlite3.Connection:
    db = db or db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    close = conn is None
    conn = conn or get_connection()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        conn.execute("ALTER TABLE channels ADD COLUMN uploads_playlist TEXT")
    except sqlite3.OperationalError:
        pass  # already exists
    try:
        conn.execute("ALTER TABLE video_features ADD COLUMN hook_dna_json TEXT")
    except sqlite3.OperationalError:
        pass  # already exists
    try:
        conn.execute("DROP INDEX IF EXISTS idx_hook_library_video")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_hook_library_video ON hook_library(video_id)")
    except sqlite3.OperationalError as e:
        # if this fails (duplicate video_ids), ON CONFLICT upserts silently
        # stop deduping — this must never pass unnoticed
        print(f"[db] WARNING: unique idx_hook_library_video NOT ensured ({e}). "
              f"Upserts will silently duplicate; run `python -m miner.hooks "
              f"build-library` after deduping hook_library.")
    conn.commit()
    if close:
        conn.close()
    return conn