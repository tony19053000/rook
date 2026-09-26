"""The Coordinator: Bob suggests the next step at a branch point; the rails decide (02_ARCHITECTURE.md §4).

Bob never decides pass or fail. Its choice is used only if `rails.enforce` accepts it; on any error,
an invalid choice or a spent budget, the deterministic default is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.schemas import CoordinatorDecision
from rook.core import rails
from rook.core.events import Log
from rook.core.rails import Branch, RunState, Step

_REQUEST_MAX = 500
_NOTE_MAX = 200
_NOTES_MAX = 5


@dataclass(frozen=True)
class CoordinatorChoice:
    step: Step
    reason: str
    source: Literal["coordinator", "default"]  # "coordinator" only when Bob's proposal passed the rails
    proposed: str | None  # what Bob proposed (None when Bob was not asked or failed)
    allowed: tuple[Step, ...]


def state_summary(
    state: RunState, branch: Branch, agent: str | None, request: str | None, notes: list[str] | None
) -> dict[str, Any]:
    """Deterministic (no timestamps) so replayed recordings match the prompt key."""
    summary: dict[str, Any] = {"branch": branch, **state.summary()}
    if agent is not None:
        summary["failed_agent"] = agent
        summary["retries_used"] = state.retries_used(agent)
        summary["max_retries"] = rails.MAX_RETRIES
    if request:
        summary["user_request"] = request[:_REQUEST_MAX]
    if notes:
        summary["notes"] = [n[:_NOTE_MAX] for n in notes[-_NOTES_MAX:]]
    return summary


class Coordinator:
    def __init__(self, client: AgentCaller, workspace: str | os.PathLike[str]) -> None:
        self.client = client
        self.workspace = workspace

    async def decide(
        self,
        state: RunState,
        branch: Branch,
        *,
        agent: str | None = None,
        request: str | None = None,
        notes: list[str] | None = None,
    ) -> CoordinatorChoice:
        allowed = tuple(rails.allowed_steps(state, branch, agent))
        default = rails.default_step(state, branch, agent)

        def fallback(reason: str, proposed: str | None = None) -> CoordinatorChoice:
            return CoordinatorChoice(step=default, reason=reason, source="default", proposed=proposed,
                                     allowed=allowed)

        if not state.bob_allowed():
            await self._log("info", f"Coordinator not called: the coin budget is spent; using {default!r}")
            return fallback("the coin budget is spent")
        try:
            result = await call_agent(
                self.client, "coordinator", self.workspace,
                state_summary=state_summary(state, branch, agent, request, notes),
                allowed_steps=list(allowed),
            )
        except BOB_FAILURES as exc:
            await self._log("warn", f"Coordinator failed ({type(exc).__name__}); using {default!r}")
            return fallback("the coordinator failed")
        decision = result.output
        assert isinstance(decision, CoordinatorDecision)
        verdict = rails.enforce(state, branch, decision.next, agent)
        if not verdict.accepted:
            await self._log("warn", f"Coordinator chose {decision.next[:40]!r}, blocked by the rails "
                                    f"({verdict.reason}); using {verdict.step!r}")
            return fallback(verdict.reason, decision.next)
        return CoordinatorChoice(step=verdict.step, reason=decision.reason, source="coordinator",
                                 proposed=decision.next, allowed=allowed)

    async def _log(self, level: Literal["info", "warn", "error"], text: str) -> None:
        await self.client.bus.publish(self.client.run_id, "log", Log(level=level, text=text))
