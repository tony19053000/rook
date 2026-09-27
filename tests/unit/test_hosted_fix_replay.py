"""ROOK-039d: a hosted guest run on the minishop demo, in replay mode, reaches a verified fix for 0 coins.

This is the server's own path (`server/runs.default_session_factory` with ROOK_BOB_MODE=replay): a demo
repo from the allowlist (the entry of deploy/demos/allowlist.yaml, pointed at a local copy of the app),
the app as a real uvicorn subprocess (ProcessSandbox) run from the run's workspace copy, and the entry's
allowlisted `test` command. Both answers a guest gives on the web are covered: approve the refund rule only,
or every proposed rule (the web UI's approve button). Every Bob call replays a committed recording.

The calls only this route makes (the Surgeon and Fix Reviewer on the hosted evidence) live in
`tests/fixtures/recordings/hosted_minishop`. To record the ones that miss (costs Bobcoins, run by hand):

    source ~/.bob-key.env
    export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH
    ROOK_RECORD_DIR=tests/fixtures/recordings/hosted_minishop \
        uv run pytest -m bob -s tests/unit/test_hosted_fix_replay.py

Then replace local paths in the new files (`/tmp/pytest-of-<user>/...` becomes `/workspace`).
"""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from session_helpers import FIXTURES, answer_questions, history, phases
from test_session_recorded import CHAIN, RECORDINGS, HybridClient, refund_rule_ids

from rook.agents.recorder import recording_key
from rook.core.events import EVENT_TYPES, EventBus, clear_secrets
from rook.core.session import Session, SessionOptions, unverified_summary
from rook.core.workspace import RepoSpec
from rook.engine.verifier import CheckResult, VerifyResult
from rook.sandbox.allowlist import Allowlist, AllowlistEntry

ROOT = Path(__file__).parents[2]
HOSTED = RECORDINGS / "hosted_minishop"
DEMO_FILES = ("app.py", "test_minishop_app.py")  # what deploy/Dockerfile installs as the demo app
BUDGET = 0.75  # a recording run's cap (coins); a replay spends 0
RECORDED_AGENTS = frozenset({"surgeon", "fix_reviewer"})


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


class CappedClient(HybridClient):
    """A HybridClient that records only the FIX-phase agents (this route's own calls) and stops at BUDGET coins
    (the Session's own cap sees a replaying client). Any other missing call fails like a missing recording."""

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: Any,
                   max_turns: int = 8, max_cost: float | None = None) -> Any:
        if self.live is not None and self.live_cost >= BUDGET:
            raise RuntimeError(f"recording budget of {BUDGET} coins spent")
        if agent_id not in RECORDED_AGENTS and not self.replayer.recorder.path(recording_key(slug, prompt)).exists():
            self.missing.append(agent_id)
            self._use(self.replayer)
            return await self.replayer.call(agent_id, slug, prompt, workspace, output_model, max_turns)
        return await super().call(agent_id, slug, prompt, workspace, output_model, max_turns, max_cost)


def demo_entry(tmp_path: Path) -> AllowlistEntry:
    """The deployed allowlist entry of rook-demo/minishop, with its app dir at a local copy of the app."""
    raw = yaml.safe_load((ROOT / "deploy" / "demos" / "allowlist.yaml").read_text())
    (entry,) = [e for e in raw["entries"] if e["repo"] == "rook-demo/minishop"]
    app_dir = tmp_path / "demos" / "minishop"
    app_dir.mkdir(parents=True)
    for name in DEMO_FILES:
        shutil.copy2(FIXTURES / "minishop" / name, app_dir / name)
    return AllowlistEntry(**{**entry, "app_dir": app_dir})


def replay_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "recordings"
    folder.mkdir()
    for name in [*CHAIN, HOSTED.name]:
        for path in sorted((RECORDINGS / name).glob("*")):
            shutil.copy2(path, folder / path.name)
    return folder


def guest(approve: str) -> Any:
    def answer(data: dict[str, Any]) -> Any:
        if data["kind"] == "approve_rules":
            return "all" if approve == "all" else (refund_rule_ids(data) or "all")
        if data["kind"] == "menu":  # a failed agent: end with a report, like the smoke tests
            return "report"
        return "yes"

    return answer


async def hosted_run(tmp_path: Path, approve: str, record_dir: Path | None = None,
                     seed: int = 7) -> tuple[Session, HybridClient]:
    entry = demo_entry(tmp_path)
    replays = replay_dir(tmp_path)
    clients: list[HybridClient] = []

    def client(bus: EventBus, run_id: str, ws: Path) -> HybridClient:
        clients.append(CappedClient(bus, run_id, replays, record_dir))
        return clients[0]

    # The server's options (routes/runs.py) with a fixed seed and a shorter VERIFY search, to keep the test fast:
    # neither reaches a prompt (the evidence Bob sees does not depend on them).
    options = SessionOptions(auto=False, hosted=True, seed=seed, verify_sequences=400, verify_seconds=30)
    session = Session(RepoSpec(kind="demo", ref=entry.repo, commit=entry.commit), "find and fix a bug", options,
                      workspaces_root=tmp_path / "workspaces", client_factory=client,
                      allowlist=Allowlist([entry]), run_workspace=True)
    asked = answer_questions(session, guest(approve))
    result = await session.run()
    await asked
    print(f"\n[{approve}] {result.status}: {result.summary}\nmissing recordings: {clients[0].missing}")
    return session, clients[0]


def check_verified_fix(session: Session) -> None:
    result = session.result
    assert result is not None and result.status == "done", result
    assert result.verified, result.summary
    seen = phases(session)
    assert seen[-7:] == ["DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE"], seen
    events = history(session)
    for e in events:
        EVENT_TYPES[e.type].model_validate(e.data)
    types = [e.type for e in events]
    order = ["counterexample.saved", "diagnosis.ready", "fix.ready", "verify.done", "fix.committed", "run.finished"]
    positions = [types.index(t) for t in order]
    assert positions == sorted(positions), order
    (done,) = [e.data for e in events if e.type == "verify.done"]
    assert done["verified"] is True, done
    assert session.state.coins_spent == 0.0


def check_honestly_unverified(session: Session) -> None:
    """Approving every rule (docs/04 section 3.8): minishop has four planted bugs. The admin-export one is found,
    diagnosed and fixed (the Fix Reviewer approves), but VERIFY's fresh search then breaks another approved rule
    (02 section 7.7). On the hosted replay route the run then ends `done`: the fix is NOT verified, reverted and
    never committed, and the summary says which rule is still broken (no paths, no recording keys)."""
    result = session.result
    assert result is not None and result.status == "done", result
    assert not result.verified
    events = history(session)
    for e in events:
        EVENT_TYPES[e.type].model_validate(e.data)
    types = [e.type for e in events]
    assert phases(session).count("DIAGNOSE") == 1 and phases(session)[-2:] == ["VERIFY", "DONE"], phases(session)
    assert "fix.ready" in types and "fix.committed" not in types
    (saved, *_) = [e.data for e in events if e.type == "counterexample.saved"]
    assert saved["rule_id"] == "admin_export_forbidden_for_customer"
    (done,) = [e.data for e in events if e.type == "verify.done"]
    assert done["verified"] is False and "fresh_search" in done["summary"], done
    (fresh,) = [e.data for e in events if e.type == "verify.step" and e.data["check"] == "fresh_search"
                and e.data["status"] != "running"]
    broken = fresh["detail"].split("new violation of rule ")[1].split()[0]
    assert fresh["status"] == "failed" and broken != saved["rule_id"], fresh
    assert result.summary == (
        "Found and saved cx_001; the fix for rule admin_export_forbidden_for_customer was written and the exact "
        f"replay now passes, but the fresh search found another approved rule still broken: {broken}. NOT "
        "verified: the patch was reverted and not shipped. Run `rook` from the CLI on your own copy to continue.")
    assert result.workspace is not None
    assert (result.workspace / "app.py").read_bytes() == (FIXTURES / "minishop" / "app.py").read_bytes()
    assert session.state.coins_spent == 0.0


async def test_a_hosted_replay_run_approving_the_refund_rule_verifies_the_fix(tmp_path: Path) -> None:
    session, client = await hosted_run(tmp_path, "refund")
    assert client.missing == [], f"no recording for: {client.missing}"
    check_verified_fix(session)
    finished = [e.data for e in history(session) if e.type == "agent.finished"]
    assert finished and all(f["recorded"] for f in finished)
    assert {"surgeon", "fix_reviewer"} <= {f["agent"] for f in finished}
    assert client.replayer.total_cost == 0.0


async def test_a_hosted_replay_run_approving_every_rule_is_honestly_unverified(tmp_path: Path) -> None:
    session, client = await hosted_run(tmp_path, "all")
    check_honestly_unverified(session)
    finished = [e.data for e in history(session) if e.type == "agent.finished"]
    assert client.missing == [], f"no recording for: {client.missing}"  # no second DIAGNOSE
    assert finished and all(f["ok"] and f["recorded"] for f in finished)
    assert {"surgeon", "fix_reviewer"} <= {f["agent"] for f in finished}
    assert client.replayer.total_cost == 0.0


def _verification(fresh_detail: str, replay: bool = True) -> VerifyResult:
    return VerifyResult("cx_001", [CheckResult("replay", replay, "held 10/10"),
                                   CheckResult("project_tests", True, "exit 0"),
                                   CheckResult("regression_test", True, "exit 0"),
                                   CheckResult("fresh_search", False, fresh_detail)])


def test_the_unverified_summary_names_the_rule_still_broken_and_no_paths() -> None:
    cx = SimpleNamespace(cx_id="cx_002", rule=SimpleNamespace(id="refund_le_paid"))
    text = unverified_summary(cx, _verification("new violation of rule stock_ok (seed 5:verify:1)"))  # type: ignore[arg-type]
    assert text == ("Found and saved cx_002; the fix for rule refund_le_paid was written and the exact replay now "
                    "passes, but the fresh search found another approved rule still broken: stock_ok. NOT verified: "
                    "the patch was reverted and not shipped. Run `rook` from the CLI on your own copy to continue.")
    other = unverified_summary(cx, _verification("rule error: /tmp/x boom", replay=False))  # type: ignore[arg-type]
    assert "these checks failed: replay, fresh_search" in other and "exact replay" not in other
    assert "/tmp" not in other and "boom" not in other


def test_hosted_recordings_hold_no_local_paths() -> None:
    for path in sorted(HOSTED.glob("*")):
        text = path.read_text(encoding="utf-8")
        assert "pytest-of-" not in text and "/home/" not in text and "/tmp/" not in text, path.name
        assert "bob_prod_" not in text and "eyJ" not in text, path.name
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text


@pytest.mark.bob
@pytest.mark.parametrize("approve", ["refund", "all"])
async def test_record_the_missing_calls_of_a_hosted_run(tmp_path: Path, approve: str) -> None:
    """Replays what is recorded and records only the calls that miss. Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    target = Path(record_dir).resolve() if record_dir else tmp_path / "rec"
    target.mkdir(parents=True, exist_ok=True)
    session, client = await hosted_run(tmp_path, approve, target)
    print(f"recorded calls: {client.missing}; coins used: {client.live_cost:.4f}")
    if approve == "refund":
        check_verified_fix(session)
    elif not RECORDED_AGENTS & set(client.missing):  # nothing new: the replay goes on to VERIFY
        check_honestly_unverified(session)
    # else a live Surgeon call means the workspace no longer holds only taped edits: VERIFY is skipped (02 §8)
