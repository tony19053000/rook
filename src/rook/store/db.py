"""SQLite schema (02_ARCHITECTURE.md §10) and connection setup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
    id TEXT PRIMARY KEY, user_id TEXT, repo_kind TEXT, repo_ref TEXT, status TEXT,
    created_at TEXT, finished_at TEXT, coins REAL
);
CREATE TABLE IF NOT EXISTS events(
    run_id TEXT, seq INTEGER, ts TEXT, type TEXT, data TEXT, PRIMARY KEY(run_id, seq)
);
CREATE TABLE IF NOT EXISTS counterexamples(
    id TEXT PRIMARY KEY, run_id TEXT, rule_id TEXT, json TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS users(
    id TEXT PRIMARY KEY, email TEXT, github_installation_id INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS guest_quota(
    key TEXT PRIMARY KEY, day TEXT, runs INTEGER, coins REAL
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (creating if missing) the database in WAL mode with the schema applied.

    The connection may be shared across threads; callers must serialise access (see `repo.Store`).
    """
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn
