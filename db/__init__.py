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
    conn.commit()
    if close:
        conn.close()
    return conn