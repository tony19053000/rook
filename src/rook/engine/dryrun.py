"""Dry-run: the engine sends every mapped action to the sandboxed app and decides whether it works
(02 section 4, MAP; section 16). Bob never decides this (CLAUDE.md rule 1).

Actions run in dependency order (producers of a captured var before the actions that require it), in
one sequence per seed. A failing action is retried with new param draws, and a few seeds are tried, so a
random draw (e.g. a product with zero stock) does not fail a correct action. An action passes if it
returned a status below 400 at least once. A state reader passes if it read at least one entity without
an error and every field it declares was found.

Failure details are built only from the action's template, the status and the response body (no ids,
tokens or fresh values), so the same app gives the same feedback text for the Mapper.
"""

import json
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from rook.core.events import redact_text
from rook.engine.executor import EgressError, Executor, SequenceContext, StepResult
from rook.model.schema import Action, RookModel, Step

DRY_RUN_SEEDS = 5
TRIES_PER_ACTION = 3
_BODY_EXCERPT = 300
_EGRESS = "refused by the egress guard: the rendered request would leave the sandboxed app"


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class DryRunReport:
    actions: dict[str, Check] = field(default_factory=dict)
    readers: dict[str, Check] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in (*self.actions.values(), *self.readers.values()))

    @property
    def failed_actions(self) -> list[str]:
        return [name for name, c in self.actions.items() if not c.ok]

    @property
    def failed_readers(self) -> list[str]:
        return [name for name, c in self.readers.items() if not c.ok]

    def summary(self) -> str:
        good = sum(c.ok for c in self.actions.values())
        text = f"{good}/{len(self.actions)} actions dry-ran OK"
        if self.readers:
            text += f", {sum(c.ok for c in self.readers.values())}/{len(self.readers)} state readers OK"
        return text

    def failures(self) -> str:
        """One line per failed action or reader (deterministic; used as feedback for the Mapper)."""
        lines = [f"action {c.name}: {c.detail}" for c in self.actions.values() if not c.ok]
        lines += [f"state reader {c.name}: {c.detail}" for c in self.readers.values() if not c.ok]
        return "\n".join(lines)


def action_order(model: RookModel) -> list[Action]:
    """Actions whose `requires` are captured by earlier actions come first (stable, model order)."""
    remaining = list(model.actions)
    captured: set[str] = set()
    ordered: list[Action] = []
    while remaining:
        ready = [a for a in remaining if set(a.requires) <= captured]
        if not ready:  # nothing can satisfy the rest; run them anyway so each gets a clear failure
            ordered += remaining
            break
        for action in ready:
            ordered.append(action)
            captured.update(action.capture)
            remaining.remove(action)
    return ordered


def _body(value: Any) -> str:
    if value is None:
        return ""
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    if len(text) > _BODY_EXCERPT:
        text = text[:_BODY_EXCERPT] + "..."
    return redact_text(text)


def _failure(action: Action, result: StepResult) -> str:
    where = f"{action.request.method} {action.request.path}"
    if result.status is None:
        return f"{where} -> {redact_text(result.error or 'no response')}"
    detail = f"{where} -> HTTP {result.status}"
    if result.error and result.status < 400:
        return f"{detail}: {redact_text(result.error)}"
    body = _body(result.response_json)
    return f"{detail}: {body}" if body else detail


async def _run_action(
    executor: Executor, ctx: SequenceContext, action: Action, rng: random.Random
) -> tuple[bool, str]:
    detail = ""
    for _ in range(TRIES_PER_ACTION):
        try:
            result = await executor.run_step(ctx, Step(action=action.name), rng)
        except EgressError:
            return False, _EGRESS
        assert isinstance(result, StepResult)
        if result.ok:
            return True, f"HTTP {result.status}"
        detail = _failure(action, result)
        if result.error is not None and result.status is None and "no captured value" in result.error:
            break  # a new draw cannot help: nothing captured the var it requires
    return False, detail


async def _check_readers(
    executor: Executor, ctx: SequenceContext, model: RookModel, report: DryRunReport
) -> None:
    for reader in model.state:
        if report.readers.get(reader.name, Check(reader.name, False, "")).ok:
            continue
        if not ctx.pool.get(reader.each):
            report.readers[reader.name] = Check(
                reader.name, False, f"never read: no action captured {reader.each!r}")
            continue
        before = len(ctx.state_errors)
        try:
            states = await executor.read_state(ctx, reader.name)
        except EgressError:
            report.readers[reader.name] = Check(reader.name, False, _EGRESS)
            continue
        errors = ctx.state_errors[before:]
        entities = list(states.get(reader.name, {}).values())
        where = f"{reader.request.method} {reader.request.path}"
        if errors or not entities:
            reason = errors[0].rsplit(": ", 1)[-1] if errors else "no entity was read"
            report.readers[reader.name] = Check(reader.name, False, f"{where} -> {redact_text(reason)}")
            continue
        missing = sorted(f for f in reader.fields if all(e.get(f) is None for e in entities))
        if missing:
            paths = ", ".join(f"{f} ({reader.fields[f]})" for f in missing)
            report.readers[reader.name] = Check(
                reader.name, False, f"{where} -> fields not found in the response: {paths}")
            continue
        report.readers[reader.name] = Check(reader.name, True, f"read {len(entities)} entity(ies)")


async def dry_run(
    model: RookModel,
    base_url: str,
    *,
    env: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    seeds: int = DRY_RUN_SEEDS,
) -> DryRunReport:
    """Send each action (and read each state entity) against the running app; see the module doc."""
    report = DryRunReport()
    order = action_order(model)
    async with Executor(model, base_url, transport=transport, env=env) as executor:
        for seed in range(seeds):
            rng = random.Random(seed)
            ctx = executor.new_context()
            for action in order:
                ok, detail = await _run_action(executor, ctx, action, rng)
                previous = report.actions.get(action.name)
                if previous is None or not previous.ok:
                    report.actions[action.name] = Check(action.name, ok, detail)
            await _check_readers(executor, ctx, model, report)
            if report.ok:
                break
    # Report in model order, whatever order they ran in.
    report.actions = {a.name: report.actions[a.name] for a in model.actions}
    report.readers = {r.name: report.readers[r.name] for r in model.state if r.name in report.readers}
    return report
