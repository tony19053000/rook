"""ROOK-050: with hosted GitHub runs off (the default), a guest's recorded example run still works end to end
through the server's own routes, and never touches Docker.

The run is created and answered over HTTP like the web does (POST /runs, POST /runs/{id}/answers, GET /runs/{id})
on a server with the default settings (`github_runs_max` 0, replay mode). The Session is the one the server builds
for a demo repo: the allowlisted minishop app as a ProcessSandbox subprocess, every Bob call replayed from the
committed recordings (the setup of test_hosted_fix_replay.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from server_helpers import client_for, guest_headers, make_app, state_of
from test_hosted_fix_replay import CappedClient, demo_entry, guest, replay_dir

from rook.core.events import EventBus, clear_secrets
from rook.core.session import Session
from rook.sandbox import reaper
from rook.sandbox.allowlist import Allowlist
from rook.server.config import DemoRepo
from rook.server.runs import RunSpec

API = "/api/v1"


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


async def test_a_guest_recorded_run_verifies_its_fix_with_github_runs_off_and_no_docker(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docker_calls: list[Any] = []

    def no_docker(*args: Any, **kwargs: Any) -> Any:
        docker_calls.append(args)
        raise AssertionError("a guest example run must not use Docker")

    monkeypatch.setattr(reaper, "docker", no_docker)
    entry = demo_entry(tmp_path)
    replays = replay_dir(tmp_path)
    sessions: list[Session] = []

    def factory(spec: RunSpec) -> Session:
        def client(bus: EventBus, run_id: str, workspace: Path) -> CappedClient:
            return CappedClient(bus, run_id, replays, None)

        session = Session(spec.repo, spec.request, spec.options, bus=spec.bus, store=spec.store, run_id=spec.run_id,
                          user_id=spec.user_id, workspaces_root=tmp_path / "workspaces", client_factory=client,
                          allowlist=Allowlist([entry]), run_workspace=True)
        sessions.append(session)
        return session

    demo = DemoRepo(ref=entry.repo, commit=entry.commit, name="minishop", language="Python")
    app = make_app(tmp_path, factory, demo_repos=[demo], docker_ready=lambda: docker_calls.append("probe") or False)
    assert state_of(app).settings.github_runs_max == 0  # the default: hosted GitHub runs off
    _, headers = guest_headers(app)
    answer = guest("refund")
    async with client_for(app) as client:
        created = await client.post(f"{API}/runs", json={"repo": {"kind": "demo", "ref": entry.repo},
                                                          "request": "find and fix a bug", "options": {"auto": False}},
                                    headers=headers)
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        (session,) = sessions

        events: list[Any] = []

        async def answer_over_http() -> None:
            async for event in session.events():
                events.append(event)
                if event.type == "question.asked" and event.data["kind"] != "setup_value":
                    body = {"question_id": event.data["question_id"], "answer": answer(event.data)}
                    response = await client.post(f"{API}/runs/{run_id}/answers", json=body, headers=headers)
                    assert response.json() == {"ok": True}

        async with asyncio.timeout(240):
            await answer_over_http()  # the stream ends with the run
        detail = (await client.get(f"{API}/runs/{run_id}", headers=headers)).json()
    assert detail["run"]["status"] == "done", detail
    assert session.result is not None and session.result.verified, session.result
    seen = [e.data["phase"] for e in events if e.type == "run.phase"]
    assert seen[-7:] == ["DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE"], seen
    (done,) = [e.data for e in events if e.type == "verify.done"]
    assert done["verified"] is True and session.state.coins_spent == 0.0
    assert all(f["recorded"] for f in (e.data for e in events if e.type == "agent.finished"))
    assert docker_calls == []
