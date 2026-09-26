"""Engine checks for the DESIGN phase's AI suggestions (02_ARCHITECTURE.md section 7.1).

The Test Designer's scenarios and the Strategist's weights are untrusted Bob output. Code decides what
reaches the search (CLAUDE.md rule 1):
- `check_scenario` accepts a scenario only if every step names a known action and actor, every param is
  declared and fits its spec (int range, choice, string values or pattern), every `ref` the step needs is
  captured by an *earlier* step (never by a sibling in a parallel group), and the length caps hold;
- `sanitize_weights` keeps only finite weights >= 0 for known actions, caps them at MAX_WEIGHT, and drops
  the whole set if it would leave no action to start a sequence with.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rook.engine.generator import DEFAULT_MAX_LEN
from rook.model.schema import Choice, IntRange, ParallelStep, RookModel, SequenceStep, Step, StringParam

MAX_SCENARIOS = 20
MAX_SCENARIO_STEPS = DEFAULT_MAX_LEN  # the prompt asks for 8 or fewer; the engine tolerates the generator max
MAX_PARALLEL_WIDTH = 4
MAX_STRING_PARAM = 200
MAX_WEIGHT = 10.0


def check_scenario(model: RookModel, steps: Sequence[SequenceStep]) -> str | None:
    """Why the scenario cannot run on `model`, or None if it is valid."""
    if not steps:
        return "it has no steps"
    if len(steps) > MAX_SCENARIO_STEPS:
        return f"it has {len(steps)} steps (the limit is {MAX_SCENARIO_STEPS})"
    actors = {a.name for a in model.actors}
    actions = {a.name: a for a in model.actions}
    captured: set[str] = set()
    for n, step in enumerate(steps, start=1):
        subs = step.parallel if isinstance(step, ParallelStep) else [step]
        if len(subs) > MAX_PARALLEL_WIDTH:
            return f"step {n}: a parallel group of {len(subs)} (the limit is {MAX_PARALLEL_WIDTH})"
        for sub in subs:
            problem = _check_step(sub, actions, actors, captured)
            if problem is not None:
                return f"step {n}: {problem}"
        # Captures count only after the whole group: a sibling never provides a ref.
        for sub in subs:
            captured.update(actions[sub.action].capture)
    return None


def _check_step(step: Step, actions: Mapping[str, Any], actors: set[str], captured: set[str]) -> str | None:
    action = actions.get(step.action)
    if action is None:
        return f"unknown action {_short(step.action)!r}"
    if step.actor is not None and step.actor not in actors:
        return f"unknown actor {_short(step.actor)!r}"
    missing = [v for v in action.requires if v not in captured]
    if missing:
        return f"{action.name} needs {', '.join(missing)}, which no earlier step captures"
    for name, value in step.params.items():
        spec = action.params.get(name)
        if spec is None:
            return f"{action.name} has no param {_short(name)!r}"
        problem = _check_param(spec, value)
        if problem is not None:
            return f"{action.name}.{name}: {problem}"
    return None


def _check_param(spec: IntRange | Choice | StringParam, value: Any) -> str | None:
    if isinstance(spec, IntRange):
        lo, hi = spec.int_range
        if type(value) is not int:
            return f"{_short(repr(value))} is not an integer"
        if not lo <= value <= hi:
            return f"{value} is outside [{lo}, {hi}]"
        return None
    if isinstance(spec, Choice):
        # Type-strict, so True never passes for 1 and 1.0 never passes for 1.
        if not any(type(value) is type(c) and value == c for c in spec.choice):
            return f"{_short(repr(value))} is not one of the choices"
        return None
    if not isinstance(value, str) or len(value) > MAX_STRING_PARAM:
        return f"{_short(repr(value))} is not a string of at most {MAX_STRING_PARAM} characters"
    if spec.string.values is not None:
        return None if value in spec.string.values else f"{_short(repr(value))} is not one of the values"
    assert spec.string.pattern is not None  # StringSpec has exactly one of the two
    if re.fullmatch(spec.string.pattern, value) is None:
        return f"{_short(repr(value))} does not match the param's pattern"
    return None


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


@dataclass
class Weights:
    """Sanitized strategist weights (action -> multiplier) and why any input was dropped or changed."""

    weights: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def sanitize_weights(model: RookModel, raw: Mapping[str, Any]) -> Weights:
    known = {a.name: a for a in model.actions}
    out: dict[str, float] = {}
    notes: list[str] = []
    for name in sorted(raw, key=str):
        value = raw[name]
        if name not in known:
            notes.append(f"unknown action {_short(str(name))!r} ignored")
            continue
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            notes.append(f"{name}: {_short(repr(value))} is not a finite number, ignored")
            continue
        if value < 0:
            notes.append(f"{name}: {value} is negative, ignored")
            continue
        if value > MAX_WEIGHT:
            notes.append(f"{name}: {value} capped at {MAX_WEIGHT}")
            value = MAX_WEIGHT
        out[name] = float(value)
    # The walk starts with an action that needs no ref: at least one of them must keep a weight > 0.
    starters = [a for a in model.actions if not a.requires]
    if out and not any(a.weight * out.get(a.name, 1.0) > 0 for a in starters):
        notes.append("the weights disable every action a sequence can start with; all weights ignored")
        out = {}
    return Weights(out, notes)
