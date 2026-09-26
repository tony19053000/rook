"""The search runner (02_ARCHITECTURE.md section 7.1): runs generated sequences until a rule breaks.

Each sequence gets a fresh `SequenceContext` (fresh actors and var pool) and its own rng seeded from
`(seed, i)`. After every step the Judge checks response rules, then the state of the entities the step
touched (ids it referenced or captured) is read and state rules are checked. The first violation
stops the whole run; the other workers are cancelled and awaited, so no task outlives `run()`.
With `concurrency=1` the outcome is fully reproducible for a seed; with more workers the sequence
list is still the same, but which violating sequence finishes first can vary.

Designed scenarios (the generator's first sequences) are dispatched before any random one. Each is
announced with a `log` event when it starts, one more `log` marks the switch to random sequences, and
if a violation is found the last `log` says which kind of sequence found it.

The failing sequence's trace records every executed step with its concrete params and the pooled-ref
indexes it used, which is enough to replay it exactly (`run_step(..., pinned_refs=entry.pinned_refs)`).
"""

import asyncio
import random
import time
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, field
from typing import Any

from rook.core.events import EngineFinished, EngineProgress, EngineStarted, EventBus, Log, SearchProgress
from rook.engine.executor import Executor, SequenceContext, StepResult
from rook.engine.generator import Generator
from rook.engine.judge import Judge, StateSnapshot, Violation
from rook.model.schema import ParallelStep, RookModel, SequenceStep, Step

PROGRESS_INTERVAL = 0.2  # seconds: at most 5 progress events of each type per second


@dataclass
class TraceStep:
    """One executed step: the concrete step (params filled in) and its result(s)."""

    step: SequenceStep
    results: list[StepResult]

    @property
    def pinned_refs(self) -> list[dict[str, int]]:
        """The pool index of every `ref` each sub-step used, for `run_step(pinned_refs=...)`."""
        return [dict(r.refs_index) for r in self.results]


@dataclass
class RunOutcome:
    violation: Violation | None
    sequences_run: int
    elapsed: float
    trace: list[TraceStep] | None = None  # the failing sequence, when there is a violation
    sequence_index: int | None = None
    rule_errors: dict[str, str] = field(default_factory=dict)

    @property
    def per_sec(self) -> float:
        return self.sequences_run / self.elapsed if self.elapsed > 0 else 0.0


@dataclass
class _Found:
    violation: Violation
    trace: list[TraceStep]
    sequence_index: int


class Runner:
    """Runs the search. `executor` is an already-entered Executor (shared by all workers) or a
    factory returning a new one, which the runner enters and closes itself."""

    def __init__(
        self,
        model: RookModel,
        executor: Executor | Callable[[], Executor],
        bus: EventBus | None,
        run_id: str,
        *,
        seed: int | str,
        budget_sequences: int = 20_000,
        budget_seconds: float = 120.0,
        concurrency: int = 16,
        generator: Generator | None = None,
        judge: Judge | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self.model = model
        self._executor_source = executor
        self.bus = bus
        self.run_id = run_id
        self.seed = seed
        self.budget_sequences = budget_sequences
        self.budget_seconds = budget_seconds
        self.concurrency = concurrency
        self.generator = generator or Generator(model, seed)
        self.judge = judge or Judge(model)
        self._actions = {a.name: a for a in model.actions}
        self._readers_by_var: dict[str, list[str]] = {}
        for reader in model.state:
            if reader.name in self.judge.state_scopes:
                self._readers_by_var.setdefault(reader.each, []).append(reader.name)
        self._reset()

    def _reset(self) -> None:
        self._next = 0
        self._done = 0
        self._found: _Found | None = None
        self._start = 0.0
        self._last_emit = float("-inf")
        self._ticks = 0

    # --- public ---

    async def run(self) -> RunOutcome:
        self._reset()
        self._start = time.monotonic()
        rules = len(self.judge.rules)
        designed = len(self.generator.scenarios)
        label = f"seed {self.seed}" + (f", {designed} designed scenarios first" if designed else "")
        await self._publish("engine.started", EngineStarted(worker="runner", label=label))
        await self._publish("engine.started", EngineStarted(worker="judge", label=f"{rules} approved rules"))
        try:
            if isinstance(self._executor_source, Executor):
                await self._search(self._executor_source)
            else:
                async with self._executor_source() as executor:
                    await self._search(executor)
        except BaseException as exc:
            summary = f"search stopped: {type(exc).__name__}: {exc}"
            await self._publish("engine.finished", EngineFinished(worker="runner", ok=False, summary=summary))
            await self._publish("engine.finished", EngineFinished(worker="judge", ok=False, summary=summary))
            raise
        return await self._finish()

    # --- search loop ---

    async def _search(self, executor: Executor) -> None:
        workers = [asyncio.create_task(self._worker(executor)) for _ in range(self.concurrency)]
        pending: set[asyncio.Task[None]] = set(workers)
        try:
            while pending and self._found is None:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    if not task.cancelled() and task.exception() is not None:
                        raise task.exception()  # type: ignore[misc]
        finally:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    def _budget_left(self) -> bool:
        return (
            self._found is None
            and self._next < self.budget_sequences
            and time.monotonic() - self._start < self.budget_seconds
        )

    async def _worker(self, executor: Executor) -> None:
        while self._budget_left():
            i = self._next
            self._next += 1
            await self._announce(i)
            found = await self._run_sequence(executor, i)
            self._done += 1
            if found is not None and self._found is None:
                self._found = found
                return  # the supervisor cancels the other workers
            await self._report_rule_errors()
            await self._maybe_progress()

    async def _run_sequence(self, executor: Executor, i: int) -> _Found | None:
        steps = self.generator.sequence(i)
        ctx = executor.new_context()
        rng = random.Random(f"{self.seed}:{i}:exec")
        trace: list[TraceStep] = []
        for step in steps:
            subs = step.parallel if isinstance(step, ParallelStep) else [step]
            required = {v for s in subs for v in self._actions[s.action].requires}
            if any(not ctx.pool.get(v) for v in required):
                continue  # an earlier step failed to capture what this one needs
            before = {var: len(values) for var, values in ctx.pool.items()}
            pins: dict[str, int] | None = None
            if isinstance(step, ParallelStep):
                # Every sub-step of a parallel step works on the same entity.
                pins = {v: rng.randrange(len(ctx.pool[v])) for v in sorted(required)}
            outcome = await executor.run_step(ctx, step, rng, pins)
            results = outcome if isinstance(outcome, list) else [outcome]
            index = len(trace)
            trace.append(TraceStep(_concrete(step, results), results))
            for result in results:
                violation = self.judge.check_response(result, index)
                if violation is not None:
                    return _Found(violation, trace, i)
            violation = await self._check_state(executor, ctx, before, results, index)
            if violation is not None:
                return _Found(violation, trace, i)
        return None

    async def _check_state(
        self,
        executor: Executor,
        ctx: SequenceContext,
        before: Mapping[str, int],
        results: list[StepResult],
        index: int,
    ) -> Violation | None:
        touched: dict[str, list[Any]] = {}
        for var, readers in self._readers_by_var.items():
            ids = [r.refs_used[var] for r in results if var in r.refs_used]
            ids += ctx.pool.get(var, [])[before.get(var, 0) :]
            ids = [v for v in dict.fromkeys(v for v in ids if isinstance(v, Hashable))]
            if ids:
                for reader in readers:
                    touched[reader] = ids
        if self.judge.needs_full_state:
            state: StateSnapshot = await executor.read_state(ctx)
        elif touched:
            snapshot: dict[str, dict[Any, dict[str, Any]]] = {}
            for reader, ids in touched.items():
                snapshot.update(await executor.read_state(ctx, reader, only_ids=ids))
            state = snapshot
        else:
            return None
        return self.judge.check_state(state, index, touched)

    # --- events ---

    async def _publish(self, event_type: str, data: Any) -> None:
        if self.bus is not None:
            await self.bus.publish(self.run_id, event_type, data)

    async def _announce(self, i: int) -> None:
        """Make the designed-scenarios-first order visible in the event stream."""
        labels = self.generator.scenario_labels
        if i < len(labels):
            await self._publish("log", Log(level="info", text=f"Designed scenario {i + 1}/{len(labels)}: "
                                                               f"{labels[i]}"))
        elif i == len(labels) and labels:
            await self._publish("log", Log(level="info", text=f"All {len(labels)} designed scenarios started; "
                                                               "random sequences follow"))

    def _found_by(self, i: int) -> str:
        labels = self.generator.scenario_labels
        if i < len(labels):
            return f"Found by designed scenario {i + 1}/{len(labels)}: {labels[i]}"
        return f"Found by generated sequence {i + 1} (after the {len(labels)} designed scenarios)"

    async def _report_rule_errors(self) -> None:
        for _, message in self.judge.pop_new_errors():
            await self._publish("log", Log(level="warn", text=f"rule error (not a violation): {message}"))

    def _rules_status(self) -> dict[str, Any]:
        broken = self._found.violation.rule_id if self._found else None
        return {r.id: "broken" if r.id == broken else "holding" for r in self.judge.rules}

    def _pct(self) -> float:
        by_count = self._done / self.budget_sequences if self.budget_sequences > 0 else 1.0
        by_time = (time.monotonic() - self._start) / self.budget_seconds if self.budget_seconds > 0 else 1.0
        return round(min(100.0, 100.0 * max(by_count, by_time)), 1)

    async def _maybe_progress(self, force: bool = False) -> None:
        if self.bus is None:
            return
        now = time.monotonic()
        if not force and now - self._last_emit < PROGRESS_INTERVAL:
            return
        if force and now - self._last_emit < PROGRESS_INTERVAL:
            await asyncio.sleep(PROGRESS_INTERVAL - (now - self._last_emit))
        self._last_emit = time.monotonic()
        elapsed = self._last_emit - self._start
        per_sec = round(self._done / elapsed, 1) if elapsed > 0 else 0.0
        await self._publish(
            "search.progress",
            SearchProgress(sequences=self._done, per_sec=per_sec, rules=self._rules_status()),
        )
        # engine.progress alternates between the two workers, so it too stays within 5/s.
        if self._ticks % 2 == 0:
            progress = EngineProgress(
                worker="runner", pct=self._pct(), label=f"{self._done} sequences", count=self._done
            )
        else:
            progress = EngineProgress(
                worker="judge", pct=self._pct(), label=f"{self.judge.checks} checks", count=self.judge.checks
            )
        self._ticks += 1
        await self._publish("engine.progress", progress)

    async def _finish(self) -> RunOutcome:
        elapsed = time.monotonic() - self._start
        await self._report_rule_errors()
        await self._maybe_progress(force=True)
        found = self._found
        rate = f"{self._done} sequences in {elapsed:.1f}s ({self._done / max(elapsed, 1e-9):.0f}/s)"
        if found is not None:
            if self.generator.scenario_labels:
                await self._publish("log", Log(level="info", text=self._found_by(found.sequence_index)))
            if self.bus is not None:
                await self.judge.publish_violation(self.bus, self.run_id, found.violation, len(found.trace))
            judge_summary = f"rule {found.violation.rule_id} broken at step {found.violation.step_index + 1}"
        else:
            judge_summary = f"no violation of {len(self.judge.rules)} rules"
        await self._publish("engine.finished", EngineFinished(worker="runner", ok=True, summary=rate))
        await self._publish(
            "engine.finished", EngineFinished(worker="judge", ok=found is None, summary=judge_summary)
        )
        return RunOutcome(
            violation=found.violation if found else None,
            sequences_run=self._done,
            elapsed=elapsed,
            trace=found.trace if found else None,
            sequence_index=found.sequence_index if found else None,
            rule_errors=dict(self.judge.rule_errors),
        )


def _concrete(step: SequenceStep, results: list[StepResult]) -> SequenceStep:
    """The step as it ran: actor and every param fixed, for exact replay."""
    subs = [Step(action=r.action, actor=r.actor, params=dict(r.params)) for r in results]
    return ParallelStep(parallel=subs) if isinstance(step, ParallelStep) else subs[0]
