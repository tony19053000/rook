"""The DESIGN phase: Test Designer + Strategist, in parallel (02_ARCHITECTURE.md section 4).

Bob suggests and code decides (CLAUDE.md rule 1):
- the Test Designer proposes scenarios (short step sequences) for the approved rules. The engine
  (engine/scenarios.py) checks each one against the model; invalid ones are dropped with a logged reason,
  valid ones go first in the runner's queue (`DesignResult.generator`);
- the Strategist proposes per-action weights. The engine sanitizes them (finite, >= 0, capped, known
  actions only) and the generator multiplies them into `action.weight`.

Neither agent decides whether a rule breaks: the scenarios and weights only steer the search. Both are
untrusted data, used only after validation, never executed. A failed agent leaves the search as it would
be without it (DESIGN is skippable, core/rails.py).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.schemas import StrategistOutput, TestDesignerOutput
from rook.agents.understand import check_not_rook_repo
from rook.core.events import Log, RunPhase, redact_text
from rook.engine.generator import Generator
from rook.engine.scenarios import MAX_SCENARIOS, check_scenario, sanitize_weights
from rook.model.schema import RookModel, Rule, SequenceStep

NO_SEARCH_YET: dict[str, Any] = {"sequences_run": 0, "note": "the search has not run yet"}
_NAME_MAX = 80


@dataclass
class DesignedScenario:
    name: str  # cleaned for display (redacted, one line, capped)
    rule_id: str
    steps: list[SequenceStep]


@dataclass
class DesignResult:
    scenarios: list[DesignedScenario] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (scenario name, the engine's reason)
    weights: dict[str, float] = field(default_factory=dict)
    weight_notes: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    reason: str = ""

    def generator(self, model: RookModel, seed: int | str, **kwargs: Any) -> Generator:
        """The search generator: the designed scenarios first, then a walk weighted by the strategist."""
        return Generator(model, seed, weights=self.weights, scenarios=[s.steps for s in self.scenarios],
                         scenario_labels=[f"{s.name} (rule {s.rule_id})" for s in self.scenarios], **kwargs)


def _clean(text: str) -> str:
    text = " ".join(redact_text(text).split())
    return text if len(text) <= _NAME_MAX else text[: _NAME_MAX - 3] + "..."


def design_inputs(model: RookModel) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The approved rules and the actions (with the actor names a step may use), as prompt data."""
    rules = [r.model_dump(mode="json", by_alias=True, exclude_none=True) for r in _approved(model)]
    actions = {
        "actors": [a.name for a in model.actors],
        "actions": [a.model_dump(mode="json", by_alias=True, exclude_none=True) for a in model.actions],
    }
    return rules, actions


def _approved(model: RookModel) -> list[Rule]:
    return [r for r in model.rules if r.status == "approved"]


class DesignPipeline:
    def __init__(
        self,
        client: AgentCaller,
        workspace: str | os.PathLike[str],
        *,
        model: RookModel,
        search_stats: Mapping[str, Any] | None = None,
    ) -> None:
        """`model` holds the approved rules; `search_stats` are the engine's numbers so far, if any."""
        self.client = client
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")
        check_not_rook_repo(self.workspace)
        self.model = model
        self.search_stats = dict(search_stats) if search_stats is not None else dict(NO_SEARCH_YET)

    async def run(self) -> DesignResult:
        await self._publish("run.phase", RunPhase(phase="DESIGN"))
        result = DesignResult()
        if not _approved(self.model):
            await self._log("warn", "No approved rules: nothing to design for; the search runs unguided")
            return result
        rules, actions = design_inputs(self.model)
        # Both calls run at once; a TaskGroup also cancels the other call if one raises a bug.
        async with asyncio.TaskGroup() as group:
            designer = group.create_task(self._designer(rules, actions))
            strategist = group.create_task(self._strategist(rules, actions))
        await self._apply_scenarios(result, designer.result())
        await self._apply_weights(result, strategist.result())
        return result

    # agents

    async def _designer(self, rules: list[dict[str, Any]], actions: dict[str, Any]) -> TestDesignerOutput | None:
        try:
            result = await call_agent(self.client, "test_designer", self.workspace, rules=rules, actions=actions)
        except BOB_FAILURES as exc:
            await self._log("warn", f"The Test Designer failed; the search runs without designed scenarios: "
                                    f"{_first_line(exc)}")
            return None
        assert isinstance(result.output, TestDesignerOutput)
        return result.output

    async def _strategist(self, rules: list[dict[str, Any]], actions: dict[str, Any]) -> StrategistOutput | None:
        try:
            result = await call_agent(self.client, "strategist", self.workspace, rules=rules, actions=actions,
                                      search_stats=self.search_stats)
        except BOB_FAILURES as exc:
            await self._log("warn", f"The Strategist failed; the search uses the model's own weights: "
                                    f"{_first_line(exc)}")
            return None
        assert isinstance(result.output, StrategistOutput)
        return result.output

    # engine decisions

    async def _apply_scenarios(self, result: DesignResult, output: TestDesignerOutput | None) -> None:
        if output is None:
            return
        rule_ids = {r.id for r in _approved(self.model)}
        for n, scenario in enumerate(output.scenarios):
            name = _clean(scenario.name)
            if n >= MAX_SCENARIOS:
                reason = f"over the limit of {MAX_SCENARIOS} scenarios"
            elif scenario.rule_id not in rule_ids:
                reason = f"rule {_clean(scenario.rule_id)!r} is not an approved rule"
            else:
                reason = check_scenario(self.model, scenario.steps) or ""
            if reason:
                result.dropped.append((name, reason))
                await self._log("warn", f"Designed scenario {name!r} dropped by the engine: {reason}")
                continue
            steps = [s.model_copy(deep=True) for s in scenario.steps]
            result.scenarios.append(DesignedScenario(name, scenario.rule_id, steps))
        await self._log("info", f"{len(result.scenarios)} designed scenarios accepted, {len(result.dropped)} "
                                "dropped; they run before the random search")

    async def _apply_weights(self, result: DesignResult, output: StrategistOutput | None) -> None:
        if output is None:
            return
        cleaned = sanitize_weights(self.model, output.weights)
        result.weights, result.weight_notes = cleaned.weights, cleaned.notes
        for note in cleaned.notes:
            await self._log("warn", f"Strategist weight {note}")
        rule_ids = {r.id for r in _approved(self.model)}
        result.focus = [r for r in dict.fromkeys(output.focus) if r in rule_ids]
        result.reason = _clean(output.reason)
        shown = ", ".join(f"{k}={v:g}" for k, v in sorted(result.weights.items())) or "none (model weights)"
        focus = ", ".join(result.focus) or "no rule in particular"
        await self._log("info", f"Strategist (a guess): focus on {focus}; weights {shown}. {result.reason}")

    # events

    async def _log(self, level: str, text: str) -> None:
        await self._publish("log", Log(level=level, text=text))  # type: ignore[arg-type]

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.client.bus.publish(self.client.run_id, event_type, data)


def _first_line(exc: Exception) -> str:
    text = redact_text(str(exc))
    return text.splitlines()[0] if text else type(exc).__name__
