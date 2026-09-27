"""ROOK-039c: a hosted demo run executes the Surgeon's patch only in replay mode (server config).

Full Sessions on minishop as an allowlisted demo repo, with the real ProcessSandbox (a uvicorn subprocess)
and a scripted Bob whose Surgeon edits stand in for the committed edit tapes:
- replay mode + the server's grant: the app and the allowlisted `test` command run from the workspace copy,
  the native regression test is accepted and VERIFY passes (engine-decided);
- live mode: the app runs from the pristine app dir, VERIFY is skipped and the summary says so honestly;
- the grant alone is not enough (the client must replay), and no request can set it.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from server_helpers import ALICE, BASE, NEW_RUN, make_app
from session_helpers import ScriptedClient, history, minishop_source, phases
from test_pipeline_fix import FIXED_LINE, TEST_PATH
from test_session import FAST, FULL_PHASES, replies

from rook.core import session as session_module
from rook.core.events import EventBus, clear_secrets
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec
from rook.sandbox import Allowlist, AllowlistEntry, ProcessSandbox
from rook.server.config import ServerSettings
from rook.server.runs import RunSpec, default_session_factory
from rook.store.repo import Store

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")

SHA = "3" * 40
REPO = "rook-demo/minishop"
PYTEST = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "asyncio_mode=auto"]
API = "/api/v1"


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


class TapedClient(ScriptedClient):
    """A scripted Bob that looks like a BobClient in `mode` (what `edit_tape.tape_mode` reads). Its recorder
    folder holds no tapes: the scripted Surgeon replies make the edits a replayed tape would make."""

    def __init__(self, bus: EventBus, run_id: str, script: dict[str, list[Any]], mode: str, tapes: Path) -> None:
        super().__init__(bus, run_id, script)
        self.mode, self.record = mode, False
        self.recorder = SimpleNamespace(dir=tapes)


class Hosted:
    """A hosted-style Session on the allowlisted minishop demo; records every ProcessSandbox it starts."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str, run_workspace: bool) -> None:
        app_dir = minishop_source(tmp_path)
        self.entry = AllowlistEntry(
            repo=REPO, commit=SHA, app_dir=app_dir,
            start=["{python}", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "{port}"],
            env={"MINISHOP_ADMIN_PASSWORD": "admin-pass"},  # the fixture's built-in default, not a secret
            commands={"test": PYTEST},
        )
        self.boxes: list[ProcessSandbox] = []
        boxes = self.boxes

        class Recording(ProcessSandbox):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                boxes.append(self)

        monkeypatch.setattr(session_module, "ProcessSandbox", Recording)
        (tmp_path / "tapes").mkdir()
        self.clients: list[TapedClient] = []

        def client(bus: EventBus, run_id: str, ws: Path) -> TapedClient:
            self.clients.append(TapedClient(bus, run_id, replies(), mode, tmp_path / "tapes"))
            return self.clients[-1]

        self.session = Session(RepoSpec(kind="demo", ref=REPO, commit=SHA), "find bugs",
                               SessionOptions(**FAST, auto=True, hosted=True), workspaces_root=tmp_path / "ws",
                               client_factory=client, allowlist=Allowlist([self.entry]), run_workspace=run_workspace)

    def events(self, event_type: str) -> list[dict[str, Any]]:
        return [e.data for e in history(self.session) if e.type == event_type]

    def logs(self) -> list[str]:
        return [e["text"] for e in self.events("log")]


async def test_replay_mode_runs_the_workspace_and_verifies_the_fix(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    h = Hosted(tmp_path, monkeypatch, mode="replay", run_workspace=True)
    result = await h.session.run()
    assert result.status == "done" and result.verified, result.summary
    assert phases(h.session) == FULL_PHASES
    ws = result.workspace
    assert ws is not None and FIXED_LINE in (ws / "app.py").read_text()
    assert h.boxes and all(box.run_dir == ws.resolve() for box in h.boxes)
    # The allowlisted test command (not the Scout's "pytest -q") ran the Surgeon's native test from the workspace.
    assert [e["test_path"] for e in h.events("counterexample.saved")][-1] == TEST_PATH
    assert not any(text.startswith("Regression test: using the generated") for text in h.logs())
    (done,) = h.events("verify.done")
    assert done["verified"] is True
    assert all(step["status"] == "passed" for step in h.events("verify.step") if step["status"] != "running")
    assert (h.entry.app_dir / "app.py").read_text().count(FIXED_LINE) == 0  # the pristine copy is untouched


async def test_live_mode_runs_the_pristine_app_and_says_the_fix_is_not_verified(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    h = Hosted(tmp_path, monkeypatch, mode="live", run_workspace=False)
    result = await h.session.run()
    assert result.status == "done" and not result.verified
    assert "NOT verified" in result.summary and "CLI" in result.summary
    assert phases(h.session) == FULL_PHASES[:FULL_PHASES.index("FIX") + 1] + ["DONE"]  # no VERIFY, no SHIP
    assert not h.events("verify.done") and not h.events("fix.committed")
    assert h.boxes and all(box.run_dir == h.entry.app_dir for box in h.boxes)
    assert any(text.startswith("Regression test: using the generated") for text in h.logs())  # as before
    assert "coordinator" not in h.clients[0].agents()  # no verify_failed branch point: no Bob call wasted


async def test_the_grant_needs_a_replaying_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    h = Hosted(tmp_path, monkeypatch, mode="live", run_workspace=True)  # misconfigured: granted, but live Bob
    result = await h.session.run()
    assert not result.verified and "NOT verified" in result.summary
    assert h.boxes and all(box.run_dir == h.entry.app_dir for box in h.boxes)
    assert any("only replayed runs may run patched code" in text for text in h.logs())


@pytest.mark.parametrize(("mode", "granted"), [("replay", True), ("live", False), ("record", False)])
def test_the_server_grants_the_workspace_from_its_own_config_only(tmp_path: Path, mode: str, granted: bool) -> None:
    settings = ServerSettings.model_validate({"db_path": tmp_path / "s.db", "workspaces_root": tmp_path / "ws",
                                              "bob_mode": mode})
    store = Store(settings.db_path)
    make = default_session_factory(settings, Allowlist())
    spec = RunSpec("r_cccccccccccc", RepoSpec(kind="demo", ref=REPO, commit=SHA), "find bugs",
                   SessionOptions(hosted=True), "u_alice", EventBus(store), store)
    session = make(spec)
    assert isinstance(session, Session) and session._run_workspace is granted
    store.close()


def test_no_request_can_ask_for_the_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SessionOptions(run_workspace=True)  # type: ignore[call-arg]
    with TestClient(make_app(tmp_path), base_url=BASE) as client:
        for body in ({**NEW_RUN, "options": {"auto": False, "run_workspace": True}},
                     {**NEW_RUN, "run_workspace": True}, {**NEW_RUN, "bob_mode": "replay"}):
            response = client.post(f"{API}/runs", json=body, headers=ALICE)
            assert response.status_code == 400 and "Extra inputs" in response.text, response.text
