"""Seeded sequence generator (02_ARCHITECTURE.md section 7.1).

`Generator.sequence(i)` is a pure function of `(seed, i)`: designed scenarios come first, then a
random walk over the actions whose `requires` can be met by vars captured earlier in the same
sequence, with mutated scenarios mixed in about 20% of the time. Every generated step has its actor
and params fixed (int params hit an edge value 30% of the time). Only `ref` picks are left to run
time, because they choose among values the app returns.
"""

import random
from collections.abc import Mapping, Sequence

from rook.engine.executor import draw_params
from rook.model.schema import Action, ParallelStep, RookModel, SequenceStep, Step

DEFAULT_MAX_LEN = 12
MUTATION_RATE = 0.2
PARALLEL_PROB = 0.1
PARALLEL_WIDTH = 2


class Generator:
    """`weights` are the strategist's per-action multipliers (on top of `action.weight`); an action
    whose combined weight is 0 is never picked. `scenarios` are the Test Designer's sequences."""

    def __init__(
        self,
        model: RookModel,
        seed: int | str,
        *,
        weights: Mapping[str, float] | None = None,
        max_len: int = DEFAULT_MAX_LEN,
        scenarios: Sequence[Sequence[SequenceStep]] | None = None,
        parallel_prob: float = PARALLEL_PROB,
    ) -> None:
        if max_len < 1:
            raise ValueError("max_len must be at least 1")
        if not 0.0 <= parallel_prob <= 1.0:
            raise ValueError("parallel_prob must be between 0 and 1")
        self.model = model
        self.seed = seed
        self.max_len = max_len
        self.parallel_prob = parallel_prob
        weights = weights or {}
        unknown = set(weights) - {a.name for a in model.actions}
        if unknown:
            raise ValueError(f"weights name unknown actions: {sorted(unknown)}")
        bad = sorted(name for name, w in weights.items() if not w >= 0)  # also rejects NaN
        if bad:
            raise ValueError(f"weights must be >= 0: {bad}")
        self._by_name = {a.name: a for a in model.actions}
        self._weights = {a.name: a.weight * weights.get(a.name, 1.0) for a in model.actions}
        self._actions = [a for a in model.actions if self._weights[a.name] > 0]
        self.scenarios: list[list[SequenceStep]] = []
        for scenario in scenarios or []:
            steps = list(scenario)
            for step in steps:
                model.check_step(step)
            if steps:
                self.scenarios.append([s.model_copy(deep=True) for s in steps])

    def sequence(self, i: int) -> list[SequenceStep]:
        """The i-th sequence (deterministic for `(seed, i)`)."""
        if i < len(self.scenarios):
            return [s.model_copy(deep=True) for s in self.scenarios[i]]
        rng = random.Random(f"{self.seed}:{i}")
        if self.scenarios and rng.random() < MUTATION_RATE:
            mutated = self._mutate(rng)
            if mutated:
                return mutated
        return self._walk(rng)

    # --- random walk ---

    def _pick(self, rng: random.Random, available: set[str]) -> Action | None:
        candidates = [a for a in self._actions if all(v in available for v in a.requires)]
        if not candidates:
            return None
        return rng.choices(candidates, weights=[self._weights[a.name] for a in candidates])[0]

    def _sub(self, action: Action, rng: random.Random) -> Step:
        return Step(action=action.name, actor=action.actor, params=draw_params(action, rng))

    def _step(self, action: Action, rng: random.Random) -> SequenceStep:
        # Sometimes a parallel pair of the same entity-touching action (the runner pins both to one
        # entity), to catch races such as two buys of the last item.
        if action.requires and self.parallel_prob > 0 and rng.random() < self.parallel_prob:
            return ParallelStep(parallel=[self._sub(action, rng) for _ in range(PARALLEL_WIDTH)])
        return self._sub(action, rng)

    def _walk(self, rng: random.Random) -> list[SequenceStep]:
        length = rng.randint(1, self.max_len)
        available: set[str] = set()
        steps: list[SequenceStep] = []
        while len(steps) < length:
            action = self._pick(rng, available)
            if action is None:
                break
            steps.append(self._step(action, rng))
            available.update(action.capture)
        return steps

    # --- scenario mutation ---

    def _mutate(self, rng: random.Random) -> list[SequenceStep]:
        steps = [s.model_copy(deep=True) for s in rng.choice(self.scenarios)]
        op = rng.choice(("insert", "delete", "duplicate", "jitter"))
        pos = rng.randrange(len(steps))
        if op == "insert":
            action = self._pick(rng, self._available_before(steps, pos))
            if action is not None:
                steps.insert(pos, self._step(action, rng))
        elif op == "delete" and len(steps) > 1:
            del steps[pos]
        elif op == "duplicate":
            steps.insert(pos, steps[pos].model_copy(deep=True))
        elif op == "jitter":
            for sub in _substeps(steps[pos]):
                sub.params = draw_params(self._by_name[sub.action], rng)
        return self._repair(steps)[: self.max_len]

    def _available_before(self, steps: list[SequenceStep], pos: int) -> set[str]:
        available: set[str] = set()
        for step in steps[:pos]:
            for sub in _substeps(step):
                available.update(self._by_name[sub.action].capture)
        return available

    def _repair(self, steps: list[SequenceStep]) -> list[SequenceStep]:
        """Drop steps whose `requires` can no longer be met by earlier captures."""
        available: set[str] = set()
        kept: list[SequenceStep] = []
        for step in steps:
            actions = [self._by_name[sub.action] for sub in _substeps(step)]
            if all(v in available for a in actions for v in a.requires):
                kept.append(step)
                for a in actions:
                    available.update(a.capture)
        return kept


def _substeps(step: SequenceStep) -> list[Step]:
    return step.parallel if isinstance(step, ParallelStep) else [step]
