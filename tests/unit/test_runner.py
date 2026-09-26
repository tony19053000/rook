"""ROOK-007 + ROOK-008: the search runner with the Judge, in-process against minishop.

The 20,000-sequence fixed-mode search and the throughput measurement take minutes (minishop's
signup and login scan every user, so the app slows down as a run creates users). They run only with
`ROOK_SLOW=1`; the default suite keeps shorter versions of both.
"""

import asyncio
import importlib.util
import itertools
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from rook.core.events import Event, EventBus
from rook.engine.executor import EgressError, Executor
from rook.engine.generator import Generator
from rook.engine.inprocess import InProcessTransport
from rook.engine.judge import Judge
from rook.engine.runner import PROGRESS_INTERVAL, Runner, RunOutcome
from rook.model.loader import load_model, load_model_str
from rook.model.schema import ParallelStep, RookModel, Step

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
BASE = "http://minishop.test"
ENV = {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}  # the fixture's built-in default, not a secret
SLOW = pytest.mark.skipif(os.environ.get("ROOK_SLOW") != "1", reason="slow: set ROOK_SLOW=1")

_spec = importlib.util.spec_from_file_location("minishop_app_runner", FIXTURE_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)

MODEL = load_model(FIXTURE_DIR / "rook.yaml")


def only_rule(rule_id: str) -> RookModel:
    """The minishop model with just one approved rule (so another bug can't be found first)."""
    rules = [
        r.model_copy(update={"status": "approved" if r.id == rule_id else "rejected"}) for r in MODEL.rules
    ]
    return MODEL.model_copy(update={"rules": rules})


def executor(model: RookModel = MODEL, *, fixed: bool) -> Executor:
    return Executor(model, BASE, transport=InProcessTransport(minishop.create_app(fixed=fixed)), env=ENV)


async def search(
    model: RookModel = MODEL, *, fixed: bool, seed: int | str = 1, bus: EventBus | None = None, **kwargs: Any
) -> RunOutcome:
    kwargs.setdefault("budget_seconds", 300.0)
    async with executor(model, fixed=fixed) as ex:
        return await Runner(model, ex, bus, "r_test", seed=seed, **kwargs).run()


async def events_of(bus: EventBus) -> list[Event]:
    await bus.close("r_test")
    return [e async for e in bus.subscribe("r_test")]


# --- ROOK-008 acceptance: the bugs are found, the fixed app is clean ---


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
async def test_finds_refund_bug_within_20000_sequences(seed: int) -> None:
    out = await search(only_rule("refund_le_paid"), fixed=False, seed=seed, budget_sequences=20_000)
    assert out.violation is not None and out.violation.rule_id == "refund_le_paid"
    assert out.sequence_index is not None and out.sequence_index < 20_000
    v = out.violation
    assert v.observed["refunded"] > v.observed["paid"]
    # The step that broke the rule is the last one run, and it was a refund of that order.
    assert out.trace is not None and v.step_index == len(out.trace) - 1
    last = out.trace[-1]
    assert last.results[0].action == "refund"
    assert any(r.refs_used.get("order_id") == v.entity for r in last.results)


async def test_finds_admin_export_bug() -> None:
    out = await search(only_rule("admin_export_forbidden"), fixed=False, budget_sequences=20_000)
    assert out.violation is not None and out.violation.rule_id == "admin_export_forbidden"
    assert out.violation.observed["status"] == 200
    assert out.trace is not None and out.trace[-1].results[0].action == "admin_export"


async def test_all_rules_on_buggy_minishop_find_some_violation() -> None:
    out = await search(fixed=False, budget_sequences=2_000)
    assert out.violation is not None
    assert out.violation.rule_id in {r.id for r in MODEL.rules}


async def test_no_violation_on_fixed_minishop_short() -> None:
    out = await search(fixed=True, seed=7, budget_sequences=500)
    assert out.violation is None and out.trace is None
    assert out.sequences_run == 500 and out.rule_errors == {}


@SLOW
async def test_no_violation_on_fixed_minishop_20000() -> None:
    out = await search(fixed=True, seed=2026, budget_sequences=20_000, budget_seconds=900)
    assert out.violation is None and out.sequences_run == 20_000


@SLOW
async def test_throughput_in_process() -> None:
    out = await search(fixed=True, seed=3, budget_sequences=3_000)
    print(f"\nin-process minishop: {out.per_sec:.0f} sequences/s")
    assert out.per_sec > 150


# --- budget ---


async def test_stops_at_sequence_budget() -> None:
    out = await search(fixed=True, budget_sequences=37, concurrency=8)
    assert out.violation is None and out.sequences_run == 37


async def test_stops_at_time_budget() -> None:
    start = time.monotonic()
    out = await search(fixed=True, budget_sequences=10_000_000, budget_seconds=0.3)
    assert out.violation is None and 0 < out.sequences_run < 10_000_000
    assert time.monotonic() - start < 3.0


async def test_zero_budget_runs_nothing() -> None:
    out = await search(fixed=True, budget_sequences=0)
    assert out.sequences_run == 0 and out.violation is None


def test_concurrency_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Runner(MODEL, executor(fixed=True), None, "r", seed=1, concurrency=0)


# --- determinism and the trace ---


async def test_same_seed_same_violation_with_one_worker() -> None:
    model = only_rule("refund_le_paid")
    a = await search(model, fixed=False, seed=9, concurrency=1, budget_sequences=20_000)
    b = await search(model, fixed=False, seed=9, concurrency=1, budget_sequences=20_000)
    assert a.sequence_index == b.sequence_index and a.trace is not None and b.trace is not None
    assert [t.step.model_dump() for t in a.trace] == [t.step.model_dump() for t in b.trace]
    assert [t.pinned_refs for t in a.trace] == [t.pinned_refs for t in b.trace]


async def test_trace_replays_to_the_same_violation() -> None:
    model = only_rule("refund_le_paid")
    out = await search(model, fixed=False, seed=4)
    assert out.violation is not None and out.trace is not None
    for entry in out.trace:  # the trace is concrete: actor and every param are fixed
        for sub in entry.step.parallel if isinstance(entry.step, ParallelStep) else [entry.step]:
            assert sub.actor is not None
            assert set(sub.params) == set(model.action(sub.action).params)

    judge = Judge(model)
    async with executor(model, fixed=False) as ex:
        ctx = ex.new_context()
        rng = random.Random(0)  # unused: params and refs are all pinned
        found = None
        for index, entry in enumerate(out.trace):
            result = await ex.run_step(ctx, entry.step, rng, entry.pinned_refs)
            assert isinstance(result, list) == isinstance(entry.step, ParallelStep)
            found = judge.check_state(await ex.read_state(ctx), index)
            if found is not None:
                break
    assert found is not None and found.rule_id == "refund_le_paid"
    assert found.step_index == out.violation.step_index


async def test_designed_scenario_runs_first() -> None:
    model = only_rule("refund_le_paid")
    scenario = [
        Step(action="create_product", params={"price": 100, "stock": 5}),
        Step(action="buy", params={"quantity": 1}),
        Step(action="refund", params={"amount": 60}),
        Step(action="refund", params={"amount": 50}),
    ]
    gen = Generator(model, 1, scenarios=[scenario])
    out = await search(model, fixed=False, generator=gen, concurrency=1)
    assert out.sequence_index == 0 and out.violation is not None
    assert out.violation.observed["refunded"] == 110 and out.violation.observed["paid"] == 100
    assert [t.step.model_dump() for t in out.trace or []] == [
        s.model_copy(update={"actor": "admin" if s.action == "create_product" else "customer"}).model_dump()
        for s in scenario
    ]


# --- events ---


async def test_events_on_violation() -> None:
    bus = EventBus()
    out = await search(only_rule("refund_le_paid"), fixed=False, seed=2, bus=bus)
    assert out.violation is not None
    events = await events_of(bus)
    types = [e.type for e in events]
    assert types[:2] == ["engine.started", "engine.started"]
    assert {e.data["worker"] for e in events if e.type == "engine.started"} == {"runner", "judge"}
    found = [e for e in events if e.type == "violation.found"]
    assert len(found) == 1
    assert found[0].data["rule_id"] == "refund_le_paid"
    assert found[0].data["violation_id"] == out.violation.violation_id
    assert found[0].data["steps_count"] == len(out.trace or [])
    finished = {e.data["worker"]: e.data for e in events if e.type == "engine.finished"}
    assert finished["runner"]["ok"] is True and finished["judge"]["ok"] is False
    progress = [e for e in events if e.type == "search.progress"]
    assert progress and progress[-1].data["rules"] == {"refund_le_paid": "broken"}


async def test_events_on_clean_run_and_throttling() -> None:
    bus = EventBus()
    out = await search(fixed=True, bus=bus, budget_sequences=10_000_000, budget_seconds=1.2)
    events = await events_of(bus)
    assert not any(e.type == "violation.found" for e in events)
    for kind in ("search.progress", "engine.progress"):
        stamps = [e.ts for e in events if e.type == kind]
        assert stamps, kind
        times = [_ts(t) for t in stamps]
        gaps = [b - a for a, b in itertools.pairwise(times)]
        # At most 5 per second (clock-rounding slack of 20 ms on the event timestamps).
        assert all(g >= PROGRESS_INTERVAL - 0.02 for g in gaps), (kind, gaps)
    last = [e for e in events if e.type == "search.progress"][-1].data
    assert last["sequences"] == out.sequences_run and last["per_sec"] > 0
    assert set(last["rules"].values()) == {"holding"}
    engine_progress = [e.data for e in events if e.type == "engine.progress"]
    assert {d["worker"] for d in engine_progress} <= {"runner", "judge"}
    assert all(0 <= d["pct"] <= 100 for d in engine_progress)
    finished = {e.data["worker"]: e.data for e in events if e.type == "engine.finished"}
    assert finished["runner"]["ok"] and finished["judge"]["ok"]


def _ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp).timestamp()


async def test_rule_errors_are_logged_not_violations() -> None:
    bad = MODEL.rules[0].model_copy(update={"id": "bad", "check": "order.missing_field > 0"})
    model = MODEL.model_copy(update={"rules": [bad]})
    bus = EventBus()
    out = await search(model, fixed=True, bus=bus, budget_sequences=50)
    assert out.violation is None and set(out.rule_errors) == {"bad"}
    logs = [e.data for e in await events_of(bus) if e.type == "log"]
    assert len(logs) == 1 and logs[0]["level"] == "warn" and "not a violation" in logs[0]["text"]


# --- executor ownership and failures ---


async def test_executor_factory_is_entered_and_closed() -> None:
    made: list[Executor] = []

    def factory() -> Executor:
        made.append(executor(fixed=True))
        return made[-1]

    out = await Runner(MODEL, factory, None, "r", seed=1, budget_sequences=20).run()
    assert out.sequences_run == 20 and len(made) == 1 and made[0]._client is None


EGRESS_MODEL = """
version: 1
actors: [{name: u}]
actions:
  - {name: go, actor: u, request: {method: GET, path: "/{{p.where}}"}, params: {where: {choice: ["/evil.test/x"]}}}
rules:
  - {id: r, text: t, kind: response, when: {action: go}, check: "response.status == 200", status: approved}
"""


async def test_egress_error_stops_the_run_and_reports_failure() -> None:
    model = load_model_str(EGRESS_MODEL)
    bus = EventBus()
    async with Executor(model, BASE, transport=InProcessTransport(minishop.create_app(fixed=True))) as ex:
        with pytest.raises(EgressError):
            await Runner(model, ex, bus, "r_test", seed=1, budget_sequences=100).run()
    events = await events_of(bus)
    finished = [e.data for e in events if e.type == "engine.finished"]
    assert len(finished) == 2 and not any(d["ok"] for d in finished)
    assert not any(e.type == "violation.found" for e in events)


async def test_no_worker_tasks_outlive_the_run() -> None:
    before = asyncio.all_tasks()
    await search(only_rule("refund_le_paid"), fixed=False, seed=1, concurrency=16)
    await asyncio.sleep(0)
    assert asyncio.all_tasks() - before == set()


async def test_skipped_steps_do_not_appear_in_trace() -> None:
    # A buy of a product with stock 0 fails, so no order is captured and the refund is skipped.
    scenario = [
        Step(action="create_product", params={"price": 10, "stock": 0}),
        Step(action="buy", params={"quantity": 1}),
        Step(action="refund", params={"amount": 20}),
        Step(action="admin_export"),
    ]
    model = only_rule("admin_export_forbidden")
    gen = Generator(model, 1, scenarios=[scenario])
    out = await search(model, fixed=False, generator=gen, concurrency=1, budget_sequences=1)
    assert out.violation is not None and out.trace is not None
    assert [t.step.action for t in out.trace] == ["create_product", "buy", "admin_export"]  # type: ignore[union-attr]
    assert out.trace[1].results[0].status == 409
    assert out.violation.step_index == 2
