"""ROOK-023 AC: a recorded full run on minishop, PREPARE -> verified fix -> SHIP (a local branch).

The run replays the committed Bob recordings of the pipeline tickets (understand, rules, design,
diagnose, surgeon) plus `session_minishop`: the calls whose prompts differ inside a whole run. Why they
differ: the pipeline tests sanity-checked rules on a *fixed* minishop and diagnosed/fixed a
counterexample of the hand-written model, while a real run checks rules on the buggy app it started
(so the engine flags the admin-export rule `already_broken` and the Rule Critic is told), the user
approves only the refund rule (so DESIGN gets other inputs), and the counterexample comes from the
Mapper's own model (so DIAGNOSE and FIX get other inputs). Every call replays for 0 coins.

To re-record only the calls that miss (costs Bobcoins, run by hand):

    source ~/.bob-key.env
    export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH
    ROOK_RECORD_DIR=tests/fixtures/recordings/session_minishop \
        uv run pytest -m bob -s tests/unit/test_session_recorded.py

Then replace the local workspace path (`/tmp/pytest-of-<user>/...`) in the new files with `/workspace`.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from session_helpers import (
    FIXTURES,
    LocalLauncher,
    answer_questions,
    history,
    minishop_source,
    phases,
    tree,
)

from rook.agents.bob import AgentResult, BobClient
from rook.agents.recorder import recording_key
from rook.core.events import EVENT_TYPES, EventBus, clear_secrets
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec, git

RECORDINGS = FIXTURES / "recordings"
SESSION_RECORDINGS = RECORDINGS / "session_minishop"
CHAIN = ["understand_minishop", "rules_minishop", "design_minishop", "diagnose_minishop", "surgeon_minishop",
         "session_minishop"]
OPTIONS: dict[str, Any] = {"seed": 1, "concurrency": 1, "search_sequences": 5_000, "search_seconds": 300.0,
                           "verify_sequences": 1_500, "verify_seconds": 120.0}
_SECRET_PATTERNS = [re.compile(p) for p in (r"bob_prod_", r"\bgh[ps]_[A-Za-z0-9]{8}", r"-----BEGIN",
                                            r"\beyJ[A-Za-z0-9_\-]{8,}")]


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def chained_recordings(tmp_path: Path) -> Path:
    """All committed recordings in one folder (a BobClient replays from one folder)."""
    folder = tmp_path / "recordings"
    folder.mkdir()
    for name in CHAIN:
        for path in sorted((RECORDINGS / name).glob("*")):
            shutil.copy2(path, folder / path.name)
    return folder


class HybridClient:
    """Replays a call when its recording exists; otherwise calls Bob live and records it (when `record_dir`
    is set) or fails like a missing recording. Records which agents missed."""

    def __init__(self, bus: EventBus, run_id: str, replay_dir: Path, record_dir: Path | None) -> None:
        self.bus, self.run_id = bus, run_id
        self.replayer = BobClient(bus, run_id, mode="replay", recordings_dir=replay_dir, replay_speed=1e9,
                                  replay_max_gap=0.0)
        self.live = BobClient(bus, run_id, mode="record", recordings_dir=record_dir, timeout=900) \
            if record_dir else None
        self._use(self.replayer)
        self.missing: list[str] = []
        self.live_cost = 0.0

    def _use(self, client: BobClient) -> None:  # what the edit tape looks at (mode, record, recorder)
        self.mode, self.record, self.recorder = client.mode, client.record, client.recorder

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        if not self.replayer.recorder.path(recording_key(slug, prompt)).exists():
            self.missing.append(agent_id)
            if self.live is not None:
                self._use(self.live)
                try:
                    return await self.live.call(agent_id, slug, prompt, workspace, output_model, max_turns)
                finally:
                    self.live_cost = self.live.total_cost
                    print(f"recorded {agent_id}: coins so far {self.live_cost:.4f}")
        self._use(self.replayer)
        return await self.replayer.call(agent_id, slug, prompt, workspace, output_model, max_turns)


def refund_rule_ids(data: dict[str, Any]) -> list[str]:
    return [r["id"] for r in data["payload"]["rules"]
            if r["accepted"] and "refund" in r["check"] and "paid" in r["check"]]


def user(data: dict[str, Any]) -> Any:
    """The human: approves only the refund rule (minishop has four bugs; one run fixes one), then yes."""
    return refund_rule_ids(data) if data["kind"] == "approve_rules" else "yes"


async def full_run(tmp_path: Path, record_dir: Path | None = None) -> tuple[Session, HybridClient, Path]:
    src = minishop_source(tmp_path)
    replay_dir = chained_recordings(tmp_path)
    clients: list[HybridClient] = []

    def client(bus: EventBus, run_id: str, ws: Path) -> HybridClient:
        clients.append(HybridClient(bus, run_id, replay_dir, record_dir))
        return clients[0]

    options = SessionOptions(**OPTIONS, budget=0.5 if record_dir else 1.5)  # recording is capped at 0.5 coins
    session = Session(RepoSpec(kind="local", ref=str(src)), "find and fix a bug", options,
                      workspaces_root=tmp_path / "workspaces", client_factory=client,
                      launcher_factory=LocalLauncher())
    asked = answer_questions(session, user)
    before = tree(src)
    result = await session.run()
    await asked
    assert tree(src) == before  # the user's folder is untouched
    print(f"\n{result.status}: {result.summary}\nmissing recordings: {clients[0].missing}")
    return session, clients[0], src


def check_full_run(session: Session) -> None:
    result = session.result
    assert result is not None and result.status == "done", result
    assert result.verified and result.cx_ids == ["cx_001"]
    assert phases(session) == ["PREPARE", "SCOUT", "START_APP", "MAP", "RULES", "APPROVE", "DESIGN", "SEARCH",
                               "SHRINK", "REPLAY", "SAVE", "DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY",
                               "APPROVE_PR", "SHIP", "DONE"]
    events = history(session)
    types = [e.type for e in events]
    for e in events:
        EVENT_TYPES[e.type].model_validate(e.data)
    assert types[0] == "run.created" and types[-1] == "run.finished"
    # The buggy app breaks the admin-export rule on the first request: kept, flagged, shown to the user.
    (approve,) = [e.data for e in events if e.type == "question.asked" and e.data["kind"] == "approve_rules"]
    flagged = [r for r in approve["payload"]["rules"] if r["already_broken"]]
    assert flagged and all(r["accepted"] and r["kind"] == "response" and "403" in r["check"] for r in flagged)
    (approved,) = [e.data for e in events if e.type == "rules.approved"]
    assert approved["rule_ids"] == refund_rule_ids(approve)
    order = ["violation.found", "counterexample.saved", "diagnosis.ready", "fix.ready", "verify.done",
             "fix.committed", "run.finished"]
    positions = [types.index(t) for t in order]
    assert positions == sorted(positions), order
    (violation,) = [e.data for e in events if e.type == "violation.found" and "refund" in e.data["rule_id"]]
    (diagnosis,) = [e.data for e in events if e.type == "diagnosis.ready"]
    assert diagnosis["reviewed"] is True and diagnosis["file"] == "app.py"
    (done,) = [e.data for e in events if e.type == "verify.done"]
    assert done["verified"] is True and done["cx_id"] == "cx_001"
    (committed,) = [e.data for e in events if e.type == "fix.committed"]
    assert committed["branch"] == "rook/fix-cx-001"
    assert violation["rule_id"] == next(e.data for e in events if e.type == "counterexample.saved")["rule_id"]
    # SHIP in test mode: a local branch in the workspace repo, holding the fix, the test and Rook's files.
    ws = result.workspace
    assert ws is not None
    assert git(ws, "rev-parse", "--abbrev-ref", "HEAD") == "rook/fix-cx-001"
    assert git(ws, "rev-parse", "main") != committed["commit"]  # the default branch is untouched
    shipped = git(ws, "show", "--name-only", "--format=", committed["commit"]).split()
    assert shipped == committed["files"]
    assert {"app.py", "rook/rook.yaml", "rook/counterexamples/cx_001.json"} <= set(shipped)
    assert "already = order.refunded_total if is_fixed else 0" not in (ws / "app.py").read_text()
    assert git(ws, "status", "--porcelain", "--", *shipped) == ""
    assert not git(ws, "remote")  # nothing to push to: test mode never pushes


async def test_recorded_full_run_ships_a_verified_fix(tmp_path: Path) -> None:
    """AC: the recorded run goes PREPARE -> verified fix -> SHIP, with the right event order, for 0 coins."""
    session, client, _ = await full_run(tmp_path)
    assert client.missing == [], f"no recording for: {client.missing}"
    check_full_run(session)
    finished = [e.data for e in history(session) if e.type == "agent.finished"]
    assert finished and all(f["recorded"] and f["ok"] for f in finished)
    assert session.state.coins_spent == 0.0 and client.replayer.total_cost == 0.0
    agents = [f["agent"] for f in finished]
    for agent in ("scout", "mechanic", "mapper", "lawmaker", "rule_critic", "test_designer", "strategist",
                  "detective", "diag_reviewer", "surgeon", "fix_reviewer"):
        assert agent in agents, agent


def test_session_recordings_hold_no_secrets() -> None:
    files = sorted(SESSION_RECORDINGS.glob("*"))
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text
        assert "pytest-of-" not in text and "/home/" not in text  # no local paths or user names


@pytest.mark.bob
async def test_record_the_missing_calls_of_a_full_run(tmp_path: Path) -> None:
    """Replays what is recorded and records only the calls that miss. Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    target = Path(record_dir).resolve() if record_dir else tmp_path / "rec"
    session, client, _ = await full_run(tmp_path, target)
    print(f"recorded calls: {client.missing}; coins used: {client.live_cost:.4f}")
    check_full_run(session)
