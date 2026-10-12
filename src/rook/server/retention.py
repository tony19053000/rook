"""Deleting a run or a user's data on request, and the retention sweep (ROOK-051, 02 §10-§11, 03 §10).

Deleting a live run, in this order: cancel it and wait (up to `STOP_TIMEOUT`) for its task to end; delete its
rows, which also tombstones the id in the `Store` so any late write of that run is dropped; drop its event
channel and remove its workspace. If the task is still stopping after the timeout, the channel and workspace go
as soon as it ends (a sandbox could still be writing into the workspace until then).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rook.core.events import EventBus
from rook.server.db import ServerDb
from rook.server.runs import RunManager
from rook.store.repo import Store

log = logging.getLogger(__name__)

STOP_TIMEOUT = 30.0  # seconds a deletion waits for a cancelled run to stop
SWEEP_SECONDS = 3600.0
QUOTA_DAYS = 2
_RUN_ID = re.compile(r"r_[a-z2-7]{4,32}")  # the ids `prepare_workspace` accepts

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def remove_workspace(root: Path, run_id: str) -> bool:
    """Remove `<root>/<run_id>` without following symlinks. Refuses (ValueError) a run id that is not one, or a
    folder that does not resolve to a direct child of the resolved root. A symlink in its place is unlinked; what
    it points to is never touched. False when there was nothing to remove."""
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError("refused workspace path: not a run id")
    base = root.expanduser().resolve()
    target = base / run_id
    if not os.path.lexists(target):
        return False
    if target.is_symlink():
        target.unlink()
        return True
    if target.resolve().parent != base:
        raise ValueError("refused workspace path: outside the workspaces root")
    if not target.is_dir():
        target.unlink()
        return True
    shutil.rmtree(target)  # fd-based on Linux: links inside are unlinked, never followed
    return True


@dataclass(frozen=True)
class SweepResult:
    runs: int
    quota_rows: int


class DataDeleter:
    def __init__(self, store: Store, db: ServerDb, bus: EventBus, runs: RunManager, workspaces_root: Path,
                 *, stop_timeout: float = STOP_TIMEOUT) -> None:
        self.store = store
        self.db = db
        self.bus = bus
        self.runs = runs
        self.workspaces_root = workspaces_root
        self.stop_timeout = stop_timeout
        self._cleanups: set[asyncio.Task[None]] = set()

    async def delete_run(self, run_id: str) -> None:
        """Delete everything of one run: its live session (cancelled first), rows, event channel and workspace."""
        still_stopping = await self.runs.stop(run_id, self.stop_timeout)
        self.store.delete_run(run_id)
        if still_stopping is None:
            await self._forget(run_id)
            return
        log.warning("run %s is still stopping; its workspace is removed when it ends", run_id)
        still_stopping.add_done_callback(lambda _: self._later(run_id))

    def _later(self, run_id: str) -> None:
        task = asyncio.get_running_loop().create_task(self._forget(run_id))
        self._cleanups.add(task)  # the loop keeps only a weak reference
        task.add_done_callback(self._cleanups.discard)

    async def _forget(self, run_id: str) -> None:
        await self.bus.forget(run_id)
        try:
            await asyncio.to_thread(remove_workspace, self.workspaces_root, run_id)
        except (OSError, ValueError):
            log.exception("could not remove the workspace of run %s", run_id)

    async def delete_user(self, user_id: str) -> int:
        """Delete every run the user owns (stored or still queued) and their `users` row; the number of runs."""
        ids = set(self.store.run_ids_of(user_id)) | {run_id for run_id, _ in self.runs.live_of(user_id)}
        await asyncio.gather(*(self.delete_run(run_id) for run_id in sorted(ids)))
        self.db.delete_user(user_id)
        return len(ids)

    async def sweep(self, now: datetime, retention_days: int) -> SweepResult:
        """Delete the runs created more than `retention_days` before `now` (never an active one) and the quota
        rows of days more than `QUOTA_DAYS` before it."""
        cutoff = (now - timedelta(days=retention_days)).astimezone(UTC).isoformat(timespec="milliseconds")
        cutoff = cutoff.replace("+00:00", "Z")
        live = self.runs.live_ids()
        old = [r.id for r in self.store.runs_created_before(cutoff) if r.status != "running" and r.id not in live]
        for run_id in old:
            await self.delete_run(run_id)
        day = (now - timedelta(days=QUOTA_DAYS)).astimezone(UTC).strftime("%Y-%m-%d")
        return SweepResult(runs=len(old), quota_rows=self.db.delete_quota_before(day))


async def sweep_forever(deleter: DataDeleter, retention_days: int, clock: Clock = utc_now,
                        interval: float = SWEEP_SECONDS) -> None:
    """The retention sweep now and then every `interval` s, until cancelled. A failed sweep is logged."""
    while True:
        try:
            result = await deleter.sweep(clock(), retention_days)
            if result.runs or result.quota_rows:
                log.info("retention: deleted %d run(s) and %d quota row(s)", result.runs, result.quota_rows)
        except Exception:
            log.exception("the retention sweep failed")
        await asyncio.sleep(interval)
