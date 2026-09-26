"""ROOK-007: the seeded sequence generator (02 section 7.1)."""

import random
from collections import Counter
from pathlib import Path

import pytest

from rook.engine.executor import EDGE_BIAS, draw_params
from rook.engine.generator import DEFAULT_MAX_LEN, MUTATION_RATE, Generator
from rook.model.loader import load_model
from rook.model.schema import ParallelStep, SequenceStep, Step

MODEL = load_model(Path(__file__).parents[1] / "fixtures" / "minishop" / "rook.yaml")
ACTIONS = {a.name: a for a in MODEL.actions}


def _subs(step: SequenceStep) -> list[Step]:
    return step.parallel if isinstance(step, ParallelStep) else [step]


def _dump(steps: list[SequenceStep]) -> list[dict]:
    return [s.model_dump() for s in steps]


def _requires_met(steps: list[SequenceStep]) -> bool:
    available: set[str] = set()
    for step in steps:
        actions = [ACTIONS[s.action] for s in _subs(step)]
        if not all(v in available for a in actions for v in a.requires):
            return False
        for a in actions:
            available.update(a.capture)
    return True


def test_same_seed_gives_identical_sequence_list() -> None:
    a = [_dump(Generator(MODEL, 42).sequence(i)) for i in range(500)]
    b = [_dump(Generator(MODEL, 42).sequence(i)) for i in range(500)]
    assert a == b
    # Order of generation does not matter: sequence(i) is a pure function of (seed, i).
    gen = Generator(MODEL, 42)
    assert [_dump(gen.sequence(i)) for i in reversed(range(500))] == list(reversed(a))


def test_different_seeds_give_different_sequences() -> None:
    a = [_dump(Generator(MODEL, 1).sequence(i)) for i in range(50)]
    b = [_dump(Generator(MODEL, 2).sequence(i)) for i in range(50)]
    assert a != b
    # Unlike Random(seed + i), (seed=1, i) and (seed=2, i-1) are unrelated streams.
    g1, g2 = Generator(MODEL, 1), Generator(MODEL, 2)
    same = sum(_dump(g1.sequence(i)) == _dump(g2.sequence(i - 1)) for i in range(1, 51))
    assert same < 5


def test_walk_respects_requires_length_and_actors() -> None:
    gen = Generator(MODEL, 7)
    lengths = Counter()
    for i in range(2000):
        steps = gen.sequence(i)
        assert 1 <= len(steps) <= DEFAULT_MAX_LEN
        assert _requires_met(steps)
        lengths[len(steps)] += 1
        for step in steps:
            for sub in _subs(step):
                assert sub.actor == ACTIONS[sub.action].actor
    assert lengths[1] > 0 and lengths[DEFAULT_MAX_LEN] > 0


def test_first_step_never_needs_a_captured_var() -> None:
    gen = Generator(MODEL, "x")
    for i in range(300):
        first = gen.sequence(i)[0]
        assert isinstance(first, Step) and ACTIONS[first.action].requires == []


def test_max_len_is_respected_and_validated() -> None:
    gen = Generator(MODEL, 3, max_len=3)
    assert all(len(gen.sequence(i)) <= 3 for i in range(300))
    with pytest.raises(ValueError):
        Generator(MODEL, 3, max_len=0)


def test_params_are_drawn_within_range_with_edge_bias() -> None:
    gen = Generator(MODEL, 11)
    amounts: list[int] = []
    for i in range(3000):
        for step in gen.sequence(i):
            for sub in _subs(step):
                spec_names = set(ACTIONS[sub.action].params)
                assert set(sub.params) == spec_names
                if sub.action == "refund":
                    amounts.append(sub.params["amount"])
                if sub.action == "create_product":
                    assert 1 <= sub.params["price"] <= 500 and 0 <= sub.params["stock"] <= 5
    assert amounts and all(1 <= a <= 500 for a in amounts)
    # Edges are [1, 50, 60, 100]; a uniform draw hits them 4/500 of the time, the bias ~30%.
    edge_share = sum(a in (1, 50, 60, 100) for a in amounts) / len(amounts)
    assert 0.22 < edge_share < 0.40


def test_draw_params_edge_bias_directly() -> None:
    rng = random.Random(0)
    refund = ACTIONS["refund"]
    draws = [draw_params(refund, rng)["amount"] for _ in range(10_000)]
    share = sum(d in (1, 50, 60, 100) for d in draws) / len(draws)
    assert abs(share - (EDGE_BIAS + (1 - EDGE_BIAS) * 4 / 500)) < 0.02


def test_weights_bias_the_walk_and_zero_excludes() -> None:
    def counts(gen: Generator) -> Counter:
        c: Counter = Counter()
        for i in range(1500):
            for step in gen.sequence(i):
                for sub in _subs(step):
                    c[sub.action] += 1
        return c

    base = counts(Generator(MODEL, 5))
    heavy = counts(Generator(MODEL, 5, weights={"admin_export": 10.0}))
    assert heavy["admin_export"] > 3 * base["admin_export"]
    none = counts(Generator(MODEL, 5, weights={"admin_export": 0}))
    assert none["admin_export"] == 0 and none["buy"] > 0


def test_bad_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        Generator(MODEL, 1, weights={"nope": 1.0})
    with pytest.raises(ValueError, match=">= 0"):
        Generator(MODEL, 1, weights={"buy": -1.0})
    with pytest.raises(ValueError, match=">= 0"):
        Generator(MODEL, 1, weights={"buy": float("nan")})


def test_all_zero_weights_give_empty_sequences() -> None:
    gen = Generator(MODEL, 1, weights={a.name: 0 for a in MODEL.actions})
    assert gen.sequence(0) == [] and gen.sequence(99) == []


def test_parallel_steps_group_actions_touching_the_same_entity() -> None:
    gen = Generator(MODEL, 9, parallel_prob=1.0)
    seen = 0
    pairs: Counter[tuple[str, ...]] = Counter()
    for i in range(200):
        for step in gen.sequence(i):
            action = ACTIONS[_subs(step)[0].action]
            if action.requires:
                assert isinstance(step, ParallelStep)
                for sub in step.parallel:  # every partner touches an entity the first one touches
                    assert set(ACTIONS[sub.action].requires) & set(action.requires)
                pairs[tuple(s.action for s in step.parallel)] += 1
                seen += 1
            else:
                assert isinstance(step, Step)
    assert seen > 0
    assert all(_requires_met(gen.sequence(i)) for i in range(200))
    assert pairs[("buy", "buy")] > 0  # buy is the only action touching a product
    assert all(a == "buy" for pair in pairs for a in pair if "buy" in pair)
    assert any(len(set(pair)) == 2 for pair in pairs)  # e.g. cancel || ship on one order
    none = Generator(MODEL, 9, parallel_prob=0.0)
    assert not any(isinstance(s, ParallelStep) for i in range(300) for s in none.sequence(i))
    with pytest.raises(ValueError):
        Generator(MODEL, 9, parallel_prob=1.5)


SCENARIO = [
    Step(action="create_product", params={"price": 100, "stock": 5}),
    Step(action="buy", params={"quantity": 1}),
    Step(action="refund", params={"amount": 60}),
    Step(action="refund", params={"amount": 50}),
]


def test_designed_scenarios_run_first_then_mutations_mix_in() -> None:
    other = [Step(action="admin_export")]
    gen = Generator(MODEL, 4, scenarios=[SCENARIO, other])
    assert _dump(gen.sequence(0)) == _dump(SCENARIO)
    assert _dump(gen.sequence(1)) == _dump(other)
    # The generator hands out copies: callers can't corrupt the stored scenario.
    gen.sequence(0)[0].params["price"] = 1
    assert gen.sequence(0)[0].params["price"] == 100

    total = 3000
    mutated = 0
    for i in range(2, total + 2):
        steps = gen.sequence(i)
        assert _requires_met(steps) and 1 <= len(steps) <= DEFAULT_MAX_LEN
        if (
            len(steps) >= 3
            and [s.action for s in _flat(steps)][:2] == ["create_product", "buy"]
            and any(s.action == "refund" for s in _flat(steps))
        ):
            mutated += 1
    # About 20% are mutations; half of those come from SCENARIO. Random walks rarely look like this.
    assert 0.5 * MUTATION_RATE * total * 0.5 < mutated < 1.6 * MUTATION_RATE * total


def _flat(steps: list[SequenceStep]) -> list[Step]:
    return [s for step in steps for s in _subs(step)]


def test_mutation_repairs_broken_requires() -> None:
    # Deleting create_product or buy leaves refunds without an order: repair must drop them.
    gen = Generator(MODEL, 12, scenarios=[SCENARIO])
    for i in range(1, 2000):
        assert _requires_met(gen.sequence(i))


def test_unknown_scenario_action_is_rejected() -> None:
    with pytest.raises(ValueError):
        Generator(MODEL, 1, scenarios=[[Step(action="nope")]])
    # Empty scenarios are ignored.
    assert Generator(MODEL, 1, scenarios=[[]]).scenarios == []
