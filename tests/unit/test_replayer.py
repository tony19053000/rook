"""ROOK-010: the Replayer (k/N with a flaky flag), in-process.

The nondeterministic fixture is a tiny raw ASGI app defined here (minishop is not touched): its
`poke` bug only triggers on every other request, so a trace that breaks the rule once replays 5/10.
"""

import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from test_parallel import STOCK
from test_runner import search
from test_shrinker import REFUND, executor, search_and_shrink

from rook.core.events import Event, EventBus
from rook.engine.executor import Executor, StepResult
from rook.engine.inprocess import InProcessTransport
from rook.engine.judge import Judge, Violation
from rook.engine.replayer import Replayer, ReplayResult
from rook.engine.runner import TraceStep
from rook.engine.shrinker import replay_trace
from rook.model.loader import load_model_str
from rook.model.schema import ParallelStep, Step

# --- the nondeterministic fixture ---

FLIP_MODEL = load_model_str(
    """
version: 1
actors: [{name: u}]
actions:
  - {name: create, actor: u, request: {method: POST, path: /items}, capture: {item_id: "$.id"}}
  - {name: poke, actor: u, request: {method: POST, path: "/items/{{ref.item_id}}/poke"}, requires: [item_id]}
state:
  - name: item
    each: item_id
    request: {method: GET, path: "/items/{{item_id}}"}
    fields: {value: "$.value"}
rules:
  - {id: value_non_negative, text: "An item's value never goes below zero", kind: state, scope: item,
     check: "item.value >= 0", status: approved}
"""
)


class FlipApp:
    """`poke` adds 1, except that every other poke (2nd, 4th, ...) wrongly sets the value to -1."""

    def __init__(self, *, buggy: bool = True) -> None:
        self.buggy = buggy
        self.items: dict[int, int] = {}
        self.pokes = 0

    async def __call__(self, scope: MutableMapping[str, Any], receive: Any, send: Any) -> None:
        method, parts = scope["method"], scope["path"].strip("/").split("/")
        status, body = 404, {"error": "not found"}
        if method == "POST" and parts == ["items"]:
            item_id = len(self.items) + 1
            self.items[item_id] = 0
            status, body = 200, {"id": item_id}
        elif len(parts) >= 2 and parts[0] == "items" and int(parts[1]) in self.items:
            item_id = int(parts[1])
            if method == "POST" and parts[2:] == ["poke"]:
                self.pokes += 1
                broken = self.buggy and self.pokes % 2 == 0
                self.items[item_id] = -1 if broken else self.items[item_id] + 1
                status, body = 200, {"ok": True}
            elif method == "GET" and len(parts) == 2:
                status, body = 200, {"id": item_id, "value": self.items[item_id]}
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": json.dumps(body).encode()})


def flip_executor(app: FlipApp) -> Executor:
    return Executor(FLIP_MODEL, "http://flip.test", transport=InProcessTransport(app))


def flip_trace() -> list[TraceStep]:
    """create, poke: pinned to the item that `create` captured."""
    # Only the steps and the pinned refs matter for a replay; these are the results a run records.
    return [
        TraceStep(Step(action="create"), [StepResult("create", "u", {}, {}, {})]),
        TraceStep(
            Step(action="poke"), [StepResult("poke", "u", {}, {"item_id": 1}, {}, refs_index={"item_id": 0})]
        ),
    ]


async def events_of(bus: EventBus) -> list[Event]:
    await bus.close("r_test")
    return [e async for e in bus.subscribe("r_test")]


# --- acceptance: the shrunk refund counterexample gives 10/10 ---


@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_shrunk_refund_counterexample_replays_10_of_10(seed: int) -> None:
    _, shrunk = await search_and_shrink(seed)
    assert shrunk.reproduced
    async with executor(REFUND) as ex:
        result = await Replayer(REFUND, ex, None, "r").replay(shrunk.violation, shrunk.trace)
    assert (result.k, result.n, result.reproduced, result.flaky) == (10, 10, "10/10", False)
    assert all(v is not None and v.rule_id == "refund_le_paid" for v in result.violations)
    # Fresh entities: every replay broke the rule on its own, new order.
    assert len({v.entity for v in result.violations if v is not None}) == 10

    # On the fixed app the same counterexample never breaks the rule.
    async with executor(REFUND, fixed=True) as ex:
        fixed = await Replayer(REFUND, ex, None, "r").replay(shrunk.violation, shrunk.trace)
    assert (fixed.k, fixed.reproduced, fixed.flaky) == (0, "0/10", False)


# --- acceptance: a deliberately nondeterministic fixture reports flaky ---


async def test_nondeterministic_fixture_is_flaky() -> None:
    app = FlipApp()
    async with flip_executor(app) as ex:
        result = await Replayer(FLIP_MODEL, ex, None, "r").replay("value_non_negative", flip_trace())
    assert (result.k, result.n, result.reproduced, result.flaky) == (5, 10, "5/10", True)
    # Alternate replays broke the rule (the 2nd, 4th, ... poke), each on its own fresh item.
    assert [v is not None for v in result.violations] == [False, True] * 5
    assert len(app.items) == 10
    assert [v.entity for v in result.violations if v is not None] == [2, 4, 6, 8, 10]
    assert all(v.step_index == 1 for v in result.violations if v is not None)


async def test_deterministic_fixture_is_not_flaky() -> None:
    async with flip_executor(FlipApp(buggy=False)) as ex:
        result = await Replayer(FLIP_MODEL, ex, None, "r", n=4).replay("value_non_negative", flip_trace())
    assert (result.k, result.n, result.reproduced, result.flaky) == (0, 4, "0/4", False)


async def test_minishop_stock_race_reports_k_of_n() -> None:
    out = await search(STOCK, fixed=False, seed=2, budget_sequences=2_000)
    assert out.violation is not None and out.trace is not None
    assert any(isinstance(t.step, ParallelStep) for t in out.trace)
    async with executor(STOCK) as ex:
        result = await Replayer(STOCK, ex, None, "r").replay(out.violation, out.trace)
    print(f"\nstock race replay: {result.reproduced}{' (flaky)' if result.flaky else ''}")
    assert result.n == 10 and 1 <= result.k <= 10
    assert result.flaky == (result.k < 10)
    assert all(v is None or v.rule_id == "stock_non_negative" for v in result.violations)


# --- the Judge decides; only the same rule counts ---


async def test_another_rule_does_not_count() -> None:
    async with flip_executor(FlipApp()) as ex:
        result = await Replayer(FLIP_MODEL, ex, None, "r").replay("some_other_rule", flip_trace())
    assert result.rule_id == "some_other_rule"
    assert (result.k, result.flaky, result.violations) == (0, False, [None] * 10)


def test_result_flags() -> None:
    v = Violation(rule_id="x", step_index=0, entity=None, observed={}, expected_expr="")
    assert ReplayResult("x", 3, [v, v, v]).flaky is False
    assert ReplayResult("x", 3, [v, None, v]).flaky is True
    assert ReplayResult("x", 3, [None, None, None]).flaky is False
    assert ReplayResult("x", 1, [v]).reproduced == "1/1"


def test_n_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Replayer(FLIP_MODEL, flip_executor(FlipApp()), None, "r", n=0)


async def test_replay_trace_stops_at_the_first_violation() -> None:
    trace = [*flip_trace(), flip_trace()[1], flip_trace()[1]]  # create, poke, poke, poke
    async with flip_executor(FlipApp()) as ex:
        found, ran = await replay_trace(ex, Judge(FLIP_MODEL), trace)
    # The first poke is fine, the second breaks the rule: the third never runs.
    assert found is not None and found.rule_id == "value_non_negative" and found.step_index == 2
    assert len(ran) == 3 and ran[2].pinned_refs == [{"item_id": 0}]


# --- events and executor handling ---


async def test_events() -> None:
    bus = EventBus()
    async with flip_executor(FlipApp()) as ex:
        result = await Replayer(FLIP_MODEL, ex, bus, "r_test").replay("value_non_negative", flip_trace())
    events = await events_of(bus)
    assert events[0].type == "engine.started"
    assert events[0].data == {"worker": "replayer", "label": "2 steps x 10, rule value_non_negative"}
    progress = [e.data for e in events if e.type == "engine.progress"]
    assert progress and all(d["worker"] == "replayer" for d in progress)
    assert progress[-1] == {"worker": "replayer", "pct": 100.0, "label": "5/10 reproduced", "count": 10}
    assert events[-1].type == "engine.finished"
    assert events[-1].data == {"worker": "replayer", "ok": True, "summary": "reproduced 5/10 (flaky)"}
    assert result.k == 5
    # Only the Judge emits violations: the replayer never publishes violation.found.
    assert not any(e.type == "violation.found" for e in events)


async def test_executor_factory_is_entered_and_closed() -> None:
    made: list[Executor] = []

    def factory() -> Executor:
        made.append(flip_executor(FlipApp(buggy=False)))
        return made[-1]

    bus = EventBus()
    result = await Replayer(FLIP_MODEL, factory, bus, "r_test", n=2).replay(
        "value_non_negative", flip_trace()
    )
    assert len(made) == 1 and result.reproduced == "0/2"
    finished = [e.data for e in await events_of(bus) if e.type == "engine.finished"]
    assert finished == [{"worker": "replayer", "ok": False, "summary": "reproduced 0/2"}]


async def test_failure_emits_finished_not_ok() -> None:
    class Broken(Executor):
        def new_context(self) -> Any:
            raise RuntimeError("sandbox gone")

    bus = EventBus()
    ex = Broken(FLIP_MODEL, "http://flip.test", transport=InProcessTransport(FlipApp()))
    async with ex:
        with pytest.raises(RuntimeError):
            await Replayer(FLIP_MODEL, ex, bus, "r_test").replay("value_non_negative", flip_trace())
    finished = [e.data for e in await events_of(bus) if e.type == "engine.finished"]
    assert finished == [
        {"worker": "replayer", "ok": False, "summary": "replay stopped: RuntimeError: sandbox gone"}
    ]
