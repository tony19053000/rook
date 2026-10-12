"""ROOK-051: `DELETE /runs/{id}`, `DELETE /me/data`, the retention sweep and safe workspace removal."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from server_helpers import (
    ALICE,
    BASE,
    BOB,
    DEMO,
    Factory,
    QuestionSession,
    RecordedSession,
    client_for,
    create_run,
    guest_headers,
    make_app,
    state_of,
    wait_for,
)

from rook.core.events import Event, now_ts
from rook.server.config import ServerSettings
from rook.server.retention import DataDeleter, SweepResult, remove_workspace, sweep_forever
from rook.server.runs import RunSpec
from rook.store.repo import RunRecord

API = "/api/v1"
SITE = "https://rook.example.app"  # the web origin make_app configures


def rows(tmp_path: Path, run_id: str) -> dict[str, int]:
    """How many rows of the run are left in each table (read from the file, not through the app)."""
    tables = (("runs", "id"), ("events", "run_id"), ("counterexamples", "run_id"))
    with closing(sqlite3.connect(tmp_path / "server.db")) as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} = ?", (run_id,)).fetchone()[0]
                for t, col in tables}


NONE_LEFT = {"runs": 0, "events": 0, "counterexamples": 0}


def workspace(tmp_path: Path, run_id: str) -> Path:
    """A workspace like PREPARE makes, with a nested folder and an inner link."""
    ws = tmp_path / "ws" / run_id
    (ws / "src").mkdir(parents=True)
    (ws / "src" / "app.ts").write_text("export {}\n")
    (ws / "link").symlink_to("src")
    return ws


async def finished_run(client: Any, app: Any, headers: dict[str, str]) -> str:
    run_id = await create_run(client, headers)
    await wait_for(lambda: state_of(app).runs.live(run_id) is None)
    return run_id


class StubbornSession(QuestionSession):
    """Ignores cancel until released, then still writes an event, a counterexample and its final status."""

    def __init__(self, spec: RunSpec) -> None:
        super().__init__(spec)
        self.release = asyncio.Event()

    async def run(self) -> None:
        await self.start()
        self.asked.set()
        await self.release.wait()
        self.spec.store.save_counterexample(f"{self.run_id}_cx_1", self.run_id, "R1", {"cx_id": "cx_1"})
        await self.publish("log", {"level": "info", "text": "a late write"})
        await self.finish("cancelled", "stopped late")

    def cancel(self) -> None:
        self.cancel_calls += 1


# --- DELETE /runs/{id} ---


async def test_the_owner_user_deletes_a_finished_run(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    async with client_for(app) as client:
        run_id = await finished_run(client, app, ALICE)
        ws = workspace(tmp_path, run_id)
        before = rows(tmp_path, run_id)
        response = await client.delete(f"{API}/runs/{run_id}", headers=ALICE)
        after_get = await client.get(f"{API}/runs/{run_id}", headers=ALICE)
        listed = (await client.get(f"{API}/runs", headers=ALICE)).json()
        events = await client.get(f"{API}/runs/{run_id}/events", headers=ALICE)
    assert before["runs"] == 1 and before["events"] > 0 and before["counterexamples"] > 0
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert after_get.status_code == 404 and events.status_code == 404 and listed == []
    assert rows(tmp_path, run_id) == NONE_LEFT
    assert not ws.exists() and (tmp_path / "ws").is_dir()


async def test_the_owner_guest_deletes_its_run(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        run_id = await finished_run(client, app, guest)
        ws = workspace(tmp_path, run_id)
        response = await client.delete(f"{API}/runs/{run_id}", headers=guest)
        after = await client.get(f"{API}/runs/{run_id}", headers=guest)
    assert response.json() == {"ok": True} and after.status_code == 404
    assert rows(tmp_path, run_id) == NONE_LEFT and not ws.exists()


async def test_anyone_else_gets_404_and_the_run_stays(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    _, guest = guest_headers(app)
    _, other_guest = guest_headers(app)
    async with client_for(app) as client:
        users_run = await finished_run(client, app, ALICE)
        guests_run = await finished_run(client, app, guest)
        ws = workspace(tmp_path, users_run)
        by_bob = await client.delete(f"{API}/runs/{users_run}", headers=BOB)
        by_guest = await client.delete(f"{API}/runs/{users_run}", headers=guest)
        by_other_guest = await client.delete(f"{API}/runs/{guests_run}", headers=other_guest)
        by_user = await client.delete(f"{API}/runs/{guests_run}", headers=ALICE)
        anonymous = await client.delete(f"{API}/runs/{users_run}")
        still = await client.get(f"{API}/runs/{users_run}", headers=ALICE)
    assert [r.status_code for r in (by_bob, by_guest, by_other_guest, by_user)] == [404] * 4
    assert {r.json()["detail"] for r in (by_bob, by_guest, by_other_guest, by_user)} == {"Run not found"}
    assert anonymous.status_code == 401  # as GET /runs/{id}: no caller at all
    assert still.status_code == 200 and ws.is_dir()
    assert rows(tmp_path, users_run)["runs"] == rows(tmp_path, guests_run)["runs"] == 1


async def test_missing_and_malformed_ids_are_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with client_for(app) as client:
        missing = await client.delete(f"{API}/runs/r_aaaaaaaaaaaa", headers=ALICE)
        malformed = await client.delete(f"{API}/runs/..%2F..%2Fetc", headers=ALICE)
        odd = await client.delete(f"{API}/runs/r_UPPERCASE123", headers=ALICE)
    assert (missing.status_code, odd.status_code) == (404, 404)
    assert malformed.status_code == 404


async def test_a_running_run_is_cancelled_then_deleted(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        session = factory.sessions[run_id]
        await wait_for(session.asked.is_set)
        ws = workspace(tmp_path, run_id)
        assert rows(tmp_path, run_id)["events"] >= 2
        response = await client.delete(f"{API}/runs/{run_id}", headers=ALICE)
        state = state_of(app)
        live_after = state.runs.live(run_id)
        after = await client.get(f"{API}/runs/{run_id}", headers=ALICE)
        listed = (await client.get(f"{API}/runs", headers=ALICE)).json()
        # a late write for the deleted run (a thread that was still stopping) is dropped
        state.store.append_event(Event(seq=99, ts=now_ts(), run_id=run_id, type="log",
                                       data={"level": "info", "text": "late"}))
        state.store.update_run(run_id, status="failed")
    assert response.json() == {"ok": True}
    assert session.cancel_calls >= 1 and session.finished  # it ended through the cancel path
    assert live_after is None and after.status_code == 404 and listed == []
    assert rows(tmp_path, run_id) == NONE_LEFT and not ws.exists()
    assert run_id not in state.bus._runs  # its event channel is gone too


async def test_a_queued_run_is_deleted(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=1)
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        await wait_for(factory.sessions[first].asked.is_set)
        queued = await create_run(client, ALICE)
        response = await client.delete(f"{API}/runs/{queued}", headers=ALICE)
        after = await client.get(f"{API}/runs/{queued}", headers=ALICE)
        assert state_of(app).runs.live(first) is not None
    assert response.json() == {"ok": True} and after.status_code == 404
    assert rows(tmp_path, queued) == NONE_LEFT


async def test_a_run_that_stops_late_leaves_nothing_behind(tmp_path: Path) -> None:
    """Cancel does not end it within the wait: its late writes are dropped and its workspace goes when it ends."""
    factory = Factory(StubbornSession)
    app = make_app(tmp_path, factory)
    state = state_of(app)
    state.deleter.stop_timeout = 0.05
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        session = factory.sessions[run_id]
        await wait_for(session.asked.is_set)
        ws = workspace(tmp_path, run_id)
        response = await client.delete(f"{API}/runs/{run_id}", headers=ALICE)
        assert response.json() == {"ok": True}
        assert (await client.get(f"{API}/runs/{run_id}", headers=ALICE)).status_code == 404
        assert ws.exists()  # the session could still be using it
        session.release.set()
        await wait_for(lambda: session.finished and not ws.exists())
        await wait_for(lambda: run_id not in state.bus._runs)
    assert rows(tmp_path, run_id) == NONE_LEFT


# --- CSRF / CORS on the DELETE routes ---


async def test_a_cross_site_delete_is_refused(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        run_id = await finished_run(client, app, guest)
        evil = await client.delete(f"{API}/runs/{run_id}",
                                   headers={**guest, "Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"})
        sibling = await client.delete(f"{API}/runs/{run_id}",
                                      headers={**guest, "Sec-Fetch-Site": "same-site", "Origin": "https://x.example.app"})
        evil_me = await client.delete(f"{API}/me/data",
                                      headers={**ALICE, "Sec-Fetch-Site": "cross-site", "Origin": "null"})
        assert rows(tmp_path, run_id)["runs"] == 1
        listed_origin = await client.delete(f"{API}/runs/{run_id}",
                                            headers={**guest, "Sec-Fetch-Site": "cross-site", "Origin": SITE})
    assert (evil.status_code, sibling.status_code, evil_me.status_code) == (403, 403, 403)
    assert listed_origin.json() == {"ok": True}


async def test_a_same_origin_browser_delete_is_allowed(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    async with client_for(app) as client:
        run_id = await finished_run(client, app, ALICE)
        response = await client.delete(f"{API}/runs/{run_id}", headers={**ALICE, "Sec-Fetch-Site": "same-origin",
                                                                         "Origin": BASE})
    assert response.json() == {"ok": True}


async def test_cors_allows_delete_only_for_the_web_origin(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    preflight = {"Access-Control-Request-Method": "DELETE"}
    async with client_for(app) as client:
        ok = await client.options(f"{API}/runs/r_aaaaaaaaaaaa", headers={**preflight, "Origin": SITE})
        evil = await client.options(f"{API}/runs/r_aaaaaaaaaaaa", headers={**preflight, "Origin": "https://evil.example"})
    assert ok.status_code == 200 and "DELETE" in ok.headers["access-control-allow-methods"]
    assert evil.status_code == 400


# --- DELETE /me/data ---


async def test_delete_my_data_removes_only_the_callers_runs_and_users_row(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    state = state_of(app)
    state.db.bind_installation("u_alice", "alice@example.com", 11, now_ts())
    state.db.bind_installation("u_bob", "bob@example.com", 22, now_ts())
    async with client_for(app) as client:
        finished = await create_run(client, ALICE)
        await wait_for(factory.sessions[finished].asked.is_set)
        await client.post(f"{API}/runs/{finished}/answers", json={"question_id": "q_fix", "answer": True},
                          headers=ALICE)
        await wait_for(lambda: state.runs.live(finished) is None)
        running = await create_run(client, ALICE)
        await wait_for(factory.sessions[running].asked.is_set)
        bobs = await create_run(client, BOB)
        await wait_for(factory.sessions[bobs].asked.is_set)
        spaces = [workspace(tmp_path, r) for r in (finished, running, bobs)]
        response = await client.delete(f"{API}/me/data", headers=ALICE)
        alice_runs = (await client.get(f"{API}/runs", headers=ALICE)).json()
        bob_runs = (await client.get(f"{API}/runs", headers=BOB)).json()
    assert response.status_code == 200 and response.json() == {"ok": True, "runs_deleted": 2}
    assert alice_runs == [] and [r["id"] for r in bob_runs] == [bobs]
    assert rows(tmp_path, finished) == rows(tmp_path, running) == NONE_LEFT
    assert rows(tmp_path, bobs)["runs"] == 1
    assert [s.exists() for s in spaces] == [False, False, True]
    with closing(sqlite3.connect(tmp_path / "server.db")) as conn:  # the app's own connection is closed now
        assert conn.execute("SELECT id, github_installation_id FROM users").fetchall() == [("u_bob", 22)]


async def test_delete_my_data_needs_a_signed_in_user(tmp_path: Path) -> None:
    app = make_app(tmp_path, Factory(RecordedSession))
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        run_id = await finished_run(client, app, guest)
        as_guest = await client.delete(f"{API}/me/data", headers=guest)
        anonymous = await client.delete(f"{API}/me/data")
        nothing = await client.delete(f"{API}/me/data", headers=BOB)
    assert (as_guest.status_code, anonymous.status_code) == (401, 401)
    assert rows(tmp_path, run_id)["runs"] == 1
    assert nothing.json() == {"ok": True, "runs_deleted": 0}


# --- the retention sweep ---


def _ts(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stored(state: Any, run_id: str, status: str, created: datetime) -> None:
    state.store.insert_run(RunRecord(id=run_id, user_id="u_alice", repo_kind="demo", repo_ref=DEMO.ref,
                                     status=status, created_at=_ts(created)))
    state.store.append_event(Event(seq=1, ts=_ts(created), run_id=run_id, type="log",
                                   data={"level": "info", "text": "x"}))
    state.store.save_counterexample(f"{run_id}_cx_1", run_id, "R1", {"cx_id": "cx_1"})


def _quota_keys(tmp_path: Path) -> set[str]:
    with closing(sqlite3.connect(tmp_path / "server.db")) as conn:
        return {row[0] for row in conn.execute("SELECT key FROM guest_quota")}


async def test_the_sweep_deletes_old_finished_runs_and_old_quota_rows(tmp_path: Path) -> None:
    factory = Factory()
    later = datetime.now(UTC) + timedelta(days=60)  # a fake "now": every real run is 60 days old by then
    app = make_app(tmp_path, factory)
    state = state_of(app)
    _stored(state, "r_olddoneaaaa", "done", later - timedelta(days=40))
    _stored(state, "r_oldfailaaaa", "failed", later - timedelta(days=31))
    _stored(state, "r_recentaaaaa", "done", later - timedelta(days=29))
    for key, age in (("guest:g_old", 3), ("ip:10.0.0.7", 5), ("guest:g_edge", 2), ("guest:g_today", 0)):
        state.db.consume_run({key: 9}, (later - timedelta(days=age)).strftime("%Y-%m-%d"))
    old_ws = workspace(tmp_path, "r_olddoneaaaa")
    async with client_for(app) as client:
        # stored as running after startup (so not marked interrupted): never deleted while active
        _stored(state, "r_oldrunaaaaa", "running", later - timedelta(days=40))
        live = await create_run(client, ALICE)  # running, created 60 fake days ago
        await wait_for(factory.sessions[live].asked.is_set)
        result = await state.deleter.sweep(later, 30)
        still_live = state.runs.live(live) is not None
    assert result == SweepResult(runs=2, quota_rows=2)
    assert rows(tmp_path, "r_olddoneaaaa") == rows(tmp_path, "r_oldfailaaaa") == NONE_LEFT
    assert rows(tmp_path, "r_oldrunaaaaa")["runs"] == rows(tmp_path, "r_recentaaaaa")["runs"] == 1
    assert rows(tmp_path, "r_recentaaaaa")["events"] == 1 and rows(tmp_path, live)["runs"] == 1
    assert still_live and not old_ws.exists()
    assert _quota_keys(tmp_path) == {"guest:g_edge", "guest:g_today"}


async def test_the_sweep_runs_at_startup_with_the_injected_clock_and_stops_on_shutdown(tmp_path: Path) -> None:
    later = datetime.now(UTC) + timedelta(days=100)
    app = make_app(tmp_path, clock=lambda: later, retention_days=7)
    state = state_of(app)
    _stored(state, "r_olddoneaaaa", "done", later - timedelta(days=8))
    _stored(state, "r_recentaaaaa", "done", later - timedelta(days=6))
    async with client_for(app):
        await wait_for(lambda: rows(tmp_path, "r_olddoneaaaa") == NONE_LEFT)
        assert any(t.get_name() == "retention sweep" for t in asyncio.all_tasks())
    assert rows(tmp_path, "r_recentaaaaa")["runs"] == 1
    assert not any(t.get_name() == "retention sweep" and not t.done() for t in asyncio.all_tasks())


class CountingDeleter:
    def __init__(self) -> None:
        self.calls: list[tuple[datetime, int]] = []

    async def sweep(self, now: datetime, retention_days: int) -> SweepResult:
        self.calls.append((now, retention_days))
        if len(self.calls) == 2:
            raise RuntimeError("the disk is busy")  # a failed sweep must not stop the next ones
        return SweepResult(runs=0, quota_rows=0)


async def test_the_sweep_repeats_every_interval_and_survives_a_failure() -> None:
    deleter = CountingDeleter()
    when = datetime(2026, 1, 1, tzinfo=UTC)
    task = asyncio.create_task(sweep_forever(deleter, 30, lambda: when, interval=0.01))  # type: ignore[arg-type]
    await wait_for(lambda: len(deleter.calls) >= 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert deleter.calls[0] == (when, 30)


# --- safe workspace removal ---


def test_remove_workspace_refuses_paths_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    for crafted in ("../precious", "/tmp/precious", "r_abcd/../../precious", "precious", "", "r_"):
        with pytest.raises(ValueError):
            remove_workspace(root, crafted)
    (root / "r_linkedaaaaa").symlink_to(outside, target_is_directory=True)
    assert remove_workspace(root, "r_linkedaaaaa") is True  # the link goes, never what it points to
    assert not (root / "r_linkedaaaaa").exists() and (outside / "keep.txt").read_text() == "keep"
    assert remove_workspace(root, "r_missingaaaa") is False


def test_remove_workspace_never_follows_links_inside(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    ws = root / "r_abcdefghijkl"
    (ws / "deep").mkdir(parents=True)
    (ws / "deep" / "escape").symlink_to(outside, target_is_directory=True)
    (ws / "file.txt").write_text("x")
    assert remove_workspace(root, "r_abcdefghijkl") is True
    assert not ws.exists() and root.is_dir() and (outside / "keep.txt").read_text() == "keep"


def test_remove_workspace_under_a_linked_root(tmp_path: Path) -> None:
    real = tmp_path / "real-ws"
    (real / "r_abcdefghijkl").mkdir(parents=True)
    root = tmp_path / "ws"
    root.symlink_to(real, target_is_directory=True)
    assert remove_workspace(root, "r_abcdefghijkl") is True
    assert not (real / "r_abcdefghijkl").exists()


# --- settings ---


def test_retention_days_setting() -> None:
    assert ServerSettings.from_env({}).retention_days == 30
    assert ServerSettings.from_env({"ROOK_RETENTION_DAYS": "7"}).retention_days == 7
    with pytest.raises(ValidationError):
        ServerSettings.from_env({"ROOK_RETENTION_DAYS": "0"})


def test_the_deleter_is_wired_to_the_configured_root(tmp_path: Path) -> None:
    deleter = state_of(make_app(tmp_path)).deleter
    assert isinstance(deleter, DataDeleter) and deleter.workspaces_root == tmp_path / "ws"
