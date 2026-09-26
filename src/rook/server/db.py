"""The server's own queries on the shared SQLite file (02 §10): guest quotas, today's coins, run headlines.

It opens its own connection (WAL lets it sit next to the `Store` the sessions write through).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path

from rook.store.db import connect


class ServerDb:
    def __init__(self, path: str | Path) -> None:
        self._conn: sqlite3.Connection = connect(path)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def consume_run(self, keys: Sequence[str], day: str, limit: int) -> bool:
        """Count one run against every key for `day`, only if none of them is at `limit` yet (atomic)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                used: dict[str, int] = {}
                for key in keys:
                    row = self._conn.execute("SELECT day, runs FROM guest_quota WHERE key = ?", (key,)).fetchone()
                    used[key] = row["runs"] if row is not None and row["day"] == day else 0
                if any(n >= limit for n in used.values()):
                    self._conn.execute("ROLLBACK")
                    return False
                for key, n in used.items():
                    self._conn.execute(
                        "INSERT INTO guest_quota(key, day, runs, coins) VALUES (?, ?, ?, 0)"
                        " ON CONFLICT(key) DO UPDATE SET day = excluded.day, runs = excluded.runs",
                        (key, day, n + 1))
                self._conn.execute("COMMIT")
                return True
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def coins_since(self, day: str) -> float:
        """Coins spent by runs created on or after `day` (YYYY-MM-DD; `created_at` is ISO 8601 UTC)."""
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(coins), 0) FROM runs WHERE created_at >= ?",
                                     (day,)).fetchone()
        return float(row[0])

    def run_request(self, run_id: str) -> str | None:
        """The `request` of the run's `run.created` event (seq 1), without loading the whole log."""
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM events WHERE run_id = ? AND seq = 1 AND type = 'run.created'", (run_id,),
            ).fetchone()
        if row is None:
            return None
        request = json.loads(row["data"]).get("request")
        return request if isinstance(request, str) else None
