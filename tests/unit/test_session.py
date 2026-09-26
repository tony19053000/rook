"""ROOK-023: the Session + Conductor with a scripted fake Bob, on minishop served in-process.

The recorded (real Bob) full run is in test_session_recorded.py. Here: auto mode vs a user answering,
the VERIFY-fail -> DIAGNOSE loop (with the workspace reverted in between), the coin budget, cancel at
several points (with no process or sandbox left behind), persistence, and workspace preparation.
"""

import asyncio
import base64
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from session_helpers import (
    BASE,
    PYTEST,
    LocalApp,
    LocalLauncher,
    ScriptedClient,
    answer_questions,
    history,
    minishop_source,
    phases,
    say_yes,
    tree,
)
from test_pipeline_diagnose import REFUND_CHECK
from test_pipeline_fix import BUGGY_LINE, FIXED_LINE, GOOD_TEST, TEST_PATH, patch_app, review, writes
from test_pipeline_understand import MAPPER_PARTS, MINISHOP_MODEL, SUMMARY

from rook.agents.bob import BobClient
from rook.agents.schemas import SandboxPlan
from rook.agents.understand import StartedApp
from rook.core.events import EVENT_TYPES, EventBus, QuestionAsked, RepoSummary, clear_secrets
from rook.core.rails import RunState
from rook.core.session import (
    BudgetedClient,
    BudgetSpent,
    SandboxTracker,
    Session,
    SessionOptions,
    mark_interrupted,
    read_run,
    valid_answer,
)
from rook.core.workspace import (
    LocalBranchShipper,
    RepoSpec,
    ShipRequest,
    Workspace,
    check_ship_paths,
    git,
    prepare_workspace,
)
from rook.sandbox.allowlist import Allowlist, AllowlistEntry, NotAllowlistedError
from rook.sandbox.base import ExecResult, Sandbox
from rook.store.repo import RunRecord, Store

RULES = {r.id: r.model_dump(mode="json", by_alias=True, exclude_none=True) | {"status": "proposed"}
         for r in MINISHOP_MODEL.rules}
PLAN = {"mode": "command", "build": "pip install fastapi uvicorn", "start": "uvicorn app:app --port 8000",
        "port": 8000, "health_path": "/health", "env_required": [],
        "env_defaults": {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}}  # the fixture's default, not a secret
DOUBLE_REFUND = [{"action": "create_product", "params": {"price": 100, "stock": 5}},
                 {"action": "buy", "params": {"quantity": 1}},
                 {"action": "refund", "params": {"amount": 60}},
                 {"action": "refund", "params": {"amount": 60}}]
WRONG_LINE = "        already = 0  # reviewed but wrong\n"
FAST: dict[str, Any] = {"seed": 1, "concurrency": 2, "search_sequences": 3_000, "search_seconds": 60.0,
                        "verify_sequences": 300, "verify_seconds": 30.0}


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def approve_all(*ids: str) -> dict[str, Any]:
    return {"verdicts": [{"rule_id": i, "verdict": "approve", "reason": "backed by the code"} for i in ids]}


def diagnosis(line: int = REFUND_CHECK) -> dict[str, Any]:
    return {"file": "app.py", "line": line, "explanation": "refund() ignores earlier refunds",
            "evidence": ["step 4: refunded 120 > paid 100"]}


def edit_app(line: str) -> Any:
    return lambda ws: writes({"app.py": patch_app(ws, line)}, "compare with the running total")(ws)


def replies(**overrides: list[Any]) -> dict[str, list[Any]]:
    """A full, happy run: the refund rule only, a reviewed diagnosis, a native test, an approved fix."""
    base: dict[str, list[Any]] = {
        "scout": [SUMMARY],
        "mechanic": [PLAN],
        "mapper": [MAPPER_PARTS],
        "lawmaker": [{"rules": [RULES["refund_le_paid"]]}],
        "rule_critic": [approve_all("refund_le_paid")],
        "test_designer": [{"scenarios": [{"name": "double refund", "rule_id": "refund_le_paid",
                                          "steps": DOUBLE_REFUND}]}],
        "strategist": [{"weights": {"refund": 2.0}, "focus": ["refund_le_paid"], "reason": "refunds add up"}],
        "detective": [diagnosis()],
        "diag_reviewer": [{"verdict": "approve", "reason": "the cited line ignores earlier refunds"}],
        "surgeon": [writes({TEST_PATH: GOOD_TEST}), edit_app(FIXED_LINE)],
        "fix_reviewer": [review("approve")],
        "coordinator": [{"next": "report", "reason": "nothing else to try"}],
        "guide": [{"answer": "Rook is searching."}],
    }
    base.update(overrides)
    return base


class Harness:
    """Builds a Session with a scripted Bob and in-process minishop; keeps the pieces for assertions."""

    def __init__(self, tmp_path: Path, script: dict[str, list[Any]], *, launcher: Any = None,
                 store: Store | None = None, cost: float = 0.0, delay: float = 0.0, **options: Any) -> None:
        self.src = minishop_source(tmp_path)
        self.before = tree(self.src)
        self.launcher = launcher or LocalLauncher()
        self.clients: list[ScriptedClient] = []

        def client(bus: EventBus, run_id: str, ws: Path) -> ScriptedClient:
            self.clients.append(ScriptedClient(bus, run_id, script, cost=cost, delay=delay))
            return self.clients[-1]

        self.session = Session(RepoSpec(kind="local", ref=str(self.src)), "find bugs",
                               SessionOptions(**{**FAST, **options}), store=store,
                               workspaces_root=tmp_path / "workspaces", client_factory=client,
                               launcher_factory=self.launcher)

    @property
    def client(self) -> ScriptedClient:
        return self.clients[0]

    def events(self, event_type: str) -> list[dict[str, Any]]:
        return [e.data for e in history(self.session) if e.type == event_type]


FULL_PHASES = ["PREPARE", "SCOUT", "START_APP", "MAP", "RULES", "APPROVE", "DESIGN", "SEARCH", "SHRINK",
               "REPLAY", "SAVE", "DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE"]


# --- auto mode vs a user answering ---


async def test_auto_mode_runs_to_a_shipped_branch(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), auto=True)
    result = await h.session.run()
    assert result.status == "done" and result.verified, result.summary
    assert phases(h.session) == FULL_PHASES
    for e in history(h.session):
        EVENT_TYPES[e.type].model_validate(e.data)
    answered = h.events("question.answered")
    assert [a["by"] for a in answered] == ["auto"] * 3
    kinds = [q["kind"] for q in h.events("question.asked")]
    assert kinds == ["approve_rules", "fix", "pr"]
    assert answered[0]["answer"] == ["refund_le_paid"]  # critic-approved rules only
    (committed,) = h.events("fix.committed")
    ws = result.workspace
    assert ws is not None and committed["branch"] == "rook/fix-cx-001" == result.ship.branch  # type: ignore[union-attr]
    assert set(committed["files"]) == {"app.py", TEST_PATH, "rook/rook.yaml", "rook/counterexamples/cx_001.json"}
    assert git(ws, "rev-parse", "--abbrev-ref", "HEAD") == "rook/fix-cx-001"
    assert git(ws, "log", "-1", "--format=%s", "main") == "rook: baseline copy of minishop"
    assert FIXED_LINE in (ws / "app.py").read_text()
    assert tree(h.src) == h.before  # the user's folder is untouched
    assert h.launcher.apps[0].stopped >= 1  # the sandbox is stopped at the end of the run
    assert "coordinator" not in h.client.agents()  # no branch point on the default path
    assert h.session.state.verified
    assert h.events("run.finished") == [{"status": "done", "summary": result.summary}]


async def test_a_user_answers_the_questions_and_the_run_waits_for_them(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(lawmaker=[{"rules": list(RULES.values())}],
                                  rule_critic=[approve_all(*RULES)]))
    seen: list[str] = []

    def user(data: dict[str, Any]) -> Any:
        seen.append(data["kind"])
        # At each question the run is paused: nothing after the question has happened yet.
        assert history(h.session)[-1].type == "question.asked"
        if data["kind"] == "approve_rules":
            rules = {r["id"]: r for r in data["payload"]["rules"]}
            # The buggy app breaks the admin rule on the first request: shown flagged, with the reason.
            admin = rules["admin_export_forbidden"]
            assert admin["accepted"] and admin["already_broken"] is True
            assert "engine: it may already be broken on the first request" in admin["reason"]
            assert not any(r["already_broken"] for i, r in rules.items() if i != "admin_export_forbidden")
            return ["refund_le_paid", "made_up_rule"]
        return "yes"

    asked = answer_questions(h.session, user)
    result = await h.session.run()
    await asked
    assert result.status == "done" and result.verified, result.summary
    assert seen == ["approve_rules", "fix", "pr"]
    assert [a["by"] for a in h.events("question.answered")] == ["user"] * 3
    assert h.events("rules.approved") == [{"rule_ids": ["refund_le_paid"]}]
    assert any("made_up_rule" in log["text"] for log in h.events("log"))
    assert h.session.state.fix_approved


async def test_auto_mode_never_approves_a_rule_flagged_already_broken(tmp_path: Path) -> None:
    # The critic approves all four rules; the admin rule is flagged by the engine (buggy app), so auto
    # mode leaves it out even though the critic approved it.
    h = Harness(tmp_path, replies(lawmaker=[{"rules": list(RULES.values())}],
                                  rule_critic=[approve_all(*RULES)]), auto=True,
                search_sequences=1, verify_sequences=1)
    await h.session.run()
    (asked, *_) = h.events("question.asked")
    flagged = [r["id"] for r in asked["payload"]["rules"] if r["already_broken"]]
    assert flagged == ["admin_export_forbidden"]
    (answered, *_) = h.events("question.answered")
    assert answered["by"] == "auto" and "admin_export_forbidden" not in answered["answer"]
    assert set(answered["answer"]) == set(RULES) - {"admin_export_forbidden"}
    assert "admin_export_forbidden" not in h.events("rules.approved")[0]["rule_ids"]
    assert any(log["text"].startswith("Auto mode does not approve admin_export_forbidden")
               for log in h.events("log"))


async def test_a_human_may_approve_a_flagged_rule(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(lawmaker=[{"rules": [RULES["admin_export_forbidden"]]}],
                                  rule_critic=[approve_all("admin_export_forbidden")]))
    policy = lambda d: ["admin_export_forbidden"] if d["kind"] == "approve_rules" else "no"
    asked = answer_questions(h.session, policy)
    result = await h.session.run()
    await asked
    assert h.events("rules.approved") == [{"rule_ids": ["admin_export_forbidden"]}]
    # The engine then proves it: the search breaks the rule in one step.
    (saved, *_) = h.events("counterexample.saved")
    assert saved["rule_id"] == "admin_export_forbidden" and len(saved["steps"]) == 1
    assert result.status == "done" and result.cx_ids == ["cx_001"] and not result.verified


async def test_saying_no_to_the_fix_leaves_the_app_unchanged(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies())
    asked = answer_questions(h.session, lambda d: "all" if d["kind"] == "approve_rules" else "no")
    result = await h.session.run()
    await asked
    assert result.status == "done" and not result.verified and result.cx_ids == ["cx_001"]
    assert "not approved" in result.summary
    assert "surgeon" not in h.client.agents() and "FIX" not in phases(h.session)
    assert BUGGY_LINE in (result.workspace / "app.py").read_text()  # type: ignore[operator]
    assert phases(h.session)[-2:] == ["APPROVE_FIX", "DONE"]


async def test_auto_mode_does_not_fix_an_unreviewed_diagnosis(tmp_path: Path) -> None:
    reject = {"verdict": "reject", "reason": "the line does not explain it"}
    h = Harness(tmp_path, replies(diag_reviewer=[reject]), auto=True)
    result = await h.session.run()
    (ready,) = h.events("diagnosis.ready")
    assert ready["reviewed"] is False
    assert h.events("question.answered")[-1]["answer"] == "no"
    assert "surgeon" not in h.client.agents() and not result.verified


def test_answers_are_checked_for_shape() -> None:
    def q(kind: str) -> QuestionAsked:
        return QuestionAsked(question_id="q_1", kind=kind, text="?",  # type: ignore[arg-type]
                             options=[{"id": "retry", "label": "r"}, {"id": "stop", "label": "s"}])

    assert valid_answer(q("approve_rules"), "all") and valid_answer(q("approve_rules"), ["a", "b"])
    assert not valid_answer(q("approve_rules"), "some") and not valid_answer(q("approve_rules"), [1])
    assert valid_answer(q("fix"), "yes") and valid_answer(q("fix"), True) and not valid_answer(q("fix"), 3)
    assert valid_answer(q("menu"), "retry") and not valid_answer(q("menu"), "ship")
    assert valid_answer(q("setup_value"), "pw") and not valid_answer(q("setup_value"), "a\x00")


async def test_answer_rejects_unknown_questions_and_chat_needs_a_live_run(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), auto=True)
    assert h.session.answer("q_nope", "yes") is False
    assert h.session.chat("hello?") is False  # not started
    await h.session.run()
    assert h.session.chat("hello?") is False  # finished
    with pytest.raises(RuntimeError):
        await h.session.run()


async def test_chat_during_the_run_gets_a_guide_answer(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), auto=True)

    async def ask_during_search() -> None:
        async for e in h.session.events():
            if e.type == "run.phase" and e.data["phase"] == "SEARCH":
                assert h.session.chat("where are we?")
                return

    chatter = asyncio.create_task(ask_during_search())
    await h.session.run()
    await chatter
    messages = h.events("chat.message")
    assert {"role": "user", "text": "where are we?"} in messages
    assert {"role": "guide", "text": "Rook is searching."} in messages


async def test_setup_values_come_from_options_or_the_user(tmp_path: Path) -> None:
    plan = {**PLAN, "env_required": ["MINISHOP_ADMIN_PASSWORD"], "env_defaults": {}}
    store = Store(tmp_path / "rook.db")
    h = Harness(tmp_path / "a", replies(mechanic=[plan]), auto=True, store=store,
                setup_values={"MINISHOP_ADMIN_PASSWORD": "admin-pass"})
    result = await h.session.run()
    assert result.verified, result.summary
    assert "admin-pass" not in str([e.data for e in history(h.session)])  # a setup value is never published
    store.close()
    assert b"admin-pass" not in (tmp_path / "rook.db").read_bytes()  # nor persisted with the run

    user = Harness(tmp_path / "b", replies(mechanic=[plan]))

    async def answer_setup() -> None:
        async for e in user.session.events():
            if e.type == "question.asked":
                value = "admin-pass" if e.data["kind"] == "setup_value" else say_yes(e.data)
                assert user.session.answer(e.data["question_id"], value)

    task = asyncio.create_task(answer_setup())
    result = await user.session.run()
    await task
    assert result.verified, result.summary
    answered = user.events("question.answered")[0]
    assert answered["answer"] == {"name": "MINISHOP_ADMIN_PASSWORD", "provided": True}

    auto = Harness(tmp_path / "c", replies(mechanic=[plan]), auto=True)  # auto mode never invents a secret
    result = await auto.session.run()
    assert result.status == "failed" and "no value was given" in result.summary


# --- VERIFY fails -> back to DIAGNOSE ---


async def test_a_failed_verification_goes_back_to_diagnose_with_the_workspace_reverted(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(
        detective=[diagnosis(), diagnosis()],
        surgeon=[writes({TEST_PATH: GOOD_TEST}), edit_app(WRONG_LINE), edit_app(FIXED_LINE)],
        coordinator=[{"next": "diagnose", "reason": "the fix did not hold"}],
    ), auto=True)
    result = await h.session.run()
    assert result.status == "done" and result.verified, result.summary
    assert [d["verified"] for d in h.events("verify.done")] == [False, True]
    assert phases(h.session) == FULL_PHASES[:15] + ["DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR",
                                                    "SHIP", "DONE"]
    # The second fix patched the original buggy line: the wrong patch had been reverted.
    assert [r["files"] for r in h.events("fix.ready")] == [["app.py"], ["app.py"]]
    reverts = [log["text"] for log in h.events("log") if log["text"].startswith("Reverted the unverified patch")]
    assert len(reverts) == 1 and "app.py" in reverts[0]
    second = [p for a, p in h.client.calls if a == "detective"][1]
    assert "FAILED verification" in second and WRONG_LINE.strip() in second
    assert h.launcher.apps[0].restarts >= 3  # verify, revert, verify
    assert h.client.agents().count("coordinator") == 1
    assert FIXED_LINE in (result.workspace / "app.py").read_text()  # type: ignore[operator]


async def test_three_failed_verifications_are_reported_honestly(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(
        surgeon=[writes({TEST_PATH: GOOD_TEST}), edit_app(WRONG_LINE)],
        coordinator=[{"next": "diagnose", "reason": "try again"}],
    ), auto=True)
    result = await h.session.run()
    assert result.status == "done" and not result.verified
    assert "NOT verified" in result.summary and h.events("fix.committed") == []
    assert [d["verified"] for d in h.events("verify.done")] == [False, False, False]
    assert "SHIP" not in phases(h.session)
    blocked = [log["text"] for log in h.events("log") if "blocked by the rails" in log["text"]]
    assert blocked and "verification already failed 3 times" in blocked[-1]


# --- the budget ---


async def test_live_bob_is_refused_once_the_budget_is_spent(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), auto=True, cost=0.3, budget=0.5)
    result = await h.session.run()
    assert h.client.agents() == ["scout", "mechanic"]  # 0.6 coins spent: the Mapper call is refused
    assert result.status == "failed" and "coin budget" in result.summary
    refused = [log["text"] for log in h.events("log") if "refused" in log["text"]]
    assert refused and "Live Bob call to mapper refused" in refused[0]
    assert any("Coordinator not called" in log["text"] for log in h.events("log"))
    assert h.session.state.coins_spent == pytest.approx(0.6)


async def test_the_budget_client_caps_live_calls_and_lets_replays_through() -> None:
    state = RunState(budget=1.0)
    bus = EventBus()
    seen: list[float | None] = []

    class Inner:
        def __init__(self, mode: str) -> None:
            self.bus, self.run_id, self.mode = bus, "r_x", mode

        async def call(self, *args: Any, max_turns: int = 8, max_cost: float | None = None) -> Any:
            seen.append(max_cost)
            return "ok"

    live = BudgetedClient(Inner("live"), state)  # type: ignore[arg-type]
    replay = BudgetedClient(Inner("replay"), state)  # type: ignore[arg-type]
    state.coins_spent = 0.25
    await live.call("scout", "rook-scout", "p", ".", RepoSummary)
    assert seen == [0.75] and live.mode == "live"
    state.coins_spent = 1.0
    with pytest.raises(BudgetSpent):
        await live.call("scout", "rook-scout", "p", ".", RepoSummary)
    assert await replay.call("scout", "rook-scout", "p", ".", RepoSummary) == "ok"  # recordings are free
    assert seen == [0.75, None]


# --- cancel ---


def alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return state != "Z"


async def wait_dead(*pids: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(alive(p) for p in pids):
            return True
        await asyncio.sleep(0.05)
    return False


def other_tasks() -> list[asyncio.Task[Any]]:
    return [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]


async def test_cancel_during_the_search_stops_it_and_the_sandbox(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), launcher=LocalLauncher(fixed=True), auto=True,
                search_sequences=10_000_000, search_seconds=600.0)

    async def cancel_when_searching() -> None:
        async for e in h.session.events():
            if e.type == "engine.progress" and e.data["worker"] == "runner" and (e.data.get("count") or 0) > 20:
                h.session.cancel()
                h.session.cancel()  # twice is fine
                return

    canceller = asyncio.create_task(cancel_when_searching())
    started = time.monotonic()
    result = await asyncio.wait_for(h.session.run(), 60)
    await canceller
    assert result.status == "cancelled" and time.monotonic() - started < 60
    assert phases(h.session)[-1] == "SEARCH"
    assert h.events("run.finished") == [{"status": "cancelled", "summary": "The run was cancelled."}]
    assert h.launcher.apps[0].stopped >= 1
    runner_done = [e for e in h.events("engine.finished") if e["worker"] == "runner"]
    assert runner_done and runner_done[-1]["ok"] is False  # the search stopped
    await asyncio.sleep(0)
    assert other_tasks() == []  # no search worker, Guide or answer task is left


FAKE_BOB = """\
import os, subprocess, sys, time
child = subprocess.Popen(["sleep", "300"])
with open(os.environ["ROOK_FAKE_PIDS"], "w") as fh:
    fh.write(f"{os.getpid()} {child.pid}")
print('{"type":"message","role":"assistant","content":"thinking"}', flush=True)
time.sleep(300)
"""


async def test_cancel_during_a_bob_call_kills_its_process_group(tmp_path: Path) -> None:
    script = tmp_path / "bob"
    script.write_text(f"#!{sys.executable}\n{FAKE_BOB}")
    script.chmod(0o755)
    pidfile = tmp_path / "pids"
    src = minishop_source(tmp_path)

    def client(bus: EventBus, run_id: str, ws: Path) -> BobClient:
        return BobClient(bus, run_id, bin=script, mode="live", env={"ROOK_FAKE_PIDS": str(pidfile)},
                         recordings_dir=tmp_path / "rec", timeout=120)

    session = Session(RepoSpec(kind="local", ref=str(src)), options=SessionOptions(**FAST, auto=True),
                      workspaces_root=tmp_path / "ws", client_factory=client, launcher_factory=LocalLauncher())
    run = asyncio.create_task(session.run())
    for _ in range(400):
        if pidfile.exists() and len(pidfile.read_text().split()) == 2:
            break
        await asyncio.sleep(0.05)
    bob_pid, child_pid = map(int, pidfile.read_text().split())
    assert alive(bob_pid) and alive(child_pid)
    session.cancel()
    result = await asyncio.wait_for(run, 30)
    assert result.status == "cancelled"
    assert await wait_dead(bob_pid, child_pid), "a bob process survived the cancel"
    assert phases(session)[-1] == "SCOUT"


class SlowSandbox(Sandbox):
    """A 'sandbox' that is a real process; stop() kills it."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(["sleep", "300"], stdin=subprocess.DEVNULL, start_new_session=True)
        self.stops = 0

    def start(self, plan: Any = None) -> str:
        return BASE

    def stop(self) -> None:
        self.stops += 1
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()

    def restart(self) -> str:
        return BASE

    def exec(self, cmd: Any, timeout: float = 600.0) -> ExecResult:
        return ExecResult(0, "", "")

    def logs(self, tail: int = 200) -> str:
        return ""


class SlowLauncher:
    """Starts the app process, then takes a while to become 'healthy' (like a Docker build)."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.sandboxes: list[SlowSandbox] = []

    def __call__(self, workspace: Workspace, run_id: str) -> Any:
        def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
            sandbox = SlowSandbox()
            self.sandboxes.append(sandbox)
            self.started.set()
            time.sleep(1.0)  # the health check, still running when the run is cancelled
            return StartedApp(sandbox=sandbox, base_url=BASE)

        return launch


async def test_cancel_during_the_sandbox_start_leaves_no_app_running(tmp_path: Path) -> None:
    launcher = SlowLauncher()
    h = Harness(tmp_path, replies(), launcher=launcher, auto=True)
    run = asyncio.create_task(h.session.run())
    assert await asyncio.to_thread(launcher.started.wait, 30)
    h.session.cancel()
    result = await asyncio.wait_for(run, 30)
    assert result.status == "cancelled"
    (sandbox,) = launcher.sandboxes
    assert sandbox.stops == 1 and sandbox.proc.poll() is not None  # stopped once the start returned
    assert await wait_dead(sandbox.proc.pid)
    assert h.events("sandbox.ready") == []


async def test_cancel_before_the_run_starts(tmp_path: Path) -> None:
    h = Harness(tmp_path, replies(), auto=True)
    h.session.cancel()
    result = await h.session.run()
    assert result.status == "cancelled" and h.clients == []
    assert [e.type for e in history(h.session)] == ["run.created", "run.finished"]


def test_the_tracker_stops_a_launch_that_finishes_after_close() -> None:
    tracker = SandboxTracker()
    sandbox = SlowSandbox()
    gate = threading.Event()

    def launcher(plan: Any, values: Any, summary: Any) -> StartedApp:
        gate.wait(5)
        return StartedApp(sandbox=sandbox, base_url=BASE)

    wrapped = tracker.wrap(launcher)
    errors: list[Exception] = []
    thread = threading.Thread(target=lambda: _catch(errors, wrapped, None, {}, None))
    thread.start()
    while tracker.inflight == 0:
        time.sleep(0.01)
    tracker.close(timeout=0.05)  # gives up waiting; the launch stops its own sandbox when it returns
    gate.set()
    thread.join(5)
    assert sandbox.stops == 1 and errors and "cancelled" in str(errors[0])
    with pytest.raises(Exception, match="cancelled"):
        wrapped(None, {}, None)  # type: ignore[arg-type]


def _catch(errors: list[Exception], fn: Any, *args: Any) -> None:
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001
        errors.append(exc)


class ProcessApp(LocalApp):
    """minishop in-process, plus a real app process (`sleep`), like a container: `exec` runs commands in
    their own process groups and `stop` kills the app and everything it runs."""

    def __init__(self, ws: Path, env: Mapping[str, str]) -> None:
        super().__init__(ws, env)
        self.proc = subprocess.Popen(["sleep", "300"], stdin=subprocess.DEVNULL, start_new_session=True)
        self.execs: list[subprocess.Popen[str]] = []
        self._lock = threading.Lock()
        self._stopped = False

    def stop(self) -> None:
        self.stopped += 1
        with self._lock:
            self._stopped = True
            procs = [self.proc, *self.execs]
        for proc in procs:
            if proc.poll() is None:
                os.killpg(proc.pid, 9)
            proc.wait()

    def exec(self, cmd: Any, timeout: float = 600.0) -> ExecResult:
        argv = [*PYTEST, *cmd[1:]] if cmd[0] == "pytest" else list(cmd)
        env = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": str(self.ws.parent),
               "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        with self._lock:
            if self._stopped:
                return ExecResult(137, "", "stopped")
            proc = subprocess.Popen(argv, cwd=self.ws, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, start_new_session=True)
            self.execs.append(proc)
        out, err = proc.communicate(timeout=timeout)
        return ExecResult(proc.returncode, out, err)

    def pids(self) -> list[int]:
        with self._lock:
            return [p.pid for p in (self.proc, *self.execs)]


class ProcessLauncher:
    def __init__(self) -> None:
        self.apps: list[ProcessApp] = []

    def __call__(self, workspace: Workspace, run_id: str) -> Any:
        def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
            app = ProcessApp(workspace.path, {**plan.env_defaults, **values})
            self.apps.append(app)
            return StartedApp(sandbox=app, base_url=BASE, transport=app.transport)

        return launch


def descendants() -> set[int]:
    """Every live process below this test process."""
    found: set[int] = set()
    todo = [os.getpid()]
    while todo:
        pid = todo.pop()
        for task in Path(f"/proc/{pid}/task").glob("*"):
            try:
                children = (task / "children").read_text().split()
            except OSError:
                continue
            for child in map(int, children):
                if child not in found and alive(child):
                    found.add(child)
                    todo.append(child)
    return found


def cmdline(pid: int) -> str:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[:3]
        wchan = Path(f"/proc/{pid}/wchan").read_text()
        return f"{cmd} state={stat} wchan={wchan} ppid-cmd={Path(f'/proc/{stat[1]}/comm').read_text().strip()}"
    except OSError:
        return f"{pid} (gone)"


CANCEL_AT = [(p, True) for p in FULL_PHASES[:-1]] + [(k, False) for k in ("approve_rules", "fix", "pr")]


@pytest.mark.parametrize(("at", "auto"), CANCEL_AT, ids=[a for a, _ in CANCEL_AT])
async def test_cancel_at_every_phase_leaves_no_process_behind(tmp_path: Path, at: str, auto: bool) -> None:
    """AC: cancel at every phase (auto) and at every open question (a user) leaves no sandbox, app, test or
    other child process, no answer future and no task behind; the run ends `cancelled`."""
    before = descendants()
    launcher = ProcessLauncher()
    h = Harness(tmp_path, replies(), launcher=launcher, auto=auto)

    def observe(event: Any) -> None:  # synchronous, inside publish: the cancel lands in this phase
        if (event.type == "run.phase" and event.data["phase"] == at) or (
                event.type == "question.asked" and event.data["kind"] == at):
            h.session.cancel()

    async def user() -> None:  # answers every question except the one the run is cancelled at
        async for e in h.session.events():
            if e.type == "question.asked" and e.data["kind"] != at:
                assert h.session.answer(e.data["question_id"], say_yes(e.data))

    h.session.bus.add_observer(h.session.run_id, observe)
    answering = None if auto else asyncio.create_task(user())
    result = await asyncio.wait_for(h.session.run(), 120)
    if answering is not None:
        await asyncio.wait_for(answering, 10)
    assert result.status == "cancelled", result.summary
    seen = phases(h.session)
    assert "DONE" not in seen and (at in seen or at in [q["kind"] for q in h.events("question.asked")])
    assert h.events("run.finished") == [{"status": "cancelled", "summary": "The run was cancelled."}]
    assert h.session.pending_questions() == []
    pids = [pid for app in launcher.apps for pid in app.pids()]
    assert all(app.stopped >= 1 for app in launcher.apps)
    assert await wait_dead(*pids, timeout=5), "a sandbox/app/test process survived the cancel"
    deadline = time.monotonic() + 10
    while descendants() - before and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    left = descendants() - before
    assert left == set(), f"a child process survived the cancel: {[cmdline(pid) for pid in left]}"
    await asyncio.sleep(0)
    assert other_tasks() == []


# --- persistence ---


async def test_a_run_is_persisted_and_can_be_read_back(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    h = Harness(tmp_path, replies(), store=store, auto=True)
    result = await h.session.run()
    view = read_run(store, result.run_id)
    assert view is not None
    assert view.record.status == "done" and view.record.finished_at and view.record.repo_kind == "local"
    streamed = [e async for e in h.session.events()]  # the bus replays the stored events
    assert [e.model_dump() for e in view.events] == [e.model_dump() for e in streamed]
    assert [e.seq for e in view.events] == list(range(1, len(view.events) + 1))
    assert view.state.phase == "DONE" and view.state.verified and view.state.auto
    assert view.snapshot["status"] == "done" and view.snapshot["counters"]["counterexamples"] == 1
    (cx,) = view.counterexamples
    assert cx.id == f"{result.run_id}_cx_001" and cx.status == "verified" and cx.data["cx_id"] == "cx_001"
    # Resume after a given seq (what SSE `?after=` reads for a finished run).
    tail = store.events_after(result.run_id, len(view.events) - 2)
    assert [e.type for e in tail] == ["run.phase", "run.finished"]
    assert read_run(store, "r_missing") is None


def test_interrupted_runs_are_marked_failed(tmp_path: Path) -> None:
    store = Store(tmp_path / "rook.db")
    for run_id in ("r_dead", "r_live"):
        store.insert_run(RunRecord(id=run_id, repo_kind="local", repo_ref="/x", status="running",
                                   created_at="2026-09-26T08:00:00Z"))
    assert mark_interrupted(store, live={"r_live"}) == ["r_dead"]
    view = read_run(store, "r_dead")
    assert view is not None and view.record.status == "failed" and view.events[-1].type == "run.finished"
    assert store.get_run("r_live").status == "running"  # type: ignore[union-attr]


# --- workspace preparation ---


def test_a_local_folder_is_copied_and_never_touched(tmp_path: Path) -> None:
    src = minishop_source(tmp_path)
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "the user's own history")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "big.js").write_text("x")
    (src / "notes.txt").write_text("uncommitted work\n")
    before = tree(src)
    ws = prepare_workspace(RepoSpec(kind="local", ref=str(src)), "r_abcdefghijkl", root=tmp_path / "wss")
    assert ws.path == (tmp_path / "wss" / "r_abcdefghijkl").resolve()
    assert (ws.path / "notes.txt").read_text() == "uncommitted work\n"  # the working tree, as it is now
    assert not (ws.path / "node_modules").exists()
    assert git(ws.path, "log", "--format=%s") == "rook: baseline copy of minishop"  # a fresh repo
    (ws.path / "app.py").write_text("changed in the workspace\n")
    assert tree(src) == before
    with pytest.raises(Exception, match="already exists"):
        prepare_workspace(RepoSpec(kind="local", ref=str(src)), "r_abcdefghijkl", root=tmp_path / "wss")
    with pytest.raises(Exception, match="may not be inside"):
        prepare_workspace(RepoSpec(kind="local", ref=str(src)), "r_abcdefghijkm", root=src / "inside")
    with pytest.raises(Exception, match="not a folder"):
        prepare_workspace(RepoSpec(kind="local", ref=str(src / "app.py")), "r_abcdefghijkn", root=tmp_path / "w")


def test_demo_repos_must_be_allowlisted(tmp_path: Path) -> None:
    sha = "a" * 40
    with pytest.raises(NotAllowlistedError, match="not an allowlisted demo repo"):
        prepare_workspace(RepoSpec(kind="demo", ref="acme/shop", commit=sha), "r_abcdefghijkl", root=tmp_path)
    with pytest.raises(NotAllowlistedError):  # the hosted server runs demo repos only
        prepare_workspace(RepoSpec(kind="local", ref=str(tmp_path)), "r_abcdefghijkl", root=tmp_path / "w",
                          hosted=True)
    assert not (tmp_path / "r_abcdefghijkl").exists()
    src = minishop_source(tmp_path)
    allowlist = Allowlist([AllowlistEntry(repo="acme/shop", commit=sha, app_dir=src, start=["{python}", "app.py"])])
    ws = prepare_workspace(RepoSpec(kind="demo", ref="acme/shop", commit=sha), "r_abcdefghijkm",
                           root=tmp_path / "w", allowlist=allowlist)
    assert ws.demo is not None and (ws.path / "app.py").is_file()


async def test_a_session_on_a_repo_that_is_not_allowlisted_fails_cleanly(tmp_path: Path) -> None:
    session = Session(RepoSpec(kind="demo", ref="acme/shop", commit="b" * 40),
                      options=SessionOptions(auto=True, hosted=True), workspaces_root=tmp_path)
    result = await session.run()
    assert result.status == "failed" and "not an allowlisted demo repo" in result.summary
    assert [e.data["phase"] for e in history(session) if e.type == "run.phase"] == ["PREPARE"]


def test_a_github_clone_passes_the_token_only_through_the_env(tmp_path: Path, monkeypatch: Any) -> None:
    origin = tmp_path / "server" / "acme" / "shop.git"
    src = minishop_source(tmp_path)
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "upstream")
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(origin)], check=True, capture_output=True)
    token = "ghs_" + "T0k3nForTest0nly"
    calls: list[tuple[list[str], dict[str, str]]] = []
    real_popen = subprocess.Popen

    def spy(argv: list[str], **kwargs: Any) -> Any:
        calls.append((list(argv), dict(kwargs.get("env") or {})))
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("rook.core.workspace.subprocess.Popen", spy)
    ws = prepare_workspace(RepoSpec(kind="github", ref="acme/shop"), "r_abcdefghijkl", root=tmp_path / "w",
                           token=token, github_url=f"file://{tmp_path / 'server'}")
    assert (ws.path / "app.py").is_file() and ws.base_commit == git(src, "rev-parse", "HEAD")
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    clone_argv, clone_env = next(c for c in calls if "clone" in c[0])
    assert all(token not in a and basic not in a for a in clone_argv)
    assert clone_env["GIT_CONFIG_VALUE_0"] == f"AUTHORIZATION: basic {basic}"
    assert token not in (ws.path / ".git" / "config").read_text()
    with pytest.raises(Exception, match="owner/name"):
        prepare_workspace(RepoSpec(kind="github", ref="--upload-pack=x"), "r_abcdefghijkm", root=tmp_path / "w")


# --- SHIP ---


async def test_the_local_shipper_commits_only_the_given_files_to_a_new_branch(tmp_path: Path) -> None:
    src = minishop_source(tmp_path)
    ws = prepare_workspace(RepoSpec(kind="local", ref=str(src)), "r_abcdefghijkl", root=tmp_path / "w").path
    (ws / "app.py").write_text("fixed\n")
    (ws / "stray.txt").write_text("not shipped\n")
    shipped = await LocalBranchShipper().ship(ws, ShipRequest("cx_002", ["app.py"], "Rook: fix", "body"))
    assert shipped.branch == "rook/fix-cx-002" and not shipped.pushed
    assert git(ws, "show", "--name-only", "--format=", shipped.commit) == "app.py"
    assert git(ws, "status", "--porcelain") == "?? stray.txt"
    os.symlink("/etc/passwd", ws / "link")
    for bad in (["../x"], ["/etc/passwd"], ["link"], [".git/config"], ["missing.py"]):
        with pytest.raises((ValueError, FileNotFoundError)):
            check_ship_paths(ws, bad)
