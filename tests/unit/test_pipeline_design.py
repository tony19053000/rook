"""ROOK-019: the DESIGN phase (Test Designer + Strategist) and how the search uses it.

The default suite uses scripted fakes and a committed replay of real Bob calls. The Understand and RULES
phases are replayed from their own recordings, so only the Test Designer and the Strategist are live. The
live run (`-m bob`, no Docker needed) re-records the DESIGN calls when ROOK_RECORD_DIR is set:

    source ~/.bob-key.env
    ROOK_RECORD_DIR=tests/fixtures/recordings/design_minishop \
        uv run pytest -m bob -s tests/unit/test_pipeline_design.py

Then replace the local workspace path (`/tmp/pytest-of-<user>/.../ws`) in the new files with `/workspace`:
Bob's tool calls quote it, and replay never uses it.

The AC measurement (`test_recorded_design_finds_the_refund_bug_sooner_than_random`) searches buggy minishop
in-process with only the refund rule approved, `concurrency=1` so every count is exact and reproducible.
"""

import asyncio
import math
import os
import statistics
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import test_pipeline_rules as rules_tests
from pydantic import BaseModel
from test_pipeline_understand import (
    _SECRET_PATTERNS,
    BASE,
    MINISHOP_MODEL,
    RUN,
    FakeClient,
    events,
    minishop,
)

from rook.agents.bob import AgentOutputError, AgentResult, BobClient
from rook.agents.design import DesignedScenario, DesignPipeline, DesignResult
from rook.agents.schemas import TestDesignerOutput as DesignerOut
from rook.agents.schemas import example_for
from rook.core.events import EventBus
from rook.engine.executor import Executor
from rook.engine.generator import Generator
from rook.engine.inprocess import InProcessTransport
from rook.engine.runner import Runner, RunOutcome
from rook.engine.scenarios import MAX_SCENARIOS, MAX_WEIGHT, check_scenario, sanitize_weights
from rook.model.schema import ParallelStep, RookModel, Step

RECORDINGS = Path(__file__).parents[1] / "fixtures" / "recordings" / "design_minishop"
ENV = rules_tests.ENV
SEEDS = [1, 2, 3, 4, 5]
AC_BUDGET = 5_000

workspace = rules_tests.workspace  # the pytest fixture: a plain copy of minishop


def approved(model: RookModel, *rule_ids: str) -> RookModel:
    """The model with only the given rules, approved."""
    rules = [r.model_copy(update={"status": "approved"}) for r in model.rules if r.id in rule_ids]
    return model.model_copy(update={"rules": rules})


MODEL = approved(MINISHOP_MODEL, *[r.id for r in MINISHOP_MODEL.rules])
REFUND_ONLY = approved(MINISHOP_MODEL, "refund_le_paid")


def steps(*items: dict[str, Any]) -> list[Any]:
    return [ParallelStep.model_validate(i) if "parallel" in i else Step.model_validate(i) for i in items]


DOUBLE_REFUND = [
    {"action": "create_product", "params": {"price": 100, "stock": 5}},
    {"action": "buy", "params": {"quantity": 1}},
    {"action": "refund", "params": {"amount": 60}},
    {"action": "refund", "params": {"amount": 60}},
]


# --- the engine checks designed scenarios ---


def test_a_valid_scenario_passes() -> None:
    assert check_scenario(MODEL, steps(*DOUBLE_REFUND)) is None
    race = [DOUBLE_REFUND[0], {"parallel": [{"action": "buy"}, {"action": "buy", "actor": "customer"}]}]
    assert check_scenario(MODEL, steps(*race)) is None


@pytest.mark.parametrize(("scenario", "reason"), [
    ([{"action": "steal"}], "step 1: unknown action 'steal'"),
    ([{"action": "admin_export", "actor": "root"}], "step 1: unknown actor 'root'"),
    ([{"action": "create_product", "params": {"price": 501, "stock": 1}}],
     "step 1: create_product.price: 501 is outside [1, 500]"),
    ([{"action": "create_product", "params": {"price": -1}}], "step 1: create_product.price: -1 is outside"),
    ([{"action": "create_product", "params": {"price": "100"}}], "'100' is not an integer"),
    ([{"action": "create_product", "params": {"price": 1.5}}], "1.5 is not an integer"),
    ([{"action": "create_product", "params": {"price": True}}], "True is not an integer"),
    ([{"action": "create_product", "params": {"discount": 5}}], "create_product has no param 'discount'"),
    ([{"action": "refund", "params": {"amount": 5}}],
     "step 1: refund needs order_id, which no earlier step captures"),
    ([DOUBLE_REFUND[0], {"parallel": [{"action": "buy"}, {"action": "refund"}]}],
     "step 2: refund needs order_id"),  # a sibling never provides a ref
    ([DOUBLE_REFUND[0]] * 13, "it has 13 steps (the limit is 12)"),
    ([DOUBLE_REFUND[0], {"parallel": [{"action": "buy"}] * 5}], "step 2: a parallel group of 5"),
])
def test_invalid_scenarios_are_rejected_with_a_reason(scenario: list[dict[str, Any]], reason: str) -> None:
    problem = check_scenario(MODEL, steps(*scenario))
    assert problem is not None and reason in problem


def test_choice_and_string_params_are_checked() -> None:
    parts = MINISHOP_MODEL.model_dump(mode="json", by_alias=True, exclude_none=True)
    parts["actions"].append({"name": "search", "actor": "customer", "request": {"method": "GET", "path": "/s"},
                             "params": {"sort": {"choice": [1, "price"]}, "q": {"string": {"pattern": "[a-z]{1,5}"}},
                                        "tag": {"string": {"values": ["new", "old"]}}}})
    model = RookModel.model_validate(parts)
    assert check_scenario(model, steps({"action": "search", "params": {"sort": 1, "q": "abc", "tag": "old"}})) \
        is None
    for params, reason in [({"sort": True}, "not one of the choices"), ({"sort": "name"}, "not one of the choices"),
                           ({"q": "ABC"}, "does not match"), ({"q": "a" * 201}, "not a string"),
                           ({"tag": "mid"}, "not one of the values")]:
        problem = check_scenario(model, steps({"action": "search", "params": params}))
        assert problem is not None and reason in problem, params


# --- the engine sanitizes strategist weights ---


def test_weights_are_sanitized() -> None:
    raw = {"buy": math.nan, "refund": math.inf, "cancel": -1.0, "ship": 1e9, "steal": 5.0, "create_product": 2.0,
           "admin_export": 0.0}
    out = sanitize_weights(MODEL, raw)
    assert out.weights == {"ship": MAX_WEIGHT, "create_product": 2.0, "admin_export": 0.0}
    notes = "\n".join(out.notes)
    for expected in ["buy: nan is not a finite number", "refund: inf is not a finite number",
                     "cancel: -1.0 is negative", f"ship: 1000000000.0 capped at {MAX_WEIGHT}",
                     "unknown action 'steal' ignored"]:
        assert expected in notes
    Generator(MODEL, 1, weights=out.weights)  # always accepted by the generator


def test_weights_that_disable_every_starting_action_are_ignored() -> None:
    all_zero = {a.name: 0.0 for a in MODEL.actions}
    out = sanitize_weights(MODEL, all_zero)
    assert out.weights == {} and "all weights ignored" in out.notes[-1]
    # Actions that need no ref (create_product, admin_export) are the only way to start a sequence.
    out = sanitize_weights(MODEL, {"create_product": 0.0, "admin_export": 0.0, "buy": 3.0})
    assert out.weights == {}
    assert sanitize_weights(MODEL, {"create_product": 0.0}).weights == {"create_product": 0.0}
    assert sanitize_weights(MODEL, {}).weights == {} and sanitize_weights(MODEL, {}).notes == []


def test_generator_with_weights_is_deterministic_per_seed() -> None:
    weights = {"refund": 4.0, "cancel": 0.0, "ship": 0.0}

    def run(seed: int, w: dict[str, float] | None) -> list[list[Any]]:
        gen = Generator(MODEL, seed, weights=w, scenarios=[steps(*DOUBLE_REFUND)], scenario_labels=["double"])
        return [[s.model_dump() for s in gen.sequence(i)] for i in range(200)]

    first = run(7, weights)
    assert first == run(7, weights)
    assert first != run(8, weights) and first != run(7, None)
    names = [s["action"] for seq in first for s in seq if "action" in s]
    names += [p["action"] for seq in first for s in seq for p in s.get("parallel", [])]
    assert "cancel" not in names and "ship" not in names  # weight 0: never picked
    assert first[0] == [s.model_dump() for s in steps(*DOUBLE_REFUND)]  # the scenario comes first
    with pytest.raises(ValueError, match="scenario_labels"):
        Generator(MODEL, 1, scenarios=[steps(*DOUBLE_REFUND)], scenario_labels=[])


# --- the pipeline with scripted agents ---


class ParallelFake(FakeClient):
    """Each call waits until both agents have started: the phase hangs unless the calls run at once."""

    def __init__(self, replies: dict[str, list[dict[str, Any] | Exception]]) -> None:
        super().__init__(replies)
        self.started: set[str] = set()
        self.both = asyncio.Event()

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        self.started.add(agent_id)
        if self.started >= {"test_designer", "strategist"}:
            self.both.set()
        await asyncio.wait_for(self.both.wait(), timeout=2.0)
        return await super().call(agent_id, slug, prompt, workspace, output_model, max_turns, max_cost)


def design(client: Any, ws: Path, model: RookModel = MODEL) -> DesignPipeline:
    return DesignPipeline(client, ws, model=model)


def designer_reply(*scenarios: dict[str, Any]) -> dict[str, Any]:
    return {"scenarios": list(scenarios)}


STRATEGY = {"weights": {"refund": 3.0, "buy": 2.0, "ghost": 1.0}, "focus": ["refund_le_paid", "nope"],
            "reason": "Refunds change the checked state."}


async def test_both_agents_run_in_parallel_and_bad_scenarios_are_dropped(workspace: Path) -> None:
    good = {"name": "double refund", "rule_id": "refund_le_paid", "steps": DOUBLE_REFUND}
    bad_ref = {"name": "refund first", "rule_id": "refund_le_paid", "steps": [{"action": "refund"}]}
    bad_rule = {"name": "other", "rule_id": "made_up_rule", "steps": DOUBLE_REFUND[:1]}
    client = ParallelFake({"test_designer": [designer_reply(good, bad_ref, bad_rule)], "strategist": [STRATEGY]})
    result = await design(client, workspace).run()

    assert [(s.name, s.rule_id) for s in result.scenarios] == [("double refund", "refund_le_paid")]
    assert result.dropped == [("refund first", "step 1: refund needs order_id, which no earlier step captures"),
                              ("other", "rule 'made_up_rule' is not an approved rule")]
    assert result.weights == {"refund": 3.0, "buy": 2.0}
    assert result.focus == ["refund_le_paid"]
    assert [e.data["phase"] for e in events(client, "run.phase")] == ["DESIGN"]
    logs = [e.data["text"] for e in events(client, "log")]
    assert "Designed scenario 'refund first' dropped by the engine: step 1: refund needs order_id" in logs[0]
    assert any("1 designed scenarios accepted, 2 dropped" in t for t in logs)
    assert any("unknown action 'ghost' ignored" in t for t in logs)
    assert any(t.startswith("Strategist (a guess): focus on refund_le_paid; weights buy=2, refund=3") for t in logs)
    # The rules (Bob output quoting the repo) are wrapped as untrusted data in both prompts.
    for agent in ("test_designer", "strategist"):
        prompt = client.prompts(agent)[0]
        assert '<untrusted path="rules">' in prompt and "refund_le_paid" in prompt
        assert '"create_product"' in prompt
    assert "the search has not run yet" in client.prompts("strategist")[0]


async def test_scenarios_over_the_cap_are_dropped(workspace: Path) -> None:
    many = [{"name": f"s{i}", "rule_id": "refund_le_paid", "steps": DOUBLE_REFUND} for i in range(MAX_SCENARIOS + 2)]
    client = FakeClient({"test_designer": [designer_reply(*many)], "strategist": [STRATEGY]})
    result = await design(client, workspace).run()
    assert len(result.scenarios) == MAX_SCENARIOS
    assert [d[0] for d in result.dropped] == [f"s{MAX_SCENARIOS}", f"s{MAX_SCENARIOS + 1}"]


async def test_a_failed_agent_leaves_the_search_unguided(workspace: Path) -> None:
    client = FakeClient({"test_designer": [AgentOutputError("no json block")], "strategist": [STRATEGY]})
    result = await design(client, workspace).run()
    assert result.scenarios == [] and result.weights == {"refund": 3.0, "buy": 2.0}
    client = FakeClient({"test_designer": [designer_reply({"name": "x", "rule_id": "refund_le_paid",
                                                           "steps": DOUBLE_REFUND})],
                         "strategist": [AgentOutputError("bad json")]})
    result = await design(client, workspace).run()
    assert len(result.scenarios) == 1 and result.weights == {}
    warns = [e.data["text"] for e in events(client, "log") if e.data["level"] == "warn"]
    assert any(w.startswith("The Strategist failed") for w in warns)


async def test_no_bob_call_without_approved_rules(workspace: Path) -> None:
    client = FakeClient({})
    result = await design(client, workspace, MINISHOP_MODEL.model_copy(update={"rules": []})).run()
    assert result == DesignResult() and client.calls == []


def test_refuses_to_run_bob_in_the_rook_repo() -> None:
    with pytest.raises(ValueError, match="Rook's own repo"):
        design(FakeClient({}), Path(__file__).parents[2])


def test_the_prompt_example_is_a_valid_scenario() -> None:
    example = DesignerOut.model_validate(example_for(DesignerOut))
    assert check_scenario(MODEL, example.scenarios[0].steps) is None


# --- the search runs designed scenarios first ---


async def search(model: RookModel, seed: int, generator: Generator | None = None, *, fixed: bool = False,
                 bus: EventBus | None = None, concurrency: int = 1, budget: int = AC_BUDGET,
                 env: dict[str, str] = ENV) -> RunOutcome:
    with mock.patch.dict(os.environ, env):
        app = minishop.create_app(fixed=fixed)
    async with Executor(model, BASE, transport=InProcessTransport(app), env=env) as ex:
        return await Runner(model, ex, bus, RUN, seed=seed, generator=generator, concurrency=concurrency,
                            budget_sequences=budget, budget_seconds=300.0).run()


def scripted_design() -> DesignResult:
    admin = DesignedScenario("customer exports", "admin_export_forbidden", steps({"action": "admin_export"}))
    refund = DesignedScenario("double refund", "refund_le_paid", steps(*DOUBLE_REFUND))
    return DesignResult(scenarios=[admin, refund], weights={"refund": 2.0})


@pytest.mark.parametrize("concurrency", [1, 4])
async def test_designed_scenarios_run_first_visible_in_events(concurrency: int) -> None:
    bus = EventBus()
    gen = scripted_design().generator(REFUND_ONLY, 3)
    out = await search(REFUND_ONLY, 3, gen, bus=bus, concurrency=concurrency)
    assert out.violation is not None
    if concurrency == 1:  # with more workers, a random sequence may finish first
        assert out.sequence_index == 1  # the double refund, the 2nd sequence
    history = bus._channel(RUN).history
    started = [e.data["label"] for e in history if e.type == "engine.started" and e.data["worker"] == "runner"]
    assert started == ["seed 3, 2 designed scenarios first"]
    logs = [e.data["text"] for e in history if e.type == "log"]
    assert logs[:2] == ["Designed scenario 1/2: customer exports (rule admin_export_forbidden)",
                        "Designed scenario 2/2: double refund (rule refund_le_paid)"]
    if concurrency == 1:
        assert "Found by designed scenario 2/2: double refund (rule refund_le_paid)" in logs
    types = [e.type for e in history]
    assert types.index("log") < types.index("violation.found")


async def test_random_sequences_follow_the_designed_ones() -> None:
    bus = EventBus()
    gen = scripted_design().generator(REFUND_ONLY, 3)
    out = await search(REFUND_ONLY, 3, gen, fixed=True, bus=bus, budget=10)  # no bug: all 10 run
    assert out.violation is None and out.sequences_run == 10
    logs = [e.data["text"] for e in bus._channel(RUN).history if e.type == "log"]
    assert logs == ["Designed scenario 1/2: customer exports (rule admin_export_forbidden)",
                    "Designed scenario 2/2: double refund (rule refund_le_paid)",
                    "All 2 designed scenarios started; random sequences follow"]


# --- the recorded real run (the AC) ---


async def rules_model(ws: Path) -> RookModel:
    """Understand + RULES replayed from their recordings, then every accepted rule approved (auto mode)."""
    known = await rules_tests.understand(ws)
    bob = BobClient(EventBus(), RUN, mode="replay", recordings_dir=rules_tests.RECORDINGS, replay_speed=1e9,
                    replay_max_gap=0.0)
    rules = rules_tests.rules_pipeline(bob, ws, known)
    result = await rules.run()
    model = await rules.approve([r.id for r in result.accepted])
    return model


async def measure(model: RookModel, result: DesignResult) -> dict[str, list[int]]:
    """Sequences run until the refund rule breaks, per seed: pure random, weights only, and the full design."""
    refund = next(r.id for r in model.rules if "refund" in r.check and "paid" in r.check)
    target = model.model_copy(update={"rules": [r for r in model.rules if r.id == refund]})
    weights_only = DesignResult(weights=result.weights)
    counts: dict[str, list[int]] = {"random": [], "weights": [], "designed": []}
    for seed in SEEDS:
        for arm, gen in [("random", None), ("weights", weights_only.generator(target, seed)),
                         ("designed", result.generator(target, seed))]:
            out = await search(target, seed, gen)
            assert out.violation is not None and out.violation.rule_id == refund, (arm, seed)
            counts[arm].append(out.sequences_run)
    for arm, values in counts.items():
        print(f"{arm:>8}: {values} total={sum(values)} median={statistics.median(values)}")
    return counts


def _check_ac(counts: dict[str, list[int]]) -> None:
    # The total is the whole search cost over the 5 seeds; the median guards against one lucky seed.
    assert sum(counts["designed"]) < sum(counts["random"]), counts
    assert statistics.median(counts["designed"]) < statistics.median(counts["random"]), counts


def test_recordings_hold_no_secrets() -> None:
    files = sorted(RECORDINGS.glob("*.ndjson"))
    assert len(files) == 2, "the recorded Test Designer and Strategist calls are missing"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text
        assert "pytest-of-" not in text and "/home/" not in text  # no local paths or user names


async def test_recorded_design_finds_the_refund_bug_sooner_than_random(workspace: Path) -> None:
    model = await rules_model(workspace)
    bob = BobClient(EventBus(), RUN, mode="replay", recordings_dir=RECORDINGS, replay_speed=1e9,
                    replay_max_gap=0.0)
    result = await DesignPipeline(bob, workspace, model=model).run()

    finished = [e.data for e in events(bob, "agent.finished")]
    assert sorted(f["agent"] for f in finished) == ["strategist", "test_designer"]
    assert all(f["recorded"] and f["ok"] for f in finished)
    assert bob.total_cost == 0.0  # replays are free
    assert result.scenarios, result.dropped
    assert all(check_scenario(model, s.steps) is None for s in result.scenarios)  # only engine-valid ones
    _check_ac(await measure(model, result))


@pytest.mark.bob
async def test_live_design_on_minishop(workspace: Path, tmp_path: Path) -> None:
    """Real Test Designer and Strategist calls (Understand and RULES are replayed). Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    model = await rules_model(workspace)
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    client = BobClient(EventBus(), RUN, mode="record" if record_dir else "live",
                       recordings_dir=Path(record_dir).resolve() if record_dir else tmp_path / "rec")
    result = await DesignPipeline(client, workspace, model=model).run()
    print(f"\ncoins used: {client.total_cost:.4f}")
    for s in result.scenarios:
        print(f"scenario {s.name!r} ({s.rule_id}): {[x.model_dump(exclude_defaults=True) for x in s.steps]}")
    print(f"dropped: {result.dropped}\nweights: {result.weights} notes: {result.weight_notes}")
    print(f"focus: {result.focus} reason: {result.reason}")
    assert result.scenarios, result.dropped
    _check_ac(await measure(model, result))
