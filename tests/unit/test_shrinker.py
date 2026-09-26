"""ROOK-009: the Shrinker, with real re-execution in-process against minishop.

The checks here replay traces with the Executor and the Judge directly (not through the shrinker), so
"still fails" and "no longer fails" are decided independently of the code under test.
"""

import importlib.util
import random
from pathlib import Path
from typing import Any

import pytest

from rook.core.events import Event, EventBus
from rook.engine.executor import Executor
from rook.engine.generator import Generator
from rook.engine.inprocess import InProcessTransport
from rook.engine.judge import Judge, Violation
from rook.engine.runner import Runner, TraceStep
from rook.engine.shrinker import Shrinker, ShrinkResult
from rook.model.loader import load_model
from rook.model.schema import IntRange, ParallelStep, RookModel, SequenceStep, Step

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
BASE = "http://minishop.test"
ENV = {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}  # the fixture's built-in default, not a secret

_spec = importlib.util.spec_from_file_location("minishop_app_shrinker", FIXTURE_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)

MODEL = load_model(FIXTURE_DIR / "rook.yaml")
REFUND_SHAPE = ["create_product", "buy", "refund", "refund"]  # buy, refund, refund + the product setup


def only_rules(*rule_ids: str) -> RookModel:
    rules = [
        r.model_copy(update={"status": "approved" if r.id in rule_ids else "rejected"}) for r in MODEL.rules
    ]
    return MODEL.model_copy(update={"rules": rules})


REFUND = only_rules("refund_le_paid")


def executor(model: RookModel = REFUND, *, fixed: bool = False) -> Executor:
    return Executor(model, BASE, transport=InProcessTransport(minishop.create_app(fixed=fixed)), env=ENV)


def subs(step: SequenceStep) -> list[Step]:
    return step.parallel if isinstance(step, ParallelStep) else [step]


def shape(trace: list[TraceStep]) -> list[Any]:
    return [
        [s.action for s in t.step.parallel] if isinstance(t.step, ParallelStep) else t.step.action
        for t in trace
    ]


async def replay(
    model: RookModel, steps: list[SequenceStep], pins: list[list[dict[str, int]]], *, fixed: bool = False
) -> tuple[Violation | None, list[TraceStep]]:
    """Run steps with pinned refs on a fresh context; the Judge checks after every step."""
    judge = Judge(model)
    trace: list[TraceStep] = []
    async with executor(model, fixed=fixed) as ex:
        ctx = ex.new_context()
        rng = random.Random(0)
        for index, (step, pin) in enumerate(zip(steps, pins, strict=True)):
            out = await ex.run_step(ctx, step, rng, pin if isinstance(step, ParallelStep) else pin[0])
            results = out if isinstance(out, list) else [out]
            trace.append(TraceStep(step, results))
            for result in results:
                found = judge.check_response(result, index)
                if found is not None:
                    return found, trace
            found = judge.check_state(await ex.read_state(ctx), index)
            if found is not None:
                return found, trace
    return None, trace


async def shrink(
    model: RookModel, violation: Violation, trace: list[TraceStep], *, bus: EventBus | None = None, **kw: Any
) -> ShrinkResult:
    async with executor(model) as ex:
        return await Shrinker(model, ex, bus, "r_test", **kw).shrink(violation, trace)


async def search_and_shrink(seed: int) -> tuple[list[TraceStep], ShrinkResult]:
    async with executor() as ex:
        out = await Runner(REFUND, ex, None, "r", seed=seed, concurrency=1, budget_seconds=300).run()
    assert out.violation is not None and out.trace is not None
    return out.trace, await shrink(REFUND, out.violation, out.trace, seed=seed)


def fails(v: Violation | None, rule_id: str = "refund_le_paid") -> bool:
    return v is not None and v.rule_id == rule_id


def _int_target(spec: IntRange) -> int:
    lo, hi = spec.int_range
    return min(max(0, lo), hi)


# --- acceptance: the refund violation shrinks to buy, refund, refund (+ setup), 1-minimal ---


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_refund_violation_shrinks_to_three_steps_plus_setup(seed: int) -> None:
    original, result = await search_and_shrink(seed)
    assert result.reproduced and not result.budget_exhausted
    assert result.violation.rule_id == "refund_le_paid"
    assert shape(result.trace) == REFUND_SHAPE
    assert result.steps_count == 4 <= result.original_steps == len(original)
    assert 0 < result.runs <= result.max_runs
    observed = result.violation.observed
    assert observed["refunded"] > observed["paid"]

    # The shrunk trace replays on its own to the same rule.
    steps = [t.step for t in result.trace]
    pins = [t.pinned_refs for t in result.trace]
    found, _ = await replay(REFUND, steps, pins)
    assert fails(found) and found is not None and found.step_index == 3

    # 1-minimal: removing any single step makes the violation disappear. (Each var has exactly one
    # producer here, so the remaining pins still point at the same entities or at nothing.)
    for i in range(len(steps)):
        found, _ = await replay(REFUND, steps[:i] + steps[i + 1 :], pins[:i] + pins[i + 1 :])
        assert not fails(found), f"seed {seed}: still fails without step {i}"


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_values_are_edges_or_locally_smallest(seed: int) -> None:
    _, result = await search_and_shrink(seed)
    steps = [t.step for t in result.trace]
    pins = [t.pinned_refs for t in result.trace]
    for i, step in enumerate(steps):
        assert isinstance(step, Step)
        for name, value in step.params.items():
            spec = REFUND.action(step.action).params[name]
            assert isinstance(spec, IntRange)
            target = _int_target(spec)
            if value == target:
                continue
            # One step closer to the simplest value no longer fails.
            closer = value - 1 if value > target else value + 1
            moved = step.model_copy(update={"params": {**step.params, name: closer}})
            found, _ = await replay(REFUND, [*steps[:i], moved, *steps[i + 1 :]], pins)
            assert not fails(found), f"seed {seed}: {step.action}.{name}={closer} still fails"


async def test_designed_trace_shrinks_to_simplest_values() -> None:
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        Step(action="admin_export", actor="customer", params={}),
        Step(action="buy", actor="customer", params={"quantity": 2}),
        Step(action="ship", actor="customer", params={}),
        Step(action="refund", actor="customer", params={"amount": 150}),
        Step(action="refund", actor="customer", params={"amount": 60}),
    ]
    pins = [[{}], [{}], [{"product_id": 0}], [{"order_id": 0}], [{"order_id": 0}], [{"order_id": 0}]]
    violation, trace = await replay(REFUND, steps, pins)
    assert fails(violation) and violation is not None
    result = await shrink(REFUND, violation, trace)
    assert [(t.step.action, t.step.params) for t in result.trace] == [  # type: ignore[union-attr]
        ("create_product", {"price": 1, "stock": 1}),
        ("buy", {"quantity": 1}),
        ("refund", {"amount": 1}),
        ("refund", {"amount": 1}),
    ]
    assert result.violation.observed == {"paid": 1, "refunded": 2, "status": "paid", "shipped": False}


# --- same violation = same rule ---


async def test_another_rule_breaking_does_not_count() -> None:
    model = only_rules("refund_le_paid", "admin_export_forbidden")
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        Step(action="buy", actor="customer", params={"quantity": 1}),
        Step(action="refund", actor="customer", params={"amount": 60}),
        Step(action="refund", actor="customer", params={"amount": 50}),
        Step(action="admin_export", actor="customer", params={}),
    ]
    pins = [[{}], [{"product_id": 0}], [{"order_id": 0}], [{"order_id": 0}], [{}]]
    violation, trace = await replay(model, steps, pins)
    assert fails(violation) and violation is not None
    result = await shrink(model, violation, trace)
    assert result.violation.rule_id == "refund_le_paid"
    assert shape(result.trace) == REFUND_SHAPE


async def test_response_rule_shrinks_to_one_step() -> None:
    model = only_rules("admin_export_forbidden")
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        Step(action="buy", actor="customer", params={"quantity": 1}),
        Step(action="admin_export", actor="customer", params={}),
    ]
    pins = [[{}], [{"product_id": 0}], [{}]]
    violation, trace = await replay(model, steps, pins)
    assert fails(violation, "admin_export_forbidden") and violation is not None
    result = await shrink(model, violation, trace)
    assert shape(result.trace) == ["admin_export"]
    assert result.violation.rule_id == "admin_export_forbidden"


# --- parallel groups ---


async def test_parallel_group_used_later_stays_one_unit() -> None:
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        ParallelStep(
            parallel=[
                Step(action="buy", actor="customer", params={"quantity": 1}),
                Step(action="buy", actor="customer", params={"quantity": 1}),
            ]
        ),
        Step(action="refund", actor="customer", params={"amount": 60}),
        Step(action="refund", actor="customer", params={"amount": 50}),
    ]
    # The refunds use the order captured by the second buy of the parallel group.
    pins = [[{}], [{"product_id": 0}, {"product_id": 0}], [{"order_id": 1}], [{"order_id": 1}]]
    violation, trace = await replay(REFUND, steps, pins)
    assert fails(violation) and violation is not None
    result = await shrink(REFUND, violation, trace)
    assert result.reproduced
    assert shape(result.trace) == ["create_product", ["buy", "buy"], "refund", "refund"]
    found, _ = await replay(REFUND, [t.step for t in result.trace], [t.pinned_refs for t in result.trace])
    assert fails(found)


async def test_parallel_refunds_become_sequential() -> None:
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        Step(action="buy", actor="customer", params={"quantity": 1}),
        ParallelStep(
            parallel=[
                Step(action="refund", actor="customer", params={"amount": 60}),
                Step(action="refund", actor="customer", params={"amount": 50}),
            ]
        ),
    ]
    pins = [[{}], [{"product_id": 0}], [{"order_id": 0}, {"order_id": 0}]]
    violation, trace = await replay(REFUND, steps, pins)
    assert fails(violation) and violation is not None
    result = await shrink(REFUND, violation, trace)
    assert shape(result.trace) == REFUND_SHAPE
    assert not any(isinstance(t.step, ParallelStep) for t in result.trace)


# --- determinism, budget, events, non-reproducing traces ---


async def test_deterministic_for_a_seed() -> None:
    _, a = await search_and_shrink(2)
    _, b = await search_and_shrink(2)
    assert [t.step.model_dump() for t in a.trace] == [t.step.model_dump() for t in b.trace]
    assert [t.pinned_refs for t in a.trace] == [t.pinned_refs for t in b.trace]
    assert a.runs == b.runs and a.improvements == b.improvements


async def test_run_budget_is_respected_and_reported() -> None:
    async with executor() as ex:
        out = await Runner(REFUND, ex, None, "r", seed=1, concurrency=1).run()
    assert out.violation is not None and out.trace is not None
    result = await shrink(REFUND, out.violation, out.trace, seed=1, max_runs=6)
    assert result.budget_exhausted and result.runs == 6 and result.max_runs == 6
    assert result.reproduced and result.violation.rule_id == "refund_le_paid"
    assert result.steps_count <= len(out.trace)
    found, _ = await replay(REFUND, [t.step for t in result.trace], [t.pinned_refs for t in result.trace])
    assert fails(found)  # even a cut-short shrink returns a trace that still fails


def test_max_runs_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Shrinker(REFUND, executor(), None, "r", max_runs=0)


async def events_of(bus: EventBus) -> list[Event]:
    await bus.close("r_test")
    return [e async for e in bus.subscribe("r_test")]


async def test_shrink_step_events() -> None:
    async with executor() as ex:
        out = await Runner(REFUND, ex, None, "r", seed=3, concurrency=1).run()
    assert out.violation is not None and out.trace is not None
    bus = EventBus()
    result = await shrink(REFUND, out.violation, out.trace, bus=bus, seed=3)
    events = await events_of(bus)
    steps = [e.data for e in events if e.type == "shrink.step"]
    assert len(steps) == result.improvements > 0
    assert all(d["violation_id"] == out.violation.violation_id for d in steps)
    counts = [d["steps_count"] for d in steps]
    # Only splitting a parallel group into its sub-steps can add a step; the rest never grows.
    assert all(c <= len(out.trace) + 1 for c in counts) and counts[-1] == result.steps_count == 4
    assert result.violation.violation_id == out.violation.violation_id
    assert events[0].type == "engine.started" and events[0].data["worker"] == "shrinker"
    assert events[-1].type == "engine.finished" and events[-1].data == {
        "worker": "shrinker",
        "ok": True,
        "summary": f"{len(out.trace)} -> 4 steps in {result.runs} runs",
    }


async def test_trace_that_does_not_reproduce_is_returned_unchanged() -> None:
    steps: list[SequenceStep] = [
        Step(action="create_product", actor="admin", params={"price": 100, "stock": 5}),
        Step(action="buy", actor="customer", params={"quantity": 1}),
        Step(action="refund", actor="customer", params={"amount": 60}),
        Step(action="refund", actor="customer", params={"amount": 50}),
    ]
    pins = [[{}], [{"product_id": 0}], [{"order_id": 0}], [{"order_id": 0}]]
    violation, trace = await replay(REFUND, steps, pins)
    assert violation is not None
    bus = EventBus()
    async with executor(fixed=True) as ex:  # the fixed app: the violation is gone
        result = await Shrinker(REFUND, ex, bus, "r_test").shrink(violation, trace)
    assert not result.reproduced and result.trace == trace and result.runs == 1
    finished = [e.data for e in await events_of(bus) if e.type == "engine.finished"]
    assert finished and finished[-1]["ok"] is False


async def test_executor_factory_is_entered_and_closed() -> None:
    gen = Generator(
        REFUND,
        1,
        scenarios=[
            [
                Step(action="create_product", params={"price": 100, "stock": 5}),
                Step(action="buy", params={"quantity": 1}),
                Step(action="refund", params={"amount": 60}),
                Step(action="refund", params={"amount": 50}),
            ]
        ],
    )
    async with executor() as ex:
        out = await Runner(REFUND, ex, None, "r", seed=1, concurrency=1, generator=gen).run()
    assert out.violation is not None and out.trace is not None
    made: list[Executor] = []

    def factory() -> Executor:
        made.append(executor())
        return made[-1]

    result = await Shrinker(REFUND, factory, None, "r").shrink(out.violation, out.trace)
    assert shape(result.trace) == REFUND_SHAPE
    assert len(made) == 1 and made[0]._client is None
