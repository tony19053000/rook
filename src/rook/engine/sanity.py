"""Rule sanity checks: the engine decides whether a proposed rule can be used (02 section 4, RULES;
section 16: "a rule that doesn't hold on a fresh app is rejected automatically").

Two checks, both deterministic code (CLAUDE.md rule 1; the Rule Critic only judges meaning):
1. static: the check parses with the safe evaluator (model/expr.py) and references only the model's
   state readers, their declared fields, and the `response` object (`status`, `json`); a response rule's
   `when` names a known action and actor.
2. fresh app: the smallest setup that exercises the rule is run on the sandboxed app (fresh actors, a
   fresh var pool, and only the actions that *create* the entities it needs), then the rule is judged
   by the Judge itself, exactly as the search will judge it:
   - a scoped state rule must hold on a freshly created entity of its scope;
   - a global state rule must hold over the freshly created entities;
   - a response rule's `when` action is sent once as its actor, and the rule's own check decides. The
     HTTP status alone never fails a rule: `response.status in (401, 403)` holds on a 403.
   A rule that could not be exercised at all (its entities could not be created) is rejected too: the
   search could never check it either.

Note: a response rule is judged on a single request, so an app that breaks it on the very first
request (a one-step bug) gets the rule rejected with a reason that says so; the human can still add it.
"""

from __future__ import annotations

import ast
import json
import random
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from rook.core.events import redact_text
from rook.engine.dryrun import TRIES_PER_ACTION
from rook.engine.executor import EgressError, Executor, SequenceContext, StepResult
from rook.engine.judge import Judge
from rook.model.expr import ExprError, compile_expr
from rook.model.schema import Action, RookModel, Rule, Step

SANITY_SEEDS = 3
RESPONSE_FIELDS = frozenset({"status", "json"})
_EXCERPT = 300


@dataclass(frozen=True, slots=True)
class SanityResult:
    rule_id: str
    ok: bool
    stage: Literal["static", "fresh"]
    reason: str


class _NotExercised(Exception):
    """The rule's entities or request could not be produced on this seed."""


# --- 1. static check ---


def _references(node: ast.AST, bound: Mapping[str, str | None]) -> Iterator[tuple[str, str | None, str | None]]:
    """Yield (name, key, reader) for every free name in the expression.

    `key` is the attribute or constant subscript read directly on that name (None if none). For a
    comprehension variable that iterates directly over a reader list, `reader` is that reader's name and
    the yielded name is the variable; free names have `reader=None`.
    """
    if isinstance(node, ast.GeneratorExp | ast.ListComp):
        gen = node.generators[0]
        yield from _references(gen.iter, bound)
        source = gen.iter.id if isinstance(gen.iter, ast.Name) and gen.iter.id not in bound else None
        assert isinstance(gen.target, ast.Name)  # guaranteed by the safe evaluator's validator
        inner = {**bound, gen.target.id: source}
        for cond in gen.ifs:
            yield from _references(cond, inner)
        yield from _references(node.elt, inner)
        return
    if isinstance(node, ast.Attribute | ast.Subscript) and isinstance(node.value, ast.Name):
        key: str | None = None
        if isinstance(node, ast.Attribute):
            key = node.attr
        elif isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            key = node.slice.value
        else:
            yield from _references(node.slice, bound)
        name = node.value.id
        if name in bound:
            reader = bound[name]
            if reader is not None and key is not None:
                yield name, key, reader
        else:
            yield name, key, None
        return
    if isinstance(node, ast.Name):
        if node.id not in bound:
            yield node.id, None, None
        return
    if isinstance(node, ast.Call):
        for arg in node.args:
            yield from _references(arg, bound)
        return
    for child in ast.iter_child_nodes(node):
        yield from _references(child, bound)


def static_check(model: RookModel, rule: Rule) -> str | None:
    """Why `rule` cannot be used with `model` (parse errors, unknown names or fields), or None if it can."""
    readers = {r.name: r for r in model.state}
    actions = {a.name for a in model.actions}
    actors = {a.name for a in model.actors}
    if rule.scope != "global" and rule.scope not in readers:
        return f"its scope {rule.scope!r} is not a state reader or 'global'"
    if rule.when is not None:
        if rule.when.action not in actions:
            return f"its `when` names an unknown action {rule.when.action!r}"
        if rule.when.actor is not None and rule.when.actor not in actors:
            return f"its `when` names an unknown actor {rule.when.actor!r}"
    if rule.kind == "response":
        fields: dict[str, frozenset[str] | None] = {"response": RESPONSE_FIELDS}
    elif rule.scope == "global":
        if not readers:
            return "it is a global state rule, but the model has no state readers"
        fields = {name: None for name in readers}  # each reader is a list of entities
    else:
        fields = {rule.scope: frozenset(readers[rule.scope].fields)}
    try:
        compiled = compile_expr(rule.check)
    except ExprError as exc:
        return f"its check does not parse with the safe evaluator: {exc}"
    for name, key, reader in _references(compiled.tree.body, {}):
        if reader is not None:
            if key not in readers[reader].fields:
                return f"its check reads {name}.{key}, but {reader!r} has no field {key!r}"
            continue
        if name not in fields:
            known = ", ".join(sorted(fields))
            return f"its check uses the unknown name {name!r} (this rule can use: {known})"
        allowed = fields[name]
        if key is None:
            continue
        if allowed is None:
            return (f"its check reads {name}.{key}, but in a global rule {name!r} is the list of every "
                    f"{name}; iterate over it, e.g. all(x.{key} ... for x in {name})")
        if key not in allowed:
            return f"its check reads {name}.{key}, but {name!r} has no field {key!r}"
    return None


# --- 2. fresh-app check ---


def producers(model: RookModel, needed: list[str]) -> list[Action]:
    """The actions that create the vars in `needed` (and what they need), producers first.

    For each var, the first action in model order that captures it is used. Raises _NotExercised if a
    var is captured by no action.
    """
    by_var: dict[str, Action] = {}
    for action in model.actions:
        for var in action.capture:
            by_var.setdefault(var, action)
    chosen: list[Action] = []
    visiting: set[str] = set()

    def need(var: str) -> None:
        action = by_var.get(var)
        if action is None:
            raise _NotExercised(f"no action captures {var!r}")
        if action in chosen or var in visiting:
            return
        visiting.add(var)
        for required in action.requires:
            need(required)
        if action not in chosen:
            chosen.append(action)

    for var in needed:
        need(var)
    return chosen


def _excerpt(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    if len(text) > _EXCERPT:
        text = text[:_EXCERPT] + "..."
    return redact_text(text)


async def _create(executor: Executor, ctx: SequenceContext, chain: list[Action], rng: random.Random) -> None:
    for action in chain:
        detail = ""
        for _ in range(TRIES_PER_ACTION):
            result = await executor.run_step(ctx, Step(action=action.name), rng)
            assert isinstance(result, StepResult)
            if result.ok and all(ctx.pool.get(var) for var in action.capture):
                break
            detail = (f"HTTP {result.status}" if result.status is not None else result.error) or "no capture"
        else:
            raise _NotExercised(f"{action.name} did not succeed ({redact_text(detail)})")


async def _check_state_rule(
    executor: Executor, model: RookModel, rule: Rule, judge: Judge, rng: random.Random
) -> SanityResult:
    ctx = executor.new_context()
    scoped = rule.scope != "global"
    readers = [r for r in model.state if r.name == rule.scope] if scoped else list(model.state)
    for reader in readers:  # one new entity per reader in scope (every reader for a global rule)
        await _create(executor, ctx, producers(model, [reader.each]), rng)
    states: dict[str, dict[Any, dict[str, Any]]] = {}
    for reader in readers:
        states.update(await executor.read_state(ctx, reader.name))
    if scoped and not states.get(rule.scope):
        errors = "; ".join(ctx.state_errors[:1]) or "nothing was read"
        raise _NotExercised(f"the new {rule.scope} could not be read ({redact_text(errors)})")
    if not scoped and not all(states.get(r.name) for r in readers):
        errors = "; ".join(ctx.state_errors[:1]) or "nothing was read"
        raise _NotExercised(f"the new entities could not be read ({redact_text(errors)})")
    violation = judge.check_state(states)
    if judge.rule_errors:
        return SanityResult(rule.id, False, "fresh",
                            f"its check fails to evaluate on a fresh app: {redact_text(judge.rule_errors[rule.id])}")
    if violation is not None:
        what = f"a new {rule.scope}" if scoped else "the new entities"
        return SanityResult(rule.id, False, "fresh",
                            f"it is already false on a fresh app: {what} gives {_excerpt(violation.observed)}, "
                            f"which fails `{rule.check}`")
    what = f"a new {rule.scope}" if scoped else "the new entities"
    return SanityResult(rule.id, True, "fresh", f"holds on {what} in a fresh app")


async def _check_response_rule(
    executor: Executor, model: RookModel, rule: Rule, judge: Judge, rng: random.Random
) -> SanityResult:
    assert rule.when is not None
    action = model.action(rule.when.action)
    ctx = executor.new_context()
    await _create(executor, ctx, producers(model, list(action.requires)), rng)
    result = await executor.run_step(ctx, Step(action=action.name, actor=rule.when.actor), rng)
    assert isinstance(result, StepResult)
    if result.status is None:
        raise _NotExercised(f"{action.name} got no response ({redact_text(result.error or 'error')})")
    actor = result.actor
    # Judged by the rule's own check, never by the status: an expected 403 holds.
    violation = judge.check_response(result)
    where = f"{action.name} as {actor} -> HTTP {result.status}"
    if judge.rule_errors:
        return SanityResult(rule.id, False, "fresh",
                            f"its check fails to evaluate on a fresh app ({where}): "
                            f"{redact_text(judge.rule_errors[rule.id])}")
    if violation is not None:
        return SanityResult(rule.id, False, "fresh",
                            f"it is already false on a fresh app: {where} with body "
                            f"{_excerpt(result.response_json)} fails `{rule.check}` (either the rule is "
                            f"wrong or the app breaks it on the first request)")
    return SanityResult(rule.id, True, "fresh", f"holds on a fresh app ({where})")


async def fresh_check(
    model: RookModel, rule: Rule, executor: Executor, *, seeds: int = SANITY_SEEDS
) -> SanityResult:
    """Run the rule's smallest setup on the app and judge it (see the module doc). Deterministic seeds."""
    single = model.model_copy(update={"rules": [rule.model_copy(update={"status": "approved"})]})
    reason = ""
    for seed in range(seeds):
        rng = random.Random(f"sanity:{rule.id}:{seed}")
        judge = Judge(single)
        try:
            if rule.kind == "response":
                return await _check_response_rule(executor, model, rule, judge, rng)
            return await _check_state_rule(executor, model, rule, judge, rng)
        except _NotExercised as exc:
            reason = str(exc)
        except EgressError:
            return SanityResult(rule.id, False, "fresh",
                                "refused by the egress guard: a request would leave the sandboxed app")
    return SanityResult(rule.id, False, "fresh", f"it could not be exercised on a fresh app: {reason}")


async def sanity_check(
    model: RookModel,
    rules: list[Rule],
    base_url: str,
    *,
    env: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    seeds: int = SANITY_SEEDS,
) -> list[SanityResult]:
    """Check every rule, statically and then on the running app (only if the static check passed)."""
    results: list[SanityResult] = []
    async with Executor(model, base_url, transport=transport, env=dict(env or {})) as executor:
        for rule in rules:
            problem = static_check(model, rule)
            if problem is not None:
                results.append(SanityResult(rule.id, False, "static", problem))
                continue
            results.append(await fresh_check(model, rule, executor, seeds=seeds))
    return results
