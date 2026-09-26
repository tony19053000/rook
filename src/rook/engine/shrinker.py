"""The Shrinker (02_ARCHITECTURE.md section 7.4): makes a failing trace as small and simple as possible.

Every candidate is **re-executed for real** from a fresh `SequenceContext` (fresh actors and
entities), and the Judge decides whether it still fails. The shrinker never judges on its own.

"Same violation" means the **same rule_id**. The entity and the step index are not compared: with
fresh entities every id changes on each run, and a shorter candidate breaks the rule at an earlier
step by design.

Units and refs: each trace step is one unit (a parallel group stays one unit). A `ref` is not kept as
a pool index (indexes shift when steps are removed) but as its provenance: which unit captured the
value, and which of that unit's captures of the var it was. When a candidate is run, each ref is
re-pinned to the pool index that its producer's capture got in *this* run.

Repair pass: a unit whose producer is not in the candidate (or captured nothing this time) cannot run
and is skipped. The candidate that is kept is the list of units that actually ran, cut after the step
that broke the rule, so dead steps disappear on their own.

Algorithm (deterministic for a given trace, app and seed):
  1. re-run the original trace to confirm the violation and learn the ref provenance;
  2. ddmin over the units (ends 1-minimal: removing any single unit no longer fails);
  2b. a parallel group whose captures nobody uses is tried as its sub-steps run one after another
     (sequential is simpler; a race that needs real concurrency keeps its group);
  3. value shrinking, repeated to a fixpoint: each param moves to a simpler value that still fails.
     Ints try their range bound nearest 0 and the model's edge values (simplest first), then a
     binary search toward that bound (the smallest still-failing value, assuming monotonic failure);
     choices and fixed string values try the options listed before the current one. Then pairs of
     ints move together (both toward their simplest value by the same amount; or one set to its
     simplest value and the other scaled by the same ratio), since params often constrain each other;
  4. repeat 2-3 until nothing changes.
All of it is bounded by `max_runs` re-executions (identical candidates are cached, not re-run).
"""

import random
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from rook.core.events import EngineFinished, EngineStarted, EventBus, ShrinkStep
from rook.engine.executor import Executor, SequenceContext, StepResult
from rook.engine.judge import Judge, StateSnapshot, Violation
from rook.engine.runner import TraceStep
from rook.model.schema import Choice, IntRange, ParallelStep, RookModel, SequenceStep, Step, StringParam

DEFAULT_MAX_RUNS = 600
_SPLIT_UID = 1_000_000  # unit ids for the sub-steps of a split parallel group (deterministic)
_SPLIT_WIDTH = 1_000

Provenance = Mapping[str, tuple[int, int]]  # var -> (producer unit id, offset among its captures)


@dataclass(frozen=True)
class _Unit:
    uid: int  # index of the step in the original trace
    subs: tuple[Step, ...]
    parallel: bool
    refs: tuple[Provenance, ...] = ()  # one per sub-step (empty only in the first, original run)
    pins: tuple[Mapping[str, int], ...] = ()  # original pool indexes (first run only)

    def step(self) -> SequenceStep:
        subs = [s.model_copy(deep=True) for s in self.subs]
        return ParallelStep(parallel=subs) if self.parallel else subs[0]

    def key(self) -> Hashable:
        return (self.uid, tuple(tuple(sorted((k, repr(v)) for k, v in s.params.items())) for s in self.subs))


@dataclass
class _Outcome:
    violation: Violation
    trace: list[TraceStep]
    units: list[_Unit]  # the units that ran, up to and including the violating one
    produced: dict[int, dict[str, tuple[int, int]]]  # uid -> var -> (pool start, count)


@dataclass
class ShrinkResult:
    reproduced: bool  # False if re-running the original trace did not break the rule again
    violation: Violation  # from the final run (violation_id kept from the original)
    trace: list[TraceStep]  # the shrunk trace, from its own fresh run: replayable with its pinned_refs
    original_steps: int
    runs: int  # real re-executions (cache hits are not counted)
    max_runs: int
    budget_exhausted: bool  # if True the result may not be 1-minimal
    improvements: int = 0

    @property
    def steps_count(self) -> int:
        return len(self.trace)


@dataclass
class _State:
    runs: int = 0
    exhausted: bool = False
    improvements: int = 0
    cache: dict[Hashable, _Outcome | None] = field(default_factory=dict)


class Shrinker:
    """Shrinks one violating trace. `executor` is an entered Executor or a factory for one."""

    def __init__(
        self,
        model: RookModel,
        executor: Executor | Callable[[], Executor],
        bus: EventBus | None,
        run_id: str,
        *,
        seed: int | str = 0,
        max_runs: int = DEFAULT_MAX_RUNS,
        judge: Judge | None = None,
    ) -> None:
        if max_runs < 1:
            raise ValueError("max_runs must be at least 1")
        self.model = model
        self._executor_source = executor
        self.bus = bus
        self.run_id = run_id
        self.seed = seed
        self.max_runs = max_runs
        self.judge = judge or Judge(model)
        self._actions = {a.name: a for a in model.actions}
        self._s = _State()
        self._ex: Executor | None = None

    # --- public ---

    async def shrink(self, violation: Violation, trace: Sequence[TraceStep]) -> ShrinkResult:
        self._s = _State()
        await self._publish(
            "engine.started",
            EngineStarted(worker="shrinker", label=f"{len(trace)} steps, rule {violation.rule_id}"),
        )
        try:
            if isinstance(self._executor_source, Executor):
                self._ex = self._executor_source
                result = await self._shrink(violation, trace)
            else:
                async with self._executor_source() as ex:
                    self._ex = ex
                    result = await self._shrink(violation, trace)
        except BaseException as exc:
            summary = f"shrink stopped: {type(exc).__name__}: {exc}"
            await self._publish(
                "engine.finished", EngineFinished(worker="shrinker", ok=False, summary=summary)
            )
            raise
        finally:
            self._ex = None
        if result.reproduced:
            summary = f"{result.original_steps} -> {result.steps_count} steps in {result.runs} runs"
            if result.budget_exhausted:
                summary += " (run budget used up)"
        else:
            summary = f"the violation did not reproduce on re-execution ({result.runs} runs)"
        await self._publish(
            "engine.finished", EngineFinished(worker="shrinker", ok=result.reproduced, summary=summary)
        )
        return result

    # --- the algorithm ---

    async def _shrink(self, violation: Violation, trace: Sequence[TraceStep]) -> ShrinkResult:
        rule_id = violation.rule_id
        original = _trace_units(trace)
        first = await self._execute(original, rule_id)
        if first is None:
            return ShrinkResult(
                False, violation, list(trace), len(trace), self._s.runs, self.max_runs, self._s.exhausted
            )
        best = _with_provenance(first)
        # Re-run with provenance-based pins so `best` holds a run of exactly these units.
        best = await self._try(best.units, rule_id) or best

        while not self._s.exhausted:
            best = await self._ddmin(best, rule_id, violation.violation_id)
            split = await self._split_parallel(best, rule_id, violation.violation_id)
            if split is not best:
                best = split
                continue
            shrunk = await self._shrink_values(best, rule_id, violation.violation_id)
            if shrunk is best:
                break
            best = shrunk

        final = replace(best.violation, violation_id=violation.violation_id)
        return ShrinkResult(
            True,
            final,
            best.trace,
            len(trace),
            self._s.runs,
            self.max_runs,
            self._s.exhausted,
            self._s.improvements,
        )

    async def _improved(self, outcome: _Outcome, violation_id: str) -> None:
        self._s.improvements += 1
        await self._publish(
            "shrink.step", ShrinkStep(violation_id=violation_id, steps_count=len(outcome.units))
        )

    async def _ddmin(self, best: _Outcome, rule_id: str, violation_id: str) -> _Outcome:
        n = 2
        while len(best.units) >= 2 and not self._s.exhausted:
            units = best.units
            chunks = _split(units, n)
            found: _Outcome | None = None
            for chunk in chunks:  # a single chunk that still fails
                found = await self._try(chunk, rule_id)
                if found is not None or self._s.exhausted:
                    break
            if found is not None:
                n = 2
            elif n > 2 and not self._s.exhausted:  # (with 2 chunks the complements are the chunks)
                for i in range(len(chunks)):
                    complement = [u for j, c in enumerate(chunks) if j != i for u in c]
                    found = await self._try(complement, rule_id)
                    if found is not None or self._s.exhausted:
                        break
                if found is not None:
                    n = max(n - 1, 2)
            if found is not None:
                best = found
                await self._improved(best, violation_id)
                continue
            if n >= len(units):
                break  # every single-unit removal was tried: 1-minimal
            n = min(len(units), 2 * n)
        return best

    async def _split_parallel(self, best: _Outcome, rule_id: str, violation_id: str) -> _Outcome:
        """Try running each parallel group's sub-steps one after another instead (sequential is
        simpler and deterministic). Only for groups whose captures no other unit uses."""
        ui = 0
        while ui < len(best.units) and not self._s.exhausted:
            unit = best.units[ui]
            used = any(producer == unit.uid for u in best.units for r in u.refs for producer, _ in r.values())
            if unit.parallel and not used:
                subs = [
                    _Unit(
                        uid=_SPLIT_UID + unit.uid * _SPLIT_WIDTH + k, subs=(sub,), parallel=False, refs=(ref,)
                    )
                    for k, (sub, ref) in enumerate(zip(unit.subs, unit.refs, strict=True))
                ]
                found = await self._try([*best.units[:ui], *subs, *best.units[ui + 1 :]], rule_id)
                if found is not None:
                    best = found
                    await self._improved(best, violation_id)
                    ui = 0
                    continue
            ui += 1
        return best

    async def _shrink_values(self, best: _Outcome, rule_id: str, violation_id: str) -> _Outcome:
        """Returns `best` itself if no value changed, else the new best outcome."""
        changed = True
        while changed and not self._s.exhausted:
            changed = False
            i = 0
            while i < len(positions := self._positions(best)):  # re-read: a change can drop units
                found = await self._shrink_param(best, *positions[i], rule_id)
                if found is not None:
                    best, changed = found, True
                    await self._improved(best, violation_id)
                if self._s.exhausted:
                    return best
                i += 1
            # Params that constrain each other (e.g. price and a refund amount) only move together.
            a = 0
            while a < len(ints := self._int_positions(best)):
                b = a + 1
                while b < len(ints := self._int_positions(best)) and a < len(ints):
                    for move in (self._shrink_pair, self._scale_pair):
                        found = await move(best, ints[a], ints[b], rule_id)
                        if found is not None:
                            best, changed = found, True
                            await self._improved(best, violation_id)
                            break
                        if self._s.exhausted:
                            return best
                    b += 1
                a += 1
        return best

    async def _scale_pair(
        self, best: _Outcome, first: tuple[int, int, str], second: tuple[int, int, str], rule_id: str
    ) -> _Outcome | None:
        """Set one int param to its simplest value and scale the other by the same ratio (either way
        round), for params that multiply (e.g. quantity 2 -> 1 halves what a refund may be)."""
        for (ui, si, name), (uj, sj, other) in ((first, second), (second, first)):
            target = self._int_target(best, ui, si, name)
            value: int = best.units[ui].subs[si].params[name]
            if not target or value == target:
                continue  # a ratio to 0 would zero the other param too
            spec = self._actions[best.units[uj].subs[sj].action].params[other]
            assert isinstance(spec, IntRange)
            lo, hi = spec.int_range
            partner: int = best.units[uj].subs[sj].params[other]
            scaled = min(max(round(partner * target / value), lo), hi)
            if scaled == partner:
                continue
            units = _set_param(_set_param(best.units, ui, si, name, target), uj, sj, other, scaled)
            found = await self._try(units, rule_id)
            if found is not None or self._s.exhausted:
                return found
        return None

    def _positions(self, best: _Outcome) -> list[tuple[int, int, str]]:
        return [
            (ui, si, name)
            for ui, unit in enumerate(best.units)
            for si, sub in enumerate(unit.subs)
            for name in sub.params
        ]

    def _int_target(self, best: _Outcome, ui: int, si: int, name: str) -> int | None:
        """The simplest value of an int param (its bound nearest 0), or None if not an int param."""
        sub = best.units[ui].subs[si]
        spec = self._actions[sub.action].params.get(name)
        value = sub.params[name]
        if not isinstance(spec, IntRange) or not isinstance(value, int) or isinstance(value, bool):
            return None
        lo, hi = spec.int_range
        return min(max(0, lo), hi)

    def _int_positions(self, best: _Outcome) -> list[tuple[int, int, str]]:
        """Int params not yet at their simplest value."""
        out = []
        for ui, si, name in self._positions(best):
            target = self._int_target(best, ui, si, name)
            if target is not None and best.units[ui].subs[si].params[name] != target:
                out.append((ui, si, name))
        return out

    async def _shrink_pair(
        self, best: _Outcome, first: tuple[int, int, str], second: tuple[int, int, str], rule_id: str
    ) -> _Outcome | None:
        """Move two int params toward their targets by the same amount: the largest still-failing
        amount (tries the full distance first, then a binary search)."""
        moves = []
        for ui, si, name in (first, second):
            target = self._int_target(best, ui, si, name)
            assert target is not None
            value: int = best.units[ui].subs[si].params[name]
            moves.append((ui, si, name, value, 1 if target > value else -1, abs(target - value)))
        limit = min(m[5] for m in moves)

        async def attempt(delta: int) -> _Outcome | None:
            units = best.units
            for ui, si, name, value, sign, _ in moves:
                units = _set_param(units, ui, si, name, value + sign * delta)
            return await self._try(units, rule_id)

        found = await attempt(limit)
        if found is not None or self._s.exhausted:
            return found
        good, bad = 0, limit  # 0 is the current (failing) values
        result: _Outcome | None = None
        while bad - good > 1 and not self._s.exhausted:
            mid = (good + bad) // 2
            found = await attempt(mid)
            if found is not None:
                good, result = mid, found
            else:
                bad = mid
        return result

    async def _shrink_param(
        self, best: _Outcome, ui: int, si: int, name: str, rule_id: str
    ) -> _Outcome | None:
        sub = best.units[ui].subs[si]
        spec = self._actions[sub.action].params.get(name)
        current = sub.params[name]

        async def attempt(value: Any) -> _Outcome | None:
            return await self._try(_set_param(best.units, ui, si, name, value), rule_id)

        if isinstance(spec, IntRange) and isinstance(current, int) and not isinstance(current, bool):
            lo, hi = spec.int_range
            target = min(max(0, lo), hi)
            simpler = sorted({target, *spec.edges} - {current}, key=_simplicity)
            for value in simpler:
                if _simplicity(value) >= _simplicity(current):
                    break
                found = await attempt(value)
                if found is not None or self._s.exhausted:
                    return found
            # Binary search between the (non-failing) target and the failing current value.
            good, bad = target, current
            result: _Outcome | None = None
            while abs(bad - good) > 1 and not self._s.exhausted:
                mid = (good + bad) // 2
                found = await attempt(mid)
                if found is not None:
                    bad, result = mid, found
                else:
                    good = mid
            return result
        options: list[Any] | None = None
        if isinstance(spec, Choice):
            options = spec.choice
        elif isinstance(spec, StringParam) and spec.string.values is not None:
            options = list(spec.string.values)
        if options is not None and current in options:
            for value in options[: options.index(current)]:
                found = await attempt(value)
                if found is not None or self._s.exhausted:
                    return found
        return None

    # --- running candidates ---

    async def _try(self, units: list[_Unit], rule_id: str) -> _Outcome | None:
        """Run a candidate (cached). Returns its outcome if it still breaks `rule_id`."""
        key = tuple(u.key() for u in units)
        if key in self._s.cache:
            return self._s.cache[key]
        if self._s.runs >= self.max_runs:
            self._s.exhausted = True
            return None
        outcome = await self._execute(units, rule_id)
        self._s.cache[key] = outcome
        return outcome

    async def _execute(self, units: list[_Unit], rule_id: str) -> _Outcome | None:
        """One real re-execution from a fresh context; the Judge checks after every step."""
        assert self._ex is not None
        self._s.runs += 1
        outcome = await _run_units(self._ex, self.judge, units, self.seed)
        if outcome.violation is None or outcome.violation.rule_id != rule_id:
            return None  # held, or another rule broke first: not the same violation
        return _Outcome(outcome.violation, outcome.trace, outcome.units, outcome.produced)

    async def _publish(self, event_type: str, data: Any) -> None:
        if self.bus is not None:
            await self.bus.publish(self.run_id, event_type, data)


# --- re-execution (shared with the Replayer) ---


@dataclass
class _Run:
    violation: Violation | None  # the first violation of any rule, or None if every rule held
    trace: list[TraceStep]
    units: list[_Unit]  # the units that ran, up to and including the violating one
    produced: dict[int, dict[str, tuple[int, int]]]


async def replay_trace(
    ex: Executor, judge: Judge, trace: Sequence[TraceStep], *, seed: int | str = 0
) -> tuple[Violation | None, list[TraceStep]]:
    """Re-execute a recorded trace exactly (concrete params, pinned refs) from a fresh context.

    The Judge checks after every step; returns the first violation of any rule (or None) and the new
    trace, which stops at the violating step.
    """
    run = await _run_units(ex, judge, _trace_units(trace), seed)
    return run.violation, run.trace


def _trace_units(trace: Sequence[TraceStep]) -> list[_Unit]:
    return [
        _Unit(
            uid=i,
            subs=tuple(t.step.parallel if isinstance(t.step, ParallelStep) else [t.step]),
            parallel=isinstance(t.step, ParallelStep),
            pins=tuple(t.pinned_refs),
        )
        for i, t in enumerate(trace)
    ]


async def _run_units(ex: Executor, judge: Judge, units: Sequence[_Unit], seed: int | str) -> _Run:
    ctx = ex.new_context()
    rng = random.Random(f"{seed}:shrink")  # only used if a param or ref was left unpinned
    produced: dict[int, dict[str, tuple[int, int]]] = {}
    trace: list[TraceStep] = []
    ran: list[_Unit] = []
    for unit in units:
        pins = _resolve(unit, produced)
        if pins is None:
            continue  # repair: a ref's producer is gone or captured nothing
        before = {var: len(values) for var, values in ctx.pool.items()}
        step = unit.step()
        outcome = await ex.run_step(ctx, step, rng, pins if unit.parallel else pins[0])
        results = outcome if isinstance(outcome, list) else [outcome]
        produced[unit.uid] = {
            var: (before.get(var, 0), len(values) - before.get(var, 0))
            for var, values in ctx.pool.items()
            if len(values) > before.get(var, 0)
        }
        index = len(trace)
        trace.append(TraceStep(step, results))
        ran.append(unit)
        violation = await _judge_step(ex, judge, ctx, results, index)
        if violation is not None:
            return _Run(violation, trace, ran, produced)
    return _Run(None, trace, ran, produced)


async def _judge_step(
    ex: Executor, judge: Judge, ctx: SequenceContext, results: list[StepResult], index: int
) -> Violation | None:
    for result in results:
        violation = judge.check_response(result, index)
        if violation is not None:
            return violation
    # The context is fresh, so every pooled entity belongs to this run: read them all.
    if judge.needs_full_state:
        state: StateSnapshot = await ex.read_state(ctx)
    else:
        snapshot: dict[str, dict[Any, dict[str, Any]]] = {}
        for reader in sorted(judge.state_scopes):
            snapshot.update(await ex.read_state(ctx, reader))
        state = snapshot
    return judge.check_state(state, index)


# --- helpers ---


def _simplicity(value: int) -> tuple[int, int]:
    """Smaller is simpler: closer to 0, then negative before positive."""
    return (abs(value), value)


def _split(units: list[_Unit], n: int) -> list[list[_Unit]]:
    size, extra = divmod(len(units), n)
    chunks: list[list[_Unit]] = []
    start = 0
    for i in range(n):
        end = start + size + (1 if i < extra else 0)
        if end > start:
            chunks.append(units[start:end])
        start = end
    return chunks


def _resolve(
    unit: _Unit, produced: Mapping[int, Mapping[str, tuple[int, int]]]
) -> list[dict[str, int]] | None:
    """Pool indexes for each sub-step's refs in this run, or None if one cannot be met."""
    if not unit.refs:
        return [dict(p) for p in unit.pins] if unit.pins else [{} for _ in unit.subs]
    pins: list[dict[str, int]] = []
    for refs in unit.refs:
        pin: dict[str, int] = {}
        for var, (producer, offset) in refs.items():
            span = produced.get(producer, {}).get(var)
            if span is None or offset >= span[1]:
                return None
            pin[var] = span[0] + offset
        pins.append(pin)
    return pins


def _with_provenance(first: _Outcome) -> _Outcome:
    """Turn the first run's pool indexes into (producer, offset) refs."""
    spans = [
        (uid, var, start, count)
        for uid, by_var in first.produced.items()
        for var, (start, count) in by_var.items()
    ]
    units: list[_Unit] = []
    for unit in first.units:
        refs: list[dict[str, tuple[int, int]]] = []
        for pin in unit.pins or tuple({} for _ in unit.subs):
            ref: dict[str, tuple[int, int]] = {}
            for var, index in pin.items():
                for uid, v, start, count in spans:
                    if v == var and start <= index < start + count:
                        ref[var] = (uid, index - start)
                        break
                else:
                    ref[var] = (-1, 0)  # never produced: the unit will be dropped by repair
            refs.append(ref)
        units.append(replace(unit, refs=tuple(refs), pins=()))
    return replace(first, units=units)


def _set_param(units: list[_Unit], ui: int, si: int, name: str, value: Any) -> list[_Unit]:
    unit = units[ui]
    subs = list(unit.subs)
    subs[si] = subs[si].model_copy(update={"params": {**subs[si].params, name: value}})
    return [*units[:ui], replace(unit, subs=tuple(subs)), *units[ui + 1 :]]
