"""ROOK-022: the Coordinator's choice is used only when the rails allow it. No real Bob is called."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from rook.agents.bob import AgentOutputError, AgentResult, BobClient
from rook.agents.coordinator import Coordinator, state_summary
from rook.agents.prompts import render_prompt
from rook.agents.recorder import Recorder, recording_key
from rook.agents.registry import get
from rook.core.events import Event, EventBus, now_ts
from rook.core.rails import RunState

RUN = "r_coord"


class FakeClient:
    """Stands in for BobClient: returns scripted outputs (or raises) and records every call."""

    def __init__(self, replies: list[dict[str, Any] | Exception]) -> None:
        self.bus = EventBus()
        self.run_id = RUN
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any,
                   output_model: type[BaseModel], max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        self.calls.append({"agent_id": agent_id, "slug": slug, "prompt": prompt, "max_turns": max_turns})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return AgentResult(output=output_model.model_validate(reply), text="", cost=0.02, recorded=False,
                           call_id="c_1")


def ev(seq: int, event_type: str, **data: Any) -> Event:
    return Event(seq=seq, ts=now_ts(), run_id=RUN, type=event_type, data=data)  # type: ignore[arg-type]


def state_at(phase: str, **kw: Any) -> RunState:
    state = RunState(**kw)
    state.observe(ev(1, "run.phase", phase=phase))
    return state


def logs(client: FakeClient | BobClient) -> list[str]:
    return [e.data["text"] for e in client.bus._channel(RUN).history if e.type == "log"]


async def test_allowed_choice_is_accepted(tmp_path: Path) -> None:
    client = FakeClient([{"next": "extend_search", "reason": "Refund paths are barely explored."}])
    choice = await Coordinator(client, tmp_path).decide(state_at("SEARCH"), "search_exhausted")
    assert choice.step == "extend_search" and choice.source == "coordinator"
    assert choice.reason == "Refund paths are barely explored."
    assert choice.allowed == ("extend_search", "report", "stop")
    call = client.calls[0]
    assert call["agent_id"] == "coordinator" and call["slug"] == "rook-coordinator"
    assert call["max_turns"] == get("coordinator").max_turns
    assert '"extend_search"' in call["prompt"] and '"search_exhausted"' in call["prompt"]


async def test_disallowed_choice_falls_back_to_default(tmp_path: Path) -> None:
    # Bob tries to ship an unverified fix: the rails refuse and the default is used.
    state = state_at("VERIFY")
    state.observe(ev(2, "violation.found", violation_id="v", rule_id="r", steps_count=3, observed={}))
    client = FakeClient([{"next": "ship", "reason": "Looks fine to me."}])
    choice = await Coordinator(client, tmp_path).decide(state, "verify_failed")
    assert choice.step == "diagnose" and choice.source == "default" and choice.proposed == "ship"
    assert "ship" not in choice.allowed
    assert any("blocked by the rails" in t for t in logs(client))


async def test_unknown_choice_falls_back(tmp_path: Path) -> None:
    client = FakeClient([{"next": "mark_verified", "reason": "x"}])
    choice = await Coordinator(client, tmp_path).decide(state_at("SEARCH"), "search_exhausted")
    assert choice.step == "report" and choice.source == "default"


async def test_fix_request_without_approval_is_blocked(tmp_path: Path) -> None:
    state = state_at("APPROVE_FIX")
    state.observe(ev(2, "violation.found", violation_id="v", rule_id="r", steps_count=3, observed={}))
    client = FakeClient([{"next": "fix", "reason": "The user asked for it in chat."}])
    choice = await Coordinator(client, tmp_path).decide(state, "user_request", request="just fix it")
    assert choice.step == "continue" and choice.source == "default"
    assert "not approved" in choice.reason


async def test_bob_failure_uses_default(tmp_path: Path) -> None:
    client = FakeClient([AgentOutputError("invalid output after 3 attempts")])
    choice = await Coordinator(client, tmp_path).decide(state_at("DESIGN"), "agent_failed", agent="strategist")
    assert choice.step == "skip" and choice.source == "default" and choice.proposed is None
    assert any("Coordinator failed" in t for t in logs(client))


async def test_budget_spent_skips_bob(tmp_path: Path) -> None:
    state = state_at("SEARCH")
    state.observe(ev(2, "cost.update", coins_total=2.0))
    client = FakeClient([])
    choice = await Coordinator(client, tmp_path).decide(state, "search_exhausted")
    assert client.calls == []
    assert choice.step == "report" and choice.source == "default"


def test_state_summary_is_deterministic_and_bounded() -> None:
    state = state_at("MAP")
    state.record_retry("mapper")
    a = state_summary(state, "agent_failed", "mapper", "x" * 5000, [f"n{i}" for i in range(9)])
    b = state_summary(state, "agent_failed", "mapper", "x" * 5000, [f"n{i}" for i in range(9)])
    assert a == b
    assert a["retries_used"] == 1 and a["failed_agent"] == "mapper"
    assert len(a["user_request"]) == 500 and a["notes"] == ["n4", "n5", "n6", "n7", "n8"]
    json.dumps(a)


async def test_replayed_recording_through_real_bob_client(tmp_path: Path) -> None:
    """End to end through BobClient in replay mode: no process is started and no coins are spent."""
    state = state_at("SEARCH")
    prompt = render_prompt("coordinator", state_summary=state_summary(state, "search_exhausted", None, None, None),
                           allowed_steps=["extend_search", "report", "stop"])
    reply = 'Extend once.\n```json\n{"next": "extend_search", "reason": "Only 200 sequences ran."}\n```'
    Recorder(tmp_path / "rec").save(recording_key("rook-coordinator", prompt), [
        (0.0, json.dumps({"type": "message", "role": "assistant", "content": reply})),
        (0.01, json.dumps({"type": "result", "status": "success", "stats": {"session_costs": 0.02}})),
    ])
    client = BobClient(EventBus(), RUN, mode="replay", recordings_dir=tmp_path / "rec", bin="/nonexistent/bob")
    choice = await Coordinator(client, tmp_path).decide(state, "search_exhausted")
    assert choice.step == "extend_search" and choice.source == "coordinator"
    finished = [e for e in client.bus._channel(RUN).history if e.type == "agent.finished"]
    assert finished and finished[0].data["recorded"] is True


async def test_missing_recording_falls_back(tmp_path: Path) -> None:
    client = BobClient(EventBus(), RUN, mode="replay", recordings_dir=tmp_path / "empty", bin="/nonexistent/bob")
    choice = await Coordinator(client, tmp_path).decide(state_at("SEARCH"), "search_exhausted")
    assert choice.step == "report" and choice.source == "default"


@pytest.mark.parametrize("branch", ["agent_failed", "search_exhausted", "verify_failed", "user_request"])
async def test_result_always_in_allowed_set(tmp_path: Path, branch: str) -> None:
    for proposal in ["retry", "skip", "ship", "fix", "diagnose", "verify", "stop", "continue", "nonsense"]:
        client = FakeClient([{"next": proposal, "reason": "r"}])
        choice = await Coordinator(client, tmp_path).decide(state_at("SEARCH"), branch, agent="scout")  # type: ignore[arg-type]
        assert choice.step in choice.allowed
