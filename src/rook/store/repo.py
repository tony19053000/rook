"""Queries over the SQLite store. One `Store` wraps one connection behind a lock, so it is thread-safe."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from rook.core.events import Event, redact
from rook.store.db import connect

CxStatus = Literal["open", "fixed", "verified"]


class RunRecord(BaseModel):
    id: str
    user_id: str | None = None
    repo_kind: str
    repo_ref: str
    status: str
    created_at: str
    finished_at: str | None = None
    coins: float = 0.0


class CounterexampleRecord(BaseModel):
    id: str
    run_id: str
    rule_id: str
    data: dict[str, Any]
    status: CxStatus


class Store:
    def __init__(self, path: str | Path) -> None:
        self._conn = connect(path)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # runs -----------------------------------------------------------------

    def insert_run(self, run: RunRecord) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs(id, user_id, repo_kind, repo_ref, status, created_at, finished_at, coins)"
                " VALUES (:id, :user_id, :repo_kind, :repo_ref, :status, :created_at, :finished_at, :coins)",
                run.model_dump(),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunRecord(**dict(row)) if row else None

    def list_runs(self, user_id: str | None = None, limit: int = 50) -> list[RunRecord]:
        """Newest first; all runs when `user_id` is None."""
        query = "SELECT * FROM runs"
        params: tuple[Any, ...] = ()
        if user_id is not None:
            query += " WHERE user_id = ?"
            params = (user_id,)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, (*params, limit)).fetchall()
        return [RunRecord(**dict(r)) for r in rows]

    # events ---------------------------------------------------------------

    def append_event(self, event: Event) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(run_id, seq, ts, type, data) VALUES (?, ?, ?, ?, ?)",
                (event.run_id, event.seq, event.ts, event.type, json.dumps(redact(event.data))),
            )

    def events_after(self, run_id: str, seq: int) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, ts, type, data FROM events WHERE run_id = ? AND seq > ? ORDER BY seq",
                (run_id, seq),
            ).fetchall()
        return [
            Event(seq=r["seq"], ts=r["ts"], run_id=run_id, type=r["type"], data=json.loads(r["data"]))
            for r in rows
        ]

    def last_seq(self, run_id: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT MAX(seq) FROM events WHERE run_id = ?", (run_id,)).fetchone()
        return row[0] or 0

    # counterexamples ------------------------------------------------------

    def save_counterexample(
        self, cx_id: str, run_id: str, rule_id: str, data: dict[str, Any], status: CxStatus = "open"
    ) -> None:
        """Insert or replace (e.g. to move status open -> fixed -> verified)."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO counterexamples(id, run_id, rule_id, json, status) VALUES (?, ?, ?, ?, ?)",
                (cx_id, run_id, rule_id, json.dumps(redact(data)), status),
            )

    def get_counterexample(self, cx_id: str) -> CounterexampleRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM counterexamples WHERE id = ?", (cx_id,)).fetchone()
        if row is None:
            return None
        return CounterexampleRecord(
            id=row["id"], run_id=row["run_id"], rule_id=row["rule_id"],
            data=json.loads(row["json"]), status=row["status"],
        )
