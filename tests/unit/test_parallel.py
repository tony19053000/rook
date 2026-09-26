"""ROOK-012: parallel steps (`{parallel: [...]}`) and the minishop stock race.

The race needs two buys of the same product in flight at once: minishop's buggy `buy()` checks the
stock, awaits 10 ms, then decrements. Sequential buys can never drive stock below zero, so only a
parallel group can find it.
"""

import asyncio
import random
from collections.abc import Collection, MutableMapping
from typing import Any

import pytest
from test_runner import ENV, MODEL, executor, minishop, only_rule, search

from rook.engine.executor import Executor, SequenceContext
from rook.engine.generator import Generator
from rook.engine.inprocess import InProcessTransport
from rook.engine.judge import Judge, Violation
from rook.engine.runner import Runner, TraceStep
from rook.model.loader import load_model_str
from rook.model.schema import ParallelStep, RookModel, Step

STOCK = only_rule("stock_non_negative")
REFUND = only_rule("refund_le_paid")


async def replay(model: RookModel, trace: list[TraceStep], *, fixed: bool) -> Violation | None:
    """Re-execute a trace step by step on fresh entities, judging after every step (as the Runner does)."""
    judge = Judge(model)
    async with executor(model, fixed=fixed) as ex:
        ctx = ex.new_context()
        rng = random.Random(0)  # unused: params and refs are all pinned
        for index, entry in enumerate(trace):
            outcome = await ex.run_step(ctx, entry.step, rng, entry.pinned_refs)
            for result in outcome if isinstance(outcome, list) else [outcome]:
                found = judge.check_response(result, index)
                if found is not None:
                    return found
            found = judge.check_state(await ex.read_state(ctx), index)
            if found is not None:
                return found
    return None


# --- acceptance: the race is found within budget, the fixed app stays clean ---


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_finds_stock_race_within_budget(seed: int) -> None:
    out = await search(STOCK, fixed=False, seed=seed, budget_sequences=2_000)
    assert out.violation is not None and out.violation.rule_id == "stock_non_negative"
    assert out.violation.observed["stock"] < 0
    assert out.trace is not None and out.violation.step_index == len(out.trace) - 1
    last = out.trace[-1]
    # The breaking step is a parallel group of buys that both succeeded on the same product.
    assert isinstance(last.step, ParallelStep)
    assert [r.action for r in last.results] == ["buy", "buy"]
    assert all(r.status == 200 for r in last.results)
    assert {r.refs_used["product_id"] for r in last.results} == {out.violation.entity}


async def test_race_search_is_deterministic_with_one_worker() -> None:
    a = await search(STOCK, fixed=False, seed=3, concurrency=1, budget_sequences=2_000)
    b = await search(STOCK, fixed=False, seed=3, concurrency=1, budget_sequences=2_000)
    assert a.sequence_index is not None and a.sequence_index == b.sequence_index
    assert a.trace is not None and b.trace is not None
    assert [t.step.model_dump() for t in a.trace] == [t.step.model_dump() for t in b.trace]
    assert [t.pinned_refs for t in a.trace] == [t.pinned_refs for t in b.trace]


async def test_race_is_not_found_without_parallel_steps() -> None:
    gen = Generator(STOCK, 1, parallel_prob=0.0)
    out = await search(STOCK, fixed=False, generator=gen, budget_sequences=500)
    assert out.violation is None


async def test_no_false_violations_on_fixed_minishop_with_parallel_groups() -> None:
    # Every entity-touching step is a parallel group, and every rule is approved.
    gen = Generator(MODEL, 5, parallel_prob=1.0)
    out = await search(MODEL, fixed=True, generator=gen, budget_sequences=400)
    assert out.violation is None and out.sequences_run == 400 and out.rule_errors == {}


async def test_race_trace_replays_k_of_10() -> None:
    out = await search(STOCK, fixed=False, seed=2, budget_sequences=2_000)
    assert out.violation is not None and out.trace is not None
    hits = [await replay(STOCK, out.trace, fixed=False) for _ in range(10)]
    k = sum(v is not None and v.rule_id == "stock_non_negative" for v in hits)
    print(f"\nstock race replay: {k}/10")
    assert 1 <= k <= 10
    assert all(v is None or v.step_index == out.violation.step_index for v in hits)
    # On the fixed app the same trace never breaks the rule.
    assert [await replay(STOCK, out.trace, fixed=True) for _ in range(10)] == [None] * 10


# --- the Runner around a parallel group ---


class CountingExecutor(Executor):
    """Records every state read (reader, ids) and what it returned."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.reads: list[tuple[str | None, list[Any] | None, dict[str, Any]]] = []

    async def read_state(
        self, ctx: SequenceContext, reader_name: str | None = None, only_ids: Collection[Any] | None = None
    ) -> dict[str, dict[Any, dict[str, Any]]]:
        out = await super().read_state(ctx, reader_name, only_ids)
        self.reads.append((reader_name, None if only_ids is None else list(only_ids), out))
        return out


def counting(model: RookModel, *, fixed: bool) -> CountingExecutor:
    return CountingExecutor(
        model, "http://minishop.test", transport=InProcessTransport(minishop.create_app(fixed=fixed)), env=ENV
    )


def buy(quantity: int = 1) -> Step:
    return Step(action="buy", params={"quantity": quantity})


async def test_judge_reads_state_once_after_the_whole_group() -> None:
    scenario = [
        Step(action="create_product", params={"price": 10, "stock": 5}),
        ParallelStep(parallel=[buy(1), buy(1)]),
    ]
    gen = Generator(STOCK, 1, scenarios=[scenario])
    async with counting(STOCK, fixed=True) as ex:
        out = await Runner(
            STOCK, ex, None, "r", seed=1, generator=gen, concurrency=1, budget_sequences=1
        ).run()
    assert out.violation is None
    # One read per executed step: the group is judged once, after both buys finished.
    assert len(ex.reads) == 2
    reader, ids, state = ex.reads[1]
    assert reader == "product" and ids is not None and len(ids) == 1
    assert state["product"][ids[0]]["stock"] == 3


async def test_parallel_refunds_capture_and_pin_one_order() -> None:
    # Two parallel buys capture two orders; the parallel refunds that follow both hit one of them.
    scenario = [
        Step(action="create_product", params={"price": 100, "stock": 5}),
        ParallelStep(parallel=[buy(1), buy(1)]),
        ParallelStep(
            parallel=[
                Step(action="refund", params={"amount": 60}),
                Step(action="refund", params={"amount": 50}),
            ]
        ),
    ]
    gen = Generator(REFUND, 1, scenarios=[scenario])
    out = await search(REFUND, fixed=False, generator=gen, concurrency=1, budget_sequences=1)
    assert out.violation is not None and out.trace is not None
    assert out.violation.step_index == 2 and len(out.trace) == 3
    assert out.violation.observed["refunded"] == 110 and out.violation.observed["paid"] == 100
    buys, refunds = out.trace[1], out.trace[2]
    order_ids = [r.response_json["id"] for r in buys.results]
    assert len(set(order_ids)) == 2  # both captures of the group landed in the pool
    used = {r.refs_used["order_id"] for r in refunds.results}
    assert len(used) == 1 and used <= set(order_ids) and out.violation.entity in used
    assert refunds.pinned_refs[0] == refunds.pinned_refs[1]
    # The same scenario on the fixed app: one refund is refused, no violation.
    clean = await search(
        REFUND, fixed=True, generator=Generator(REFUND, 1, scenarios=[scenario]), budget_sequences=1
    )
    assert clean.violation is None


async def test_group_requires_must_be_met_before_the_group() -> None:
    # `buy` needs a product_id that only its sibling would capture, so the whole group is skipped.
    scenario = [
        ParallelStep(parallel=[Step(action="create_product", params={"price": 1, "stock": 1}), buy(1)]),
        Step(action="admin_export"),
    ]
    model = only_rule("admin_export_forbidden")
    gen = Generator(model, 1, scenarios=[scenario])
    out = await search(model, fixed=False, generator=gen, concurrency=1, budget_sequences=1)
    assert out.violation is not None and out.trace is not None
    assert [t.step.model_dump() for t in out.trace] == [
        Step(action="admin_export", actor="customer").model_dump()
    ]
    assert out.violation.step_index == 0


# --- the executor: real overlap, errors and cancellation ---


GATE_MODEL = load_model_str(
    """
version: 1
actors: [{name: u}]
actions:
  - {name: seed, actor: u, request: {method: GET, path: /seed}, capture: {x: "$.x"}}
  - {name: hit, actor: u, request: {method: POST, path: "/hit/{{ref.x}}"}, requires: [x]}
  - {name: boom, actor: u, request: {method: POST, path: "/boom/{{ref.x}}"}, requires: [x]}
"""
)


class GateApp:
    """A raw ASGI app that tracks how many `/hit` requests are in flight at once."""

    def __init__(self, *, release: bool = True) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.started = 0
        self.cancelled = 0
        self.both_in = asyncio.Event()
        self.release = release

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        path = scope["path"]
        if path.startswith("/boom"):
            raise RuntimeError("app crashed")
        body = b'{"x": 1}'
        if path.startswith("/hit"):
            self.in_flight += 1
            self.started += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            if self.in_flight >= 2:
                self.both_in.set()
            try:
                if self.release:
                    # Each request waits until its sibling is in flight too (proof of overlap).
                    await asyncio.wait_for(self.both_in.wait(), timeout=2)
                else:
                    await asyncio.Event().wait()  # never answers
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            finally:
                self.in_flight -= 1
            body = b'{"ok": true}'
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


def gate_executor(app: GateApp) -> Executor:
    return Executor(GATE_MODEL, "http://gate.test", transport=InProcessTransport(app))


def _other_tasks() -> set[asyncio.Task[Any]]:
    return asyncio.all_tasks() - {asyncio.current_task()}


async def _seeded(ex: Executor) -> SequenceContext:
    ctx = ex.new_context()
    await ex.run_step(ctx, Step(action="seed"), random.Random(0))
    assert ctx.pool["x"] == [1]
    return ctx


async def test_parallel_requests_really_overlap_in_process() -> None:
    app = GateApp()
    async with gate_executor(app) as ex:
        ctx = await _seeded(ex)
        results = await ex.run_step(ctx, ParallelStep(parallel=[Step(action="hit")] * 2), random.Random(0))
    assert isinstance(results, list) and [r.status for r in results] == [200, 200]
    assert app.max_in_flight == 2  # neither request could have finished before the other started


async def test_app_crash_in_one_sub_step_is_recorded_and_the_sibling_completes() -> None:
    app = GateApp()
    async with gate_executor(app) as ex:
        ctx = await _seeded(ex)
        before = _other_tasks()
        step = ParallelStep(parallel=[Step(action="boom"), Step(action="seed")])
        crashed, ok = await ex.run_step(ctx, step, random.Random(0))  # type: ignore[misc]
        assert _other_tasks() == before
    assert crashed.status is None and "app crashed" in (crashed.error or "")
    assert ok.status == 200 and ctx.pool["x"] == [1, 1]  # the sibling's capture was applied


async def test_cancelling_a_group_cancels_and_awaits_every_request() -> None:
    app = GateApp(release=False)
    async with gate_executor(app) as ex:
        ctx = await _seeded(ex)
        before = _other_tasks()
        task = asyncio.create_task(
            ex.run_step(ctx, ParallelStep(parallel=[Step(action="hit")] * 2), random.Random(0))
        )
        await asyncio.wait_for(app.both_in.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert _other_tasks() == before  # nothing left running
    assert app.started == 2 and app.cancelled == 2 and app.in_flight == 0
