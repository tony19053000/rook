"""The server's own queries on the shared SQLite file (02 §10): guest quotas, today's coins, run headlines.

It opens its own connection (WAL lets it sit next to the `Store` the sessions write through).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from pathlib import Path

from rook.store.db import connect


class ServerDb:
    def __init__(self, path: str | Path) -> None:
        self._conn: sqlite3.Connection = connect(path)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def consume_run(self, limits: Mapping[str, int], day: str) -> bool:
        """Count one run against every key for `day`, only if none of them is at its limit yet (atomic)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                used: dict[str, int] = {}
                for key in limits:
                    row = self._conn.execute("SELECT day, runs FROM guest_quota WHERE key = ?", (key,)).fetchone()
                    used[key] = row["runs"] if row is not None and row["day"] == day else 0
                if any(n >= limits[key] for key, n in used.items()):
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

    # --- GitHub installations (ROOK-031): `users.github_installation_id` ---

    def installation_of(self, user_id: str) -> int | None:
        with self._lock:
            row = self._conn.execute("SELECT github_installation_id FROM users WHERE id = ?", (user_id,)).fetchone()
        return int(row[0]) if row is not None and row[0] is not None else None

    def installation_owner(self, installation_id: int) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT id FROM users WHERE github_installation_id = ?",
                                     (installation_id,)).fetchone()
        return str(row[0]) if row is not None else None

    def bind_installation(self, user_id: str, email: str, installation_id: int, created_at: str) -> bool:
        """Link the installation to the user, only if no other user has it (atomic). False otherwise."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT id FROM users WHERE github_installation_id = ? AND id != ?",
                                         (installation_id, user_id)).fetchone()
                if row is not None:
                    self._conn.execute("ROLLBACK")
                    return False
                self._conn.execute(
                    "INSERT INTO users(id, email, github_installation_id, created_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(id) DO UPDATE SET email = excluded.email,"
                    " github_installation_id = excluded.github_installation_id",
                    (user_id, email, installation_id, created_at))
                self._conn.execute("COMMIT")
                return True
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def unbind_installation(self, installation_id: int) -> int:
        """Forget a deleted installation for every user who had it; the number of users changed."""
        with self._lock:
            cursor = self._conn.execute("UPDATE users SET github_installation_id = NULL"
                                        " WHERE github_installation_id = ?", (installation_id,))
        return cursor.rowcount
