import asyncio
import sqlite3
import threading
from pathlib import Path

from rook.core.events import REDACTED, Event, EventBus
from rook.store.db import connect
from rook.store.repo import RunRecord, Store

FAKE_GHP = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0"


def _run(run_id: str, created_at: str, user_id: str | None = "u1") -> RunRecord:
    return RunRecord(id=run_id, user_id=user_id, repo_kind="github", repo_ref="acme/shop@main",
                     status="running", created_at=created_at)


def _log(run_id: str, seq: int, text: str) -> Event:
    return Event(seq=seq, ts="2026-09-26T08:10:00.123Z", run_id=run_id, type="log",
                 data={"level": "info", "text": text})


def test_schema_created_with_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "rook.db"
    conn = connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "events", "counterexamples", "users", "guest_quota"} <= tables
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    conn.close()
    connect(db_path).close()  # reopening an existing db is fine


def test_runs_insert_get_list(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    store.insert_run(_run("r1", "2026-09-26T08:00:00Z"))
    store.insert_run(_run("r2", "2026-09-26T09:00:00Z"))
    store.insert_run(_run("r3", "2026-09-26T10:00:00Z", user_id="u2"))
    assert store.get_run("r1") == _run("r1", "2026-09-26T08:00:00Z")
    assert store.get_run("missing") is None
    assert [r.id for r in store.list_runs()] == ["r3", "r2", "r1"]
    assert [r.id for r in store.list_runs(user_id="u1", limit=1)] == ["r2"]


def test_events_resume_from_after(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    for seq in range(1, 6):
        store.append_event(_log("r1", seq, f"e{seq}"))
    store.append_event(_log("r2", 1, "other"))
    assert [e.seq for e in store.events_after("r1", 0)] == [1, 2, 3, 4, 5]
    resumed = store.events_after("r1", 3)
    assert [e.data["text"] for e in resumed] == ["e4", "e5"]
    assert store.events_after("r1", 5) == []
    assert store.last_seq("r1") == 5 and store.last_seq("nope") == 0


def test_duplicate_seq_is_rejected(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    store.append_event(_log("r1", 1, "a"))
    try:
        store.append_event(_log("r1", 1, "b"))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("duplicate (run_id, seq) accepted")


def test_counterexample_save_get_and_status_update(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    data = {"cx_id": "cx_001", "steps": [{"action": "refund", "headers": {"auth": FAKE_GHP}}]}
    store.save_counterexample("cx_001", "r1", "r2", data)
    cx = store.get_counterexample("cx_001")
    assert cx is not None and cx.status == "open" and cx.rule_id == "r2"
    assert cx.data["steps"][0]["headers"]["auth"] == REDACTED
    store.save_counterexample("cx_001", "r1", "r2", data, status="verified")
    assert store.get_counterexample("cx_001").status == "verified"  # type: ignore[union-attr]
    assert store.get_counterexample("nope") is None


def test_store_is_thread_safe(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")

    def write(worker: int) -> None:
        for i in range(50):
            store.append_event(_log(f"r{worker}", i + 1, "x"))

    threads = [threading.Thread(target=write, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(store.last_seq(f"r{w}") == 50 for w in range(4))


async def test_bus_persists_and_continues_seq_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "rook.db"
    bus = EventBus(Store(db_path))
    await asyncio.gather(*(bus.publish("r1", "log", {"level": "info", "text": str(i)}) for i in range(200)))

    store = Store(db_path)
    assert [e.seq for e in store.events_after("r1", 0)] == list(range(1, 201))
    fresh_bus = EventBus(store)  # e.g. after a server restart
    event = await fresh_bus.publish("r1", "log", {"level": "info", "text": "after restart"})
    assert event.seq == 201


async def test_late_subscriber_with_store_gets_replay_then_live(tmp_path: Path) -> None:
    bus = EventBus(Store(tmp_path / "rook.db"))
    for i in range(3):
        await bus.publish("r1", "log", {"level": "info", "text": f"old {i}"})

    seen: list[int] = []

    async def consume() -> None:
        async for event in bus.subscribe("r1", after=2):
            seen.append(event.seq)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await bus.publish("r1", "log", {"level": "info", "text": "new"})
    await bus.close("r1")
    await asyncio.wait_for(task, 1)
    assert seen == [3, 4]
