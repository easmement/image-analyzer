"""SQLite access: one connection per request or job thread, WAL mode for concurrent reads."""

import sqlite3
from collections.abc import Generator, Iterator
from contextlib import contextmanager

from image_analyzer.core.config import settings

# Append-only: each entry upgrades the schema by one version (tracked in PRAGMA user_version).
MIGRATIONS = [
    """
    CREATE TABLE libraries (
        id           INTEGER PRIMARY KEY,
        root_path    TEXT NOT NULL UNIQUE,
        name         TEXT NOT NULL,
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        last_scan_at TEXT
    );
    CREATE TABLE images (
        id          INTEGER PRIMARY KEY,
        library_id  INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
        rel_path    TEXT NOT NULL,
        size_bytes  INTEGER NOT NULL,
        mtime_ns    INTEGER NOT NULL,
        sha256      TEXT,
        width       INTEGER,
        height      INTEGER,
        format      TEXT,
        status      TEXT NOT NULL,          -- ok | error
        error       TEXT,
        indexed_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (library_id, rel_path)
    );
    CREATE INDEX images_sha256 ON images (library_id, sha256);
    CREATE TABLE jobs (
        id          TEXT PRIMARY KEY,
        kind        TEXT NOT NULL,
        library_id  INTEGER REFERENCES libraries(id) ON DELETE CASCADE,
        status      TEXT NOT NULL,          -- running | completed | cancelled | failed
        total       INTEGER NOT NULL DEFAULT 0,
        done        INTEGER NOT NULL DEFAULT 0,
        failed      INTEGER NOT NULL DEFAULT 0,
        message     TEXT,
        started_at  TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT
    );
    """,
    # v2: perceptual hashes (8 orientations x 8 bytes each). features_version marks which
    # pipeline produced a row, so a scan can reprocess rows from an older pipeline.
    """
    ALTER TABLE images ADD COLUMN phash8 BLOB;
    ALTER TABLE images ADD COLUMN dhash8 BLOB;
    ALTER TABLE images ADD COLUMN features_version INTEGER NOT NULL DEFAULT 1;
    """,
    # v3: image embedding (L2-normalised, stored as float16) and the model that produced it.
    """
    ALTER TABLE images ADD COLUMN embedding BLOB;
    ALTER TABLE images ADD COLUMN embedding_model TEXT;
    """,
    # v4: watch mode (rescan automatically when files change).
    """
    ALTER TABLE libraries ADD COLUMN watch INTEGER NOT NULL DEFAULT 0;
    """,
]


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def transaction() -> Generator[sqlite3.Connection]:
    """Commit on success, roll back on error, and always close. (A bare `with conn:` only
    commits; it leaves the connection open.)"""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with transaction() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
            conn.executescript(f"BEGIN; {script} PRAGMA user_version = {i}; COMMIT;")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: a connection scoped to one request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
