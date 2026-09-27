"""ROOK-029: the app wiring: Starlette's TestClient end to end, the default Session factory, and
`rook.server.app:app` built from the environment."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from server_helpers import ALICE, BASE, DEMO, NEW_RUN, Factory, make_app, parse_sse

from rook.core.events import EventBus
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec
from rook.sandbox.allowlist import Allowlist
from rook.server import app as app_module
from rook.server.config import ServerSettings
from rook.server.runs import RunSpec, default_session_factory
from rook.store.repo import Store

API = "/api/v1"


def test_testclient_create_answer_and_stream(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    with TestClient(app, base_url=BASE) as client:
        assert client.get(f"{API}/health").json()["ok"] is True
        run_id = client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE).json()["run_id"]
        session = factory.sessions[run_id]
        for _ in range(200):
            if session.asked.is_set():
                break
            client.get(f"{API}/health")
        answer = client.post(f"{API}/runs/{run_id}/answers", json={"question_id": "q_fix", "answer": True},
                             headers=ALICE)
        assert answer.json() == {"ok": True}
        for _ in range(200):
            if client.get(f"{API}/runs/{run_id}", headers=ALICE).json()["run"]["status"] == "done":
                break
        events = parse_sse(client.get(f"{API}/runs/{run_id}/events", headers=ALICE).text)
    assert [e["type"] for e in events] == ["run.created", "question.asked", "question.answered", "run.finished"]


def test_the_default_factory_builds_a_hosted_session(tmp_path: Path) -> None:
    settings = ServerSettings(db_path=tmp_path / "s.db", workspaces_root=tmp_path / "ws", bob_mode="replay")
    store = Store(settings.db_path)
    bus = EventBus(store)
    allowlist = Allowlist()
    make = default_session_factory(settings, allowlist)
    repo = RepoSpec(kind="demo", ref=DEMO.ref, commit=DEMO.commit)
    session = make(RunSpec("r_cccccccccccc", repo, "find bugs", SessionOptions(hosted=True), "u_alice", bus, store))
    assert isinstance(session, Session)
    assert session.run_id == "r_cccccccccccc" and session.user_id == "u_alice"
    assert session.bus is bus and session.store is store and session.options.hosted is True
    assert session.workspaces_root == settings.workspaces_root
    store.close()


def test_the_featured_rule_comes_from_the_trusted_demo_entry_only(tmp_path: Path) -> None:
    featured = DEMO.model_copy(update={"featured_rule": "refund_le_paid"})
    settings = ServerSettings(db_path=tmp_path / "s.db", workspaces_root=tmp_path / "ws", bob_mode="replay",
                              demo_repos=[featured])
    store = Store(settings.db_path)
    make = default_session_factory(settings, Allowlist())
    demo = RepoSpec(kind="demo", ref=DEMO.ref.upper(), commit=DEMO.commit)
    other = RepoSpec(kind="demo", ref="rook-demo/other", commit=DEMO.commit)
    sessions = [make(RunSpec(f"r_{i:012d}", repo, "", SessionOptions(hosted=True), "u_alice", EventBus(store), store))
                for i, repo in enumerate((demo, other))]
    assert [s._featured_rule for s in sessions] == ["refund_le_paid", None]  # type: ignore[attr-defined]
    store.close()


def test_a_request_cannot_set_the_featured_rule(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    with TestClient(app, base_url=BASE) as client:
        for body in ({**NEW_RUN, "featured_rule": "x"},
                     {**NEW_RUN, "repo": {**NEW_RUN["repo"], "featured_rule": "x"}},
                     {**NEW_RUN, "options": {"auto": False, "featured_rule": "x"}}):
            assert client.post(f"{API}/runs", json=body, headers=ALICE).status_code == 400
    assert factory.sessions == {}


def test_module_app_is_built_from_the_environment_on_first_access(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOK_DB_PATH", str(tmp_path / "env.db"))
    monkeypatch.setenv("ROOK_BOB_MODE", "replay")
    monkeypatch.setattr(app_module, "_app", None)
    built: Any = app_module.app
    assert built is app_module.app
    assert built.state.rook.settings.db_path == tmp_path / "env.db"
    with TestClient(built, base_url=BASE) as client:
        assert client.get(f"{API}/health").json()["bob_mode"] == "replay"
    with pytest.raises(AttributeError):
        _ = app_module.nothing_here  # type: ignore[attr-defined]
