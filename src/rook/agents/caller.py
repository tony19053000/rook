"""The small interface the agent pipelines need from BobClient, and a helper to call one agent."""

from __future__ import annotations

import os
from typing import Any, Protocol

from pydantic import BaseModel

from rook.agents.bob import AgentResult, BobError
from rook.agents.prompts import render_prompt
from rook.agents.recorder import RecordingMissing
from rook.agents.registry import get
from rook.core.events import EventBus

# Ways a Bob call can fail at run time (bad status/output/timeout, no recording in replay, bob not found).
# Callers fall back to deterministic behaviour on these; anything else is a bug and propagates.
BOB_FAILURES: tuple[type[Exception], ...] = (BobError, RecordingMissing, OSError)


class AgentCaller(Protocol):
    """Implemented by `BobClient` (and by fakes in tests)."""

    bus: EventBus
    run_id: str

    async def call(
        self,
        agent_id: str,
        slug: str,
        prompt: str,
        workspace: str | os.PathLike[str],
        output_model: type[BaseModel],
        max_turns: int = ...,
        max_cost: float | None = ...,
    ) -> AgentResult: ...


async def call_agent(
    client: AgentCaller, agent_id: str, workspace: str | os.PathLike[str], **inputs: Any
) -> AgentResult:
    """Render the agent's prompt from `inputs` and call it with its registered mode, schema and turn cap."""
    spec = get(agent_id)
    prompt = render_prompt(agent_id, **inputs)
    return await client.call(agent_id, spec.slug, prompt, workspace, spec.output_model, max_turns=spec.max_turns)
