"""The Session and its Conductor: one run through the phases of 02_ARCHITECTURE.md section 4.

PREPARE -> SCOUT -> START_APP -> MAP -> RULES -> APPROVE -> DESIGN -> SEARCH -> SHRINK -> REPLAY -> SAVE
-> DIAGNOSE -> APPROVE_FIX -> FIX -> VERIFY -> APPROVE_PR -> SHIP -> DONE

- Every phase is done by an existing pipeline or engine part; the Conductor only wires them together
  and publishes the phase events. The engine decides every pass/fail (CLAUDE.md rule 1).
- The rails state (`RunState`) and the Guide's snapshot are fed by the bus itself (synchronous
  observers), so a rails check made right after an event always sees it.
- The Coordinator (Bob) is asked only at branch points (an agent failed, the search found nothing, a
  verification failed); the rails accept its choice or fall back to the default. `ask_user` becomes a
  `menu` question.
- Questions (approve_rules, fix, pr, menu, setup_value) are `question.asked` events plus an answer
  future resolved by `answer()`. With `auto`, the Conductor answers them itself (`by: auto`): only
  critic-approved rules (never one flagged `already_broken`), only a reviewed diagnosis, and SHIP still makes a branch, never a push to the
  default branch. Setup values come from `options.setup_values` or the user, never from auto mode.
- Budget: live Bob calls are refused once the run's coin budget (or the daily cap) is spent
  (`BudgetedClient`); replays are free.
- Cancel: `cancel()` cancels the run task. That kills any running `bob` process group (BobClient),
  stops the search, waits for a sandbox that is still starting and stops every sandbox the run started.
- Persistence: with a `Store`, the bus stores every event and the run row is kept up to date;
  `read_run()` rebuilds a run's state from its events.
- Demo repos (ProcessSandbox) run the pristine allowlisted app unless the server grants `run_workspace`
  (replay mode only, 03 section 3): then the app and the entry's allowlisted `test` command run from the
  workspace copy, so VERIFY executes the Surgeon's patch. Without it a fix cannot be verified there, so
  VERIFY is skipped and the summary says so.

The public API (used by the CLI, ROOK-024/028, and the server, ROOK-029) is `Session.run()`,
`events(after)`, `answer()`, `chat()`, `cancel()` and `pending_questions()`. `answer`, `chat` and
`cancel` are thread-safe (the TUI calls them from its own thread).
"""

from __future__ import annotations

import asyncio
import secrets
import threading
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rook.agents import edit_tape
from rook.agents.bob import BobClient, BobError
from rook.agents.caller import AgentCaller
from rook.agents.coordinator import Coordinator
from rook.agents.design import DesignPipeline, DesignResult
from rook.agents.diagnose import DiagnosePipeline, DiagnosisResult
from rook.agents.fix import FixPipeline, FixResult, RegressionTest, SandboxHarness
from rook.agents.guide import Guide, RunSnapshot
from rook.agents.rules import RulesError, RulesPipeline, RulesResult
from rook.agents.schemas import SandboxPlan
from rook.agents.understand import (
    MODEL_PATH,
    Launcher,
    StartedApp,
    UnderstandError,
    Understanding,
    UnderstandPipeline,
    docker_launcher,
)
from rook.core import rails
from rook.core.events import (
    Event,
    EventBus,
    FixCommitted,
    Log,
    Phase,
    QuestionAnswered,
    QuestionAsked,
    QuestionOption,
    RepoRef,
    RepoSummary,
    RunCreated,
    RunFinished,
    RunOptions,
    RunPhase,
    now_ts,
    redact,
    redact_text,
    register_secret,
    validate_data,
)
from rook.core.rails import Branch, RunState, Step
from rook.core.workspace import (
    DEFAULT_ROOT,
    GITHUB_URL,
    LocalBranchShipper,
    RepoSpec,
    Shipper,
    ShipRequest,
    ShipResult,
    Workspace,
    new_run_id,
    prepare_workspace,
)
from rook.engine.executor import Executor
from rook.engine.pathguard import PathGuard, Snapshot
from rook.engine.replayer import Replayer
from rook.engine.runner import Runner, RunOutcome
from rook.engine.shrinker import Shrinker
from rook.engine.testrunner import TestRunner, parse_command
from rook.engine.verifier import Verifier, VerifyResult
from rook.export.counterexample import CX_DIR, Counterexample, next_cx_id, publish_saved, save_counterexample
from rook.model.schema import RookModel
from rook.sandbox.allowlist import DEFAULT_ALLOWLIST, TEST_COMMAND, Allowlist
from rook.sandbox.base import Sandbox, SandboxError
from rook.sandbox.process import ProcessSandbox
from rook.store.repo import CxStatus, RunRecord, Store

# Why a fix cannot be verified on a demo app that runs from its pristine copy (live mode on the server).
_PRISTINE_NOTE = ("the server runs the original demo app, never AI-patched code from a live run. "
                  "Run `rook` from the CLI to fix and verify on your own copy.")
LAUNCH_WAIT = 120.0  # how long cancel waits for a sandbox that is still starting, before stopping it
_ANSWER_MAX = 10_000
_RULE_IDS_MAX = 200
_PREFERRED: dict[Branch, tuple[Step, ...]] = {  # what auto mode picks in a menu, first allowed wins
    "agent_failed": ("retry", "skip", "report", "stop"),
    "search_exhausted": ("extend_search", "report", "stop"),
    "verify_failed": ("diagnose", "report", "stop"),
    "user_request": ("continue", "report", "stop"),
}
_LABELS: dict[str, str] = {
    "retry": "Try again", "skip": "Skip this step", "report": "Stop and report", "stop": "Stop the run",
    "extend_search": "Search once more", "diagnose": "Diagnose again", "continue": "Continue",
    "fix": "Fix it", "verify": "Verify", "ship": "Ship it",
}
_AGENT_OF_PHASE = {"SCOUT": "scout", "START_APP": "mechanic", "MAP": "mapper"}

RunStatus = Literal["done", "failed", "cancelled"]
ClientFactory = Callable[[EventBus, str, Path], AgentCaller]
LauncherFactory = Callable[[Workspace, str], Launcher]


class SessionOptions(BaseModel):
    """Only `auto` and `budget` are published (`run.created`); setup values are secrets."""

    model_config = ConfigDict(extra="forbid")

    auto: bool = False
    budget: float = Field(default=rails.DEFAULT_RUN_BUDGET, ge=0)
    daily_cap: float | None = Field(default=None, ge=0)
    daily_spent: float = Field(default=0.0, ge=0)
    seed: int = Field(default_factory=lambda: secrets.randbelow(2**31))
    search_sequences: int = Field(default=20_000, ge=1)
    search_seconds: float = Field(default=120.0, gt=0)
    verify_sequences: int = Field(default=20_000, ge=1)
    verify_seconds: float = Field(default=120.0, gt=0)
    concurrency: int = Field(default=16, ge=1)
    setup_values: dict[str, str] = Field(default_factory=dict)  # answers to setup_value questions
    hosted: bool = False  # the hosted server: demo repos only


@dataclass
class RunResult:
    run_id: str
    status: RunStatus
    summary: str
    workspace: Path | None = None
    cx_ids: list[str] = field(default_factory=list)
    verified: bool = False
    ship: ShipResult | None = None


class RunStop(Exception):
    """End the run early with an honest status and summary (not a bug)."""

    def __init__(self, status: RunStatus, summary: str) -> None:
        super().__init__(summary)
        self.status = status
        self.summary = summary


class BudgetSpent(BobError):
    """A live Bob call was refused because the run's coin budget (or the daily cap) is spent."""


class BudgetedClient:
    """Wraps the Bob client: a live call is refused once the budget is spent, and capped (`--max-cost`)
    at what is left. Replays are free. Other attributes (`mode`, `recorder`: the edit tape) pass through."""

    def __init__(self, inner: AgentCaller, state: RunState) -> None:
        self._inner = inner
        self._state = state
        self.bus: EventBus = inner.bus
        self.run_id: str = inner.run_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def remaining(self) -> float:
        left = self._state.budget - self._state.coins_spent
        if self._state.daily_cap is not None:
            left = min(left, self._state.daily_cap - self._state.daily_spent - self._state.coins_spent)
        return max(0.0, round(left, 4))

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> Any:
        if edit_tape.tape_mode(self._inner) != "replay":
            if not self._state.bob_allowed():
                why = f"the coin budget is spent ({self._state.coins_spent:.4f} of {self._state.budget:g})"
                await self.bus.publish(self.run_id, "log", Log(
                    level="warn", text=f"Live Bob call to {agent_id} refused: {why}"))
                raise BudgetSpent(f"{agent_id}: {why}")
            left = self.remaining()
            max_cost = left if max_cost is None else min(max_cost, left)
        return await self._inner.call(agent_id, slug, prompt, workspace, output_model, max_turns=max_turns,
                                      max_cost=max_cost)


class SandboxTracker:
    """Keeps every sandbox the run starts, so cancel and the end of the run can stop them all.

    A launch runs in a worker thread and cannot be interrupted: `close()` waits for launches still in
    flight (up to a timeout); a launch that finishes after `close()` stops its own sandbox."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._sandboxes: list[Sandbox] = []
        self._inflight = 0
        self._closed = False

    def wrap(self, launcher: Launcher) -> Launcher:
        def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
            with self._cond:
                if self._closed:
                    raise SandboxError("the run was cancelled")
                self._inflight += 1
            try:
                app = launcher(plan, values, summary)
                with self._cond:
                    closed = self._closed
                    if not closed:
                        self._sandboxes.append(app.sandbox)
                if closed:  # still counted in flight, so close() waits for this stop
                    app.sandbox.stop()
                    raise SandboxError("the run was cancelled")
                return app
            finally:
                with self._cond:
                    self._inflight -= 1
                    self._cond.notify_all()

        return launch

    def close(self, timeout: float = LAUNCH_WAIT) -> None:
        """Refuse new launches, wait for running ones, then stop every sandbox (safe to call twice)."""
        with self._cond:
            self._closed = True
            self._cond.wait_for(lambda: self._inflight == 0, timeout=timeout)
            boxes, self._sandboxes = self._sandboxes, []
        for sandbox in boxes:
            sandbox.stop()

    @property
    def inflight(self) -> int:
        with self._cond:
            return self._inflight


def process_launcher(workspace: Workspace, allowlist: Allowlist = DEFAULT_ALLOWLIST, *,
                     run_workspace: bool = False) -> Launcher:
    """The hosted launcher: the allowlisted demo app as a subprocess (a SandboxPlan is never executed),
    from its pristine app dir, or from the run's workspace copy with `run_workspace` (replay mode only)."""
    entry = workspace.demo
    if entry is None:
        raise ValueError("the process launcher runs allowlisted demo repos only")
    run_from = workspace.path if run_workspace else None

    def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
        env = {k: v for k, v in values.items() if k in entry.settable_env}
        sandbox = ProcessSandbox(entry.repo, entry.commit, allowlist=allowlist, env=env, workspace=run_from)
        return StartedApp(sandbox=sandbox, base_url=sandbox.start(plan))

    return launch


def _default_client(bus: EventBus, run_id: str, workspace: Path) -> AgentCaller:
    return BobClient(bus, run_id)


@dataclass
class _Pending:
    question: QuestionAsked
    future: asyncio.Future[Any]


def valid_answer(question: QuestionAsked, answer: Any) -> bool:
    """Whether `answer` has the right shape for the question's kind (the meaning is checked later)."""
    kind = question.kind
    if kind == "approve_rules":
        if isinstance(answer, str):
            return answer in ("all", "none")
        return (isinstance(answer, list) and len(answer) <= _RULE_IDS_MAX
                and all(isinstance(i, str) and 0 < len(i) <= 200 for i in answer))
    if kind in ("fix", "pr"):
        return isinstance(answer, bool) or (isinstance(answer, str) and 0 < len(answer) <= 100)
    if kind == "menu":
        return isinstance(answer, str) and answer in {o.id for o in question.options}
    return isinstance(answer, str) and 0 < len(answer) <= _ANSWER_MAX and "\x00" not in answer


class Session:
    def __init__(
        self,
        repo: RepoSpec,
        request: str = "",
        options: SessionOptions | None = None,
        *,
        bus: EventBus | None = None,
        store: Store | None = None,
        run_id: str | None = None,
        user_id: str | None = None,
        workspaces_root: Path = DEFAULT_ROOT,
        client_factory: ClientFactory = _default_client,
        launcher_factory: LauncherFactory | None = None,
        shipper: Shipper | None = None,
        token: str | None = None,
        allowlist: Allowlist = DEFAULT_ALLOWLIST,
        github_url: str = GITHUB_URL,
        run_workspace: bool = False,
    ) -> None:
        """`bus` should hold `store` when both are given (the server shares one bus); `token` is a GitHub
        installation token for a clone (never published or stored).

        `run_workspace` comes from trusted server config only (never a request): a demo app then runs from
        the workspace copy. It takes effect only while the Bob client replays (`_runs_workspace`)."""
        self.repo = repo
        self.request = request
        self.options = options or SessionOptions()
        self.run_id = run_id or new_run_id()
        self.store = store
        self.bus = bus or EventBus(store)
        self.user_id = user_id
        self.workspaces_root = workspaces_root
        self._client_factory = client_factory
        self._launcher_factory = launcher_factory
        self.shipper: Shipper = shipper or LocalBranchShipper()
        self._token = token
        self._allowlist = allowlist
        self._github_url = github_url
        self._run_workspace = run_workspace
        for value in self.options.setup_values.values():
            register_secret(value)
        self.state = RunState(auto=self.options.auto, budget=self.options.budget,
                              daily_cap=self.options.daily_cap, daily_spent=self.options.daily_spent)
        self.snapshot = RunSnapshot()
        self.bus.add_observer(self.run_id, self._observe)
        self.workspace: Workspace | None = None
        self.result: RunResult | None = None
        self._tracker = SandboxTracker()
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None
        self._started = False
        self._cancel_requested = False
        self._client: BudgetedClient | None = None
        self._coordinator: Coordinator | None = None
        self._guide: Guide | None = None
        self._harness: SandboxHarness | None = None
        self._app: StartedApp | None = None
        self._env: dict[str, str] = {}
        self._pre_fix: Snapshot | None = None
        self._cx_ids: list[str] = []
        self._sequences = 0
        self._verified = False
        self._ship: ShipResult | None = None

    # --- the public API ---

    def events(self, after: int = 0) -> AsyncIterator[Event]:
        """Every event of the run with seq > `after`: the stored replay, then the live tail."""
        return self.bus.subscribe(self.run_id, after=after)

    def pending_questions(self) -> list[QuestionAsked]:
        with self._lock:
            return [p.question for p in self._pending.values() if not p.future.done()]

    def answer(self, question_id: str, answer: Any) -> bool:
        """Answer an open question. False if it is not open or the answer has the wrong shape."""
        with self._lock:
            pending = self._pending.get(question_id)
        if pending is None or pending.future.done() or not valid_answer(pending.question, answer):
            return False

        def resolve() -> None:
            if not pending.future.done():
                pending.future.set_result(answer)

        self._call_soon(resolve)
        return True

    def chat(self, text: str) -> bool:
        """Send chat text to the Guide (answered as `chat.message` events). False if the run is not live."""
        guide = self._guide
        if guide is None or self.result is not None or not text.strip():
            return False
        self._call_soon(lambda: guide.ask(text))
        return True

    def cancel(self) -> None:
        """Stop the run: Bob processes, the search and every sandbox are stopped. Safe to call twice."""
        if self._cancel_requested:
            return
        self._cancel_requested = True
        task = self._task
        if task is not None:
            self._call_soon(task.cancel)

    async def run(self) -> RunResult:
        if self._started:
            raise RuntimeError("a session runs only once")
        self._started = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        status: RunStatus = "failed"
        summary = ""
        external_cancel = False
        try:
            await self._created()
            if self._cancel_requested:
                raise asyncio.CancelledError
            summary = await self._conduct()
            status = "done"
        except asyncio.CancelledError:
            status, summary = "cancelled", "The run was cancelled."
            external_cancel = not self._cancel_requested
            if not external_cancel and self._task is not None:
                self._task.uncancel()
        except RunStop as stop:
            status, summary = stop.status, stop.summary
        except Exception as exc:  # noqa: BLE001 - any failure ends the run honestly, with the reason
            summary = redact_text(f"{type(exc).__name__}: {exc}".splitlines()[0])[:500]
            await self._log("error", f"The run failed: {summary}")
        finally:
            await self._cleanup()
        await self._finish(status, summary)
        if external_cancel:
            raise asyncio.CancelledError
        assert self.result is not None
        return self.result

    # --- plumbing ---

    def _call_soon(self, fn: Callable[[], Any]) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            loop.call_soon(fn)
        else:
            loop.call_soon_threadsafe(fn)

    def _observe(self, event: Event) -> None:
        self.state.observe(event)
        self.snapshot.observe(event)

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.bus.publish(self.run_id, event_type, data)

    async def _phase(self, phase: Phase) -> None:
        await self._publish("run.phase", RunPhase(phase=phase))

    async def _log(self, level: Literal["info", "warn", "error"], text: str) -> None:
        await self._publish("log", Log(level=level, text=redact_text(text)))

    async def _created(self) -> None:
        if self.store is not None:
            self.store.insert_run(RunRecord(id=self.run_id, user_id=self.user_id, repo_kind=self.repo.kind,
                                            repo_ref=self.repo.ref, status="running", created_at=now_ts()))
        await self._publish("run.created", RunCreated(
            repo=RepoRef(kind=self.repo.kind, ref=self.repo.ref, name=self.repo.name),
            request=self.request, options=RunOptions(auto=self.options.auto, budget=self.options.budget)))

    async def _cleanup(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
        for p in pending:
            p.future.cancel()
        if self._guide is not None:
            await self._guide.aclose()
        await asyncio.shield(asyncio.to_thread(self._tracker.close, LAUNCH_WAIT))
        if self._pre_fix is not None:
            self._pre_fix.close()
            self._pre_fix = None

    async def _finish(self, status: RunStatus, summary: str) -> None:
        if status == "done":
            await self._phase("DONE")
        await self._publish("run.finished", RunFinished(status=status, summary=summary))
        await self.bus.close(self.run_id)
        if self.store is not None:
            self.store.update_run(self.run_id, status=status, finished_at=now_ts(),
                                  coins=round(self.state.coins_spent, 6))
        self.result = RunResult(run_id=self.run_id, status=status, summary=summary,
                                workspace=self.workspace.path if self.workspace else None,
                                cx_ids=list(self._cx_ids), verified=self._verified, ship=self._ship)

    # --- questions ---

    async def _await_answer(self, question: QuestionAsked, publish: bool) -> Any:
        assert self._loop is not None
        future: asyncio.Future[Any] = self._loop.create_future()
        with self._lock:
            self._pending[question.question_id] = _Pending(question, future)
        try:
            if publish:
                await self._publish("question.asked", question)
            return await future
        finally:
            with self._lock:
                self._pending.pop(question.question_id, None)

    async def _ask(self, kind: Any, text: str, options: Sequence[tuple[str, str]], payload: Any,
                   auto_answer: Any) -> Any:
        question = QuestionAsked(question_id=f"q_{uuid.uuid4().hex[:10]}", kind=kind, text=text,
                                 options=[QuestionOption(id=i, label=label) for i, label in options],
                                 payload=payload)
        by: Literal["user", "auto"]
        if self.options.auto:
            await self._publish("question.asked", question)
            answer, by = auto_answer, "auto"
        else:
            answer, by = await self._await_answer(question, publish=True), "user"
        await self._publish("question.answered", QuestionAnswered(question_id=question.question_id,
                                                                  answer=answer, by=by))
        return answer

    async def _setup_answer(self, question: QuestionAsked) -> str | None:
        """The UnderstandPipeline's answerer (it publishes the question and a redacted answer itself)."""
        name = str((question.payload or {}).get("name", ""))
        if name in self.options.setup_values:
            return self.options.setup_values[name]
        if self.options.auto:
            await self._log("warn", f"Auto mode has no value for {name}; pass it as a setup value")
            return None
        answer = await self._await_answer(question, publish=False)
        return answer if isinstance(answer, str) else None

    # --- branch points ---

    async def _decide(self, branch: Branch, *, agent: str | None = None, notes: list[str] | None = None) -> Step:
        assert self._coordinator is not None
        choice = await self._coordinator.decide(self.state, branch, agent=agent, notes=notes)
        who = "the Coordinator" if choice.source == "coordinator" else "the default"
        await self._log("info", f"Branch point {branch}: {choice.step} (chosen by {who}: {choice.reason})")
        if choice.step != "ask_user":
            return choice.step
        allowed = [s for s in rails.allowed_steps(self.state, branch, agent) if s != "ask_user"]
        options = [(s, _LABELS.get(s, s)) for s in allowed]
        auto = next((s for s in _PREFERRED[branch] if s in allowed), "stop")
        text = f"{'; '.join(notes or []) or branch}. What next?"
        answer = await self._ask("menu", text[:500], options, {"branch": branch, "agent": agent}, auto)
        return answer if rails.check_step(self.state, answer, agent) is None else "stop"  # type: ignore[return-value]

    async def _retry_or_stop(self, agent: str, why: str) -> None:
        step = await self._decide("agent_failed", agent=agent, notes=[why])
        if step == "retry":
            self.state.record_retry(agent)
            return
        raise RunStop("failed", why)

    # --- the Conductor ---

    async def _conduct(self) -> str:
        await self._phase("PREPARE")
        await self._prepare()
        known = await self._understand()
        rules, result = await self._rules(known)
        model = await self._approve(rules, result)
        if model is None:
            return "No rules were approved, so there was nothing to search."
        design = await DesignPipeline(self._bob(), self._ws(), model=model).run()
        outcome = await self._search(model, design)
        if outcome is None:
            return f"No counterexample in {self._sequences} sequences: every approved rule held."
        cx = await self._save(model, outcome)
        return await self._fix_and_ship(model, known, cx)

    def _bob(self) -> BudgetedClient:
        assert self._client is not None
        return self._client

    def _ws(self) -> Path:
        assert self.workspace is not None
        return self.workspace.path

    async def _prepare(self) -> None:
        # The copy runs in a worker thread, which a task cancel cannot stop. So a cancel sets `stop`, which
        # makes the thread kill its git process and remove the half-made workspace, and the run waits for
        # that before it ends: no git child and no stray workspace outlive the run.
        stop = threading.Event()
        job = asyncio.ensure_future(asyncio.to_thread(
            prepare_workspace, self.repo, self.run_id, root=self.workspaces_root, token=self._token,
            allowlist=self._allowlist, hosted=self.options.hosted, github_url=self._github_url, cancel=stop))
        try:
            self.workspace = await asyncio.shield(job)
        except asyncio.CancelledError:
            stop.set()
            while not job.done():  # the thread stops within one copy step or git poll
                try:
                    await asyncio.wait([job])
                except asyncio.CancelledError:
                    pass  # already cancelling: the CancelledError below ends the run
            if not job.cancelled() and job.exception() is None:
                self.workspace = job.result()
            raise
        ws = self.workspace.path
        for rel in self.workspace.skipped:
            await self._log("warn", f"Left out of the workspace for safety (a symlink leading outside the "
                                    f"repo, or a special file): {rel}")
        self._client = BudgetedClient(self._client_factory(self.bus, self.run_id, ws), self.state)
        self._coordinator = Coordinator(self._client, ws)
        self._guide = Guide(self._client, ws, self.snapshot, bob_allowed=self.state.bob_allowed)
        await self._log("info", f"Workspace ready: a copy of {self.repo.name} "
                                f"(base {self.workspace.base_commit[:12]})")
        if self._run_workspace and self.workspace.demo is not None and not self._runs_workspace():
            await self._log("warn", "The demo app runs from its original copy: only replayed runs may run "
                                    "patched code on this server")

    def _runs_workspace(self) -> bool:
        """A demo app may run from the workspace only when the server allows it AND every Bob call replays
        a committed recording, so every edit in the workspace comes from a reviewed edit tape."""
        return self._run_workspace and self._client is not None and edit_tape.tape_mode(self._client) == "replay"

    def _pristine_demo(self) -> bool:
        """The app runs from the untouched allowlisted app dir, so it never serves a patch."""
        return (self._launcher_factory is None and self.workspace is not None and self.workspace.demo is not None
                and not self._runs_workspace())

    def _launcher(self) -> Launcher:
        assert self.workspace is not None
        if self._launcher_factory is not None:
            launcher = self._launcher_factory(self.workspace, self.run_id)
        elif self.workspace.demo is not None:
            launcher = process_launcher(self.workspace, self._allowlist, run_workspace=self._runs_workspace())
        else:
            launcher = docker_launcher(self.workspace.path, self.run_id)
        return self._tracker.wrap(launcher)

    async def _understand(self) -> Understanding:
        while True:
            pipeline = UnderstandPipeline(self._bob(), self._ws(), answer=self._setup_answer,
                                          launcher=self._launcher())
            try:
                known = await pipeline.run()
            except UnderstandError as exc:
                await self._retry_or_stop(_AGENT_OF_PHASE.get(exc.phase, "mapper"), str(exc))
                continue
            self._app, self._env = known.app, dict(known.env)
            command: str | list[str] | None = known.summary.test_command or None
            demo = self.workspace.demo if self.workspace is not None else None
            if self._launcher_factory is None and demo is not None and self._runs_workspace():
                command = demo.commands.get(TEST_COMMAND)  # the allowlisted one, never the Scout's guess
            try:
                if command:
                    parse_command(command)
            except ValueError:
                await self._log("warn", "The project's test command could not be parsed; it is not run")
                command = None
            self._harness = SandboxHarness(known.app.sandbox, TestRunner(self.bus, self.run_id),
                                           base_url=known.app.base_url, test_command=command, env=self._env)
            return known

    async def _rules(self, known: Understanding) -> tuple[RulesPipeline, RulesResult]:
        while True:
            pipeline = RulesPipeline(self._bob(), self._ws(), model=known.model, summary=known.summary,
                                     app=known.app, env=known.env)
            try:
                return pipeline, await pipeline.run()
            except RulesError as exc:
                await self._retry_or_stop("lawmaker", str(exc))

    async def _approve(self, rules: RulesPipeline, result: RulesResult) -> RookModel | None:
        """APPROVE: the human (or auto mode) picks rules. Whatever the RULES phase put in the model can
        be approved; the pipeline refuses anything else. Auto mode takes only critic-approved rules, and
        never a rule flagged `already_broken` (it may be wrong: only a human may approve it)."""
        await self._phase("APPROVE")
        approvable = [r.id for r in result.model.rules]
        critic_ok = [o.rule.id for o in result.outcomes
                     if o.accepted and o.critic is not None and o.critic.verdict in ("approve", "revise")]
        flagged = [o.rule.id for o in result.outcomes if o.accepted and o.already_broken]
        auto_ids = [i for i in critic_ok if i not in flagged]
        payload = {"rules": [redact({
            "id": o.rule.id, "text": o.rule.text, "kind": o.rule.kind, "check": o.rule.check,
            "accepted": o.accepted,
            "reason": f"{o.reason}; engine: {o.engine.reason}" if o.already_broken else o.reason,
            "critic": o.critic.verdict if o.critic is not None else None,
            "already_broken": o.already_broken,
        }) for o in result.outcomes]}
        if not approvable:
            await self._log("warn", "No proposed rule passed the checks")
            return None
        if self.options.auto and flagged:
            await self._log("warn", f"Auto mode does not approve {', '.join(flagged)[:300]}: the app may "
                                    "already break it on the first request, or it is wrong (a human decides)")
        answer = await self._ask("approve_rules", f"Approve {len(approvable)} rules?",
                                 [("all", f"Approve {len(approvable)} rules"), ("none", "Reject all")],
                                 payload, auto_ids)
        if answer == "all":
            ids = approvable
        elif isinstance(answer, list):
            ids = [i for i in answer if i in approvable]
            ignored = [i for i in answer if i not in approvable]
            if ignored:
                await self._log("warn", f"Not approvable, ignored: {', '.join(ignored)[:300]}")
        else:
            ids = []
        if not ids:
            return None
        return await rules.approve(ids)

    def _executor(self, model: RookModel) -> Callable[[], Executor]:
        assert self._harness is not None and self._app is not None
        harness, app, env = self._harness, self._app, self._env
        return lambda: Executor(model, harness.base_url, transport=app.transport, env=env)

    async def _search(self, model: RookModel, design: DesignResult) -> RunOutcome | None:
        seed: int | str = self.options.seed
        while True:
            await self._phase("SEARCH")
            runner = Runner(model, self._executor(model), self.bus, self.run_id, seed=seed,
                            budget_sequences=self.options.search_sequences,
                            budget_seconds=self.options.search_seconds, concurrency=self.options.concurrency,
                            generator=design.generator(model, seed))
            outcome = await runner.run()
            self._sequences += outcome.sequences_run
            if outcome.violation is not None:
                return outcome
            step = await self._decide("search_exhausted",
                                      notes=[f"no violation in {outcome.sequences_run} sequences"])
            if step != "extend_search":
                return None
            self.state.search_extended = True
            seed = f"{seed}:extended"

    async def _save(self, model: RookModel, outcome: RunOutcome) -> Counterexample:
        """SHRINK -> REPLAY -> SAVE: the minimal, replayed counterexample is written as cx_NNN.json."""
        assert outcome.violation is not None and outcome.trace is not None
        seed = self.options.seed
        await self._phase("SHRINK")
        shrunk = await Shrinker(model, self._executor(model), self.bus, self.run_id, seed=seed).shrink(
            outcome.violation, outcome.trace)
        violation, trace = (shrunk.violation, shrunk.trace) if shrunk.reproduced else (
            outcome.violation, outcome.trace)
        if not shrunk.reproduced:
            await self._log("warn", "The violation did not reproduce while shrinking; keeping the original "
                                    "sequence (it may be a race)")
        await self._phase("REPLAY")
        replay = await Replayer(model, self._executor(model), self.bus, self.run_id, seed=seed).replay(
            violation, trace)
        await self._phase("SAVE")
        ws = self._ws()
        cx = Counterexample.build(next_cx_id(ws), model, violation, trace, replay, seed)
        path = await asyncio.to_thread(save_counterexample, ws, cx)
        self._cx_ids.append(cx.cx_id)
        self._store_cx(cx, "open")
        await publish_saved(self.bus, self.run_id, cx, None)
        await self._log("info", f"Saved {path.relative_to(ws).as_posix()} (reproduced {cx.reproduced})")
        return cx

    def _store_cx(self, cx: Counterexample, status: CxStatus) -> None:
        if self.store is not None:
            self.store.save_counterexample(f"{self.run_id}_{cx.cx_id}", self.run_id, cx.rule.id,
                                           cx.model_dump(mode="json"), status)

    async def _diagnose(self, model: RookModel, known: Understanding, cx: Counterexample,
                        prior: str) -> DiagnosisResult:
        while True:
            async with self._executor(model)() as ex:
                diagnosis = await DiagnosePipeline(self._bob(), self._ws()).run(
                    model, cx, ex, sandbox=known.app.sandbox, summary=known.summary, prior=prior)
            if diagnosis.file:
                return diagnosis
            await self._retry_or_stop("detective", f"No diagnosis for {cx.cx_id}: {diagnosis.explanation}")

    async def _fix_and_ship(self, model: RookModel, known: Understanding, cx: Counterexample) -> str:
        """DIAGNOSE -> APPROVE_FIX -> FIX -> VERIFY, back to DIAGNOSE on a failed verification (at most 3
        verifications, rails), then APPROVE_PR -> SHIP."""
        assert self._harness is not None
        fixer = FixPipeline(self._bob(), self._ws())
        guard = PathGuard(self._ws())
        regression: RegressionTest | None = None
        prior = ""
        while True:
            diagnosis = await self._diagnose(model, known, cx, prior)
            if not await self._approve_fix(cx, diagnosis):
                return (f"Found and saved {cx.cx_id} (rule {cx.rule.id}); the fix was not approved, so the "
                        "app was not changed.")
            await self._phase("FIX")
            if regression is None:
                regression = await fixer.regression_test(model, cx, self._harness, diagnosis,
                                                          language=known.summary.language)
            fixed = await self._apply_fix(fixer, guard, model, cx, diagnosis, regression)
            if fixed is None:
                return f"Found and saved {cx.cx_id}; no fix was approved by the Fix Reviewer."
            self._store_cx(cx, "fixed")
            if self._pristine_demo():
                await self._log("warn", f"The fix for {cx.cx_id} was not verified: {_PRISTINE_NOTE}")
                return (f"Found and saved {cx.cx_id}; a fix was written to the run's workspace but NOT verified: "
                        f"{_PRISTINE_NOTE}")
            verification = await fixer.verify(cx, regression, self._harness, self._verifier(model))
            if verification.verified:
                self._verified = True
                self._store_cx(cx, "verified")
                return await self._ship_fix(cx, fixed, regression, verification)
            note = f"verification of {cx.cx_id} failed: {verification.summary}"
            step = await self._decide("verify_failed", notes=[note])
            if step != "diagnose":
                return (f"Found and saved {cx.cx_id}; the fix was NOT verified ({verification.summary}). "
                        "The last patch is left in the workspace and was not shipped.")
            await self._revert(guard)
            prior = _failed_fix_note(fixed, verification)

    async def _approve_fix(self, cx: Counterexample, diagnosis: DiagnosisResult) -> bool:
        await self._phase("APPROVE_FIX")
        where = f"{diagnosis.file}:{diagnosis.line}" if diagnosis.line else diagnosis.file
        payload = {"cx_id": cx.cx_id, "file": diagnosis.file, "line": diagnosis.line,
                   "explanation": diagnosis.explanation, "reviewed": diagnosis.reviewed}
        answer = await self._ask("fix", f"Fix {cx.cx_id} in {where}?", [("yes", "Fix it"), ("no", "Not now")],
                                 payload, "yes" if diagnosis.reviewed else "no")
        return rails.is_approval(answer)

    async def _apply_fix(self, fixer: FixPipeline, guard: PathGuard, model: RookModel, cx: Counterexample,
                         diagnosis: DiagnosisResult, regression: RegressionTest) -> FixResult | None:
        if self._pre_fix is not None:
            self._pre_fix.close()
        self._pre_fix = await asyncio.to_thread(guard.snapshot)  # the workspace before this fix
        while True:
            fixed = await fixer.fix(self.state, model, cx, diagnosis, regression, announce=False)
            if fixed.applied:
                return fixed
            step = await self._decide("agent_failed", agent="surgeon", notes=[fixed.summary])
            if step != "retry":
                return None
            self.state.record_retry("surgeon")

    async def _revert(self, guard: PathGuard) -> None:
        """Undo the unverified patch and reload the app, so the next diagnosis sees the original code."""
        assert self._pre_fix is not None and self._harness is not None
        reverted = await asyncio.to_thread(guard.restore, self._pre_fix)
        await self._log("info", f"Reverted the unverified patch ({', '.join(reverted) or 'no files'}); "
                                "diagnosing again")
        await self._harness.reload()

    def _verifier(self, model: RookModel) -> Verifier:
        return Verifier(model, self._executor(model), self.bus, self.run_id,
                        seed=f"{self.options.seed}:verify:{self.state.verify_rounds + 1}",
                        budget_sequences=self.options.verify_sequences,
                        budget_seconds=self.options.verify_seconds, concurrency=self.options.concurrency)

    async def _ship_fix(self, cx: Counterexample, fixed: FixResult, regression: RegressionTest,
                        verification: VerifyResult) -> str:
        await self._phase("APPROVE_PR")
        branch_note = "a new branch (never the default branch)"
        answer = await self._ask("pr", f"Ship the verified fix for {cx.cx_id} to {branch_note}?",
                                 [("yes", "Ship it"), ("no", "Not now")],
                                 {"cx_id": cx.cx_id, "files": fixed.files, "diff": fixed.diff}, "yes")
        if not rails.is_approval(answer):
            return f"Fixed and verified {cx.cx_id}; the fix is left in the workspace (not shipped)."
        why = rails.check_step(self.state, "ship")
        if why is not None:
            raise RunStop("failed", f"SHIP refused by the rails: {why}")
        await self._phase("SHIP")
        files = [*fixed.files, regression.path, MODEL_PATH.as_posix(), (CX_DIR / f"{cx.cx_id}.json").as_posix()]
        title = f"Rook: fix {cx.rule.id} ({cx.cx_id})"
        body = (f"Rule: {cx.rule.text}\nCounterexample: {len(cx.steps)} steps, reproduced {cx.reproduced}.\n"
                f"Regression test: {regression.path}\nVerified by Rook: {verification.summary}.")
        shipped = await self.shipper.ship(self._ws(), ShipRequest(cx_id=cx.cx_id, files=files, title=title,
                                                                  body=redact_text(body)))
        self._ship = shipped
        await self._publish("fix.committed", FixCommitted(cx_id=cx.cx_id, branch=shipped.branch,
                                                          commit=shipped.commit, files=shipped.files))
        where = shipped.pr_url or f"local branch {shipped.branch} in the workspace (not pushed)"
        return f"Fixed and verified {cx.cx_id} (rule {cx.rule.id}); committed to {where}."


def _failed_fix_note(fixed: FixResult, verification: VerifyResult) -> str:
    checks = "; ".join(f"{c.check}: {'passed' if c.passed else 'FAILED'} ({c.detail})" for c in verification.checks)
    return redact_text(f"An earlier fix of {', '.join(fixed.files)} was approved but FAILED verification by the "
                       f"engine ({checks}). It has been reverted. The diff was:\n{fixed.diff}")[:6_000]


# --- reading stored runs ---


@dataclass
class RunView:
    record: RunRecord
    events: list[Event]
    state: RunState
    snapshot: dict[str, Any]
    counterexamples: list[Any]


def read_run(store: Store, run_id: str) -> RunView | None:
    """A stored run with its state rebuilt from its events (for listing, reading and SSE resume)."""
    record = store.get_run(run_id)
    if record is None:
        return None
    events = store.events_after(run_id, 0)
    state = RunState()
    snapshot = RunSnapshot()
    for event in events:
        if event.type == "run.created":
            state.auto = bool(event.data["options"]["auto"])
            state.budget = float(event.data["options"]["budget"])
        state.observe(event)
        snapshot.observe(event)
    return RunView(record, events, state, snapshot.to_dict(), store.list_counterexamples(run_id))


def mark_interrupted(store: Store, live: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Mark runs left `running` by a process that died (not in `live`) as failed, with a final event.

    A run's work (sandbox, Bob calls, answer futures) lives in its process, so it cannot be resumed; its
    events and counterexamples stay readable."""
    marked = []
    for record in store.list_runs(limit=10_000):
        if record.status != "running" or record.id in live:
            continue
        data = validate_data("run.finished", RunFinished(status="failed", summary="Interrupted: Rook stopped "
                                                                                  "while the run was going"))
        store.append_event(Event(seq=store.last_seq(record.id) + 1, ts=now_ts(), run_id=record.id,
                                 type="run.finished", data=data))
        store.update_run(record.id, status="failed", finished_at=now_ts())
        marked.append(record.id)
    return marked


__all__ = [
    "BudgetSpent", "BudgetedClient", "RepoSpec", "RunResult", "RunStop", "RunView", "SandboxTracker",
    "Session", "SessionOptions", "mark_interrupted", "process_launcher", "read_run", "valid_answer",
]

