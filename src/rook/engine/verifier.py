"""The Verifier (02_ARCHITECTURE.md section 7.7): decides whether a fix is verified.

A fix is verified only if all four checks pass (each one reported with `verify.step` events):
  1. replay: the exact counterexample now holds its rule N/N times (Replayer, judged on that rule
     only), and one more exact replay shows every step really ran (got an HTTP response, no skipped
     step, no failed state read, no rule error), so the pass is not vacuous;
  2. project_tests: the project's own test command exits 0 (no command known: reported and passed);
  3. regression_test: the regression test exits 0;
  4. fresh_search: a new search with a new seed over `budget_sequences` / `budget_seconds` finds no
     violation of any approved rule (and no rule error), at least one step got a successful (<400)
     response and the Judge evaluated at least one rule (otherwise it "could not exercise the app").
All four always run, so the user sees every result. Only engine results (the Judge's verdicts and
exit codes) decide; `verify.done` carries the outcome.
"""

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from rook.core.events import EngineFinished, EngineStarted, EventBus, VerifyDone, VerifyStep
from rook.engine.executor import Executor, StepResult
from rook.engine.judge import Judge, Violation
from rook.engine.replayer import DEFAULT_REPLAYS, Replayer
from rook.engine.runner import Runner
from rook.engine.testrunner import TestRun
from rook.export.counterexample import Counterexample, replay_counterexample, rule_only_model
from rook.model.schema import RookModel

Check = Literal["replay", "project_tests", "regression_test", "fresh_search"]
TestCheck = Callable[[], Awaitable[TestRun]]


@dataclass(frozen=True)
class CheckResult:
    check: Check
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerifyResult:
    cx_id: str
    checks: list[CheckResult]

    @property
    def verified(self) -> bool:
        return len(self.checks) == 4 and all(c.passed for c in self.checks)

    @property
    def summary(self) -> str:
        passed = sum(c.passed for c in self.checks)
        failed = [c.check for c in self.checks if not c.passed]
        head = f"{passed}/{len(self.checks)} checks passed"
        return head + (f"; failed: {', '.join(failed)}" if failed else "")


class _CountingJudge(Judge):
    """A Judge that also counts the successful (<400) responses it was shown: the Runner shows it
    every step's result, so this tells whether the fresh search reached the app at all."""

    def __init__(self, model: RookModel) -> None:
        super().__init__(model)
        self.ok_responses = 0

    def check_response(self, result: StepResult, step_index: int = 0) -> Violation | None:
        if result.status is not None and result.status < 400:
            self.ok_responses += 1
        return super().check_response(result, step_index)


class Verifier:
    """`executor` is an entered Executor or a factory for one (used by the replay and the search)."""

    def __init__(
        self,
        model: RookModel,
        executor: Executor | Callable[[], Executor],
        bus: EventBus | None,
        run_id: str,
        *,
        replays: int = DEFAULT_REPLAYS,
        seed: int | str | None = None,
        budget_sequences: int = 20_000,
        budget_seconds: float = 120.0,
        concurrency: int = 16,
    ) -> None:
        self.model = model
        self._executor_source = executor
        self.bus = bus
        self.run_id = run_id
        self.replays = replays
        self.seed = seed if seed is not None else secrets.randbelow(2**31)
        self.budget_sequences = budget_sequences
        self.budget_seconds = budget_seconds
        self.concurrency = concurrency

    async def verify(
        self, cx: Counterexample, *, regression_test: TestCheck, project_tests: TestCheck | None = None
    ) -> VerifyResult:
        await self._publish("engine.started", EngineStarted(worker="verifier", label=f"verify {cx.cx_id}"))
        try:
            if isinstance(self._executor_source, Executor):
                result = await self._verify(self._executor_source, cx, regression_test, project_tests)
            else:
                async with self._executor_source() as ex:
                    result = await self._verify(ex, cx, regression_test, project_tests)
        except BaseException as exc:
            summary = f"verification stopped: {type(exc).__name__}: {exc}"
            await self._publish(
                "engine.finished", EngineFinished(worker="verifier", ok=False, summary=summary)
            )
            raise
        await self._publish(
            "verify.done", VerifyDone(cx_id=cx.cx_id, verified=result.verified, summary=result.summary)
        )
        await self._publish(
            "engine.finished", EngineFinished(worker="verifier", ok=result.verified, summary=result.summary)
        )
        return result

    async def _verify(
        self, ex: Executor, cx: Counterexample, regression_test: TestCheck, project_tests: TestCheck | None
    ) -> VerifyResult:
        checks = [
            await self._check(cx, "replay", lambda: self._replay(ex, cx)),
            await self._check(cx, "project_tests", lambda: self._project_tests(project_tests)),
            await self._check(cx, "regression_test", lambda: self._test(regression_test)),
            await self._check(cx, "fresh_search", lambda: self._fresh_search(ex)),
        ]
        return VerifyResult(cx.cx_id, checks)

    async def _check(
        self, cx: Counterexample, check: Check, run: Callable[[], Awaitable[tuple[bool, str]]]
    ) -> CheckResult:
        await self._publish(
            "verify.step", VerifyStep(cx_id=cx.cx_id, check=check, status="running", detail="")
        )
        try:
            passed, detail = await run()
        except Exception as exc:  # noqa: BLE001 - a check that crashes has not passed
            passed, detail = False, f"error: {type(exc).__name__}: {exc}"
        status: Literal["passed", "failed"] = "passed" if passed else "failed"
        await self._publish(
            "verify.step", VerifyStep(cx_id=cx.cx_id, check=check, status=status, detail=detail)
        )
        return CheckResult(check, passed, detail)

    # --- the four checks ---

    async def _replay(self, ex: Executor, cx: Counterexample) -> tuple[bool, str]:
        restricted = rule_only_model(self.model, cx)
        judge = Judge(restricted)
        replayer = Replayer(
            restricted, ex, self.bus, self.run_id, n=self.replays, seed=self.seed, judge=judge
        )
        result = await replayer.replay(cx.rule.id, cx.to_trace(restricted))
        held = result.n - result.k
        if result.k > 0:
            return False, f"rule {cx.rule.id} still broken in {result.k}/{result.n} replays"
        if judge.rule_errors:
            return False, "rule error: " + "; ".join(judge.rule_errors.values())
        probe = await replay_counterexample(ex, self.model, cx)
        if not probe.holds:
            return False, probe.message
        return True, f"rule {cx.rule.id} held in {held}/{result.n} replays"

    async def _project_tests(self, project_tests: TestCheck | None) -> tuple[bool, str]:
        if project_tests is None:
            return True, "skipped: the project has no test command"
        return await self._test(project_tests)

    @staticmethod
    async def _test(test: TestCheck) -> tuple[bool, str]:
        run = await test()
        return run.passed, run.summary

    async def _fresh_search(self, ex: Executor) -> tuple[bool, str]:
        judge = _CountingJudge(self.model)
        runner = Runner(
            self.model,
            ex,
            self.bus,
            self.run_id,
            seed=self.seed,
            budget_sequences=self.budget_sequences,
            budget_seconds=self.budget_seconds,
            concurrency=self.concurrency,
            judge=judge,
        )
        out = await runner.run()
        if out.violation is not None:
            return False, f"new violation of rule {out.violation.rule_id} (seed {self.seed})"
        if out.rule_errors:
            return False, "rule error: " + "; ".join(out.rule_errors.values())
        if judge.ok_responses == 0:
            return False, "fresh search could not exercise the app: no step got a successful (<400) response"
        if judge.checks == 0:
            return False, "fresh search could not exercise the app: no rule was ever evaluated"
        rules = len(judge.rules)
        return True, f"no violation of {rules} rules in {out.sequences_run} sequences (seed {self.seed})"

    async def _publish(self, event_type: str, data: Any) -> None:
        if self.bus is not None:
            await self.bus.publish(self.run_id, event_type, data)
