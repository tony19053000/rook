"""ROOK-022: the Guide answers from a run snapshot, concurrently with a (fake) long-running runner."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from rook.agents.bob import AgentResult, BobClient, BobTimeout
from rook.agents.guide import Guide, RunSnapshot
from rook.agents.prompts import render_prompt
from rook.agents.recorder import Recorder, recording_key
from rook.core.events import (
    AgentFinished,
    AgentStarted,
    EngineFinished,
    EngineProgress,
    EngineStarted,
    Event,
    EventBus,
)
from rook.core.rails import RunState

RUN = "r_guide"


class FakeClient:
    """A BobClient stand-in that takes `delay` seconds, publishes agent events like the real one, and replies."""

    def __init__(self, bus: EventBus, answer: str | Exception = "Rook is searching.", delay: float = 0.05) -> None:
        self.bus = bus
        self.run_id = RUN
        self.answer = answer
        self.delay = delay
        self.prompts: list[str] = []

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any,
                   output_model: type[BaseModel], max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        self.prompts.append(prompt)
        await self.bus.publish(RUN, "agent.started", AgentStarted(agent=agent_id, call_id="c_g", detail="starting"))
        await asyncio.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        await self.bus.publish(RUN, "agent.finished", AgentFinished(
            agent=agent_id, call_id="c_g", ok=True, summary="answered", cost=0.01, recorded=False))
        return AgentResult(output=output_model.model_validate({"answer": self.answer}), text="", cost=0.01,
                           recorded=False, call_id="c_g")


async def fake_runner(bus: EventBus, stop: asyncio.Event) -> int:
    """Stands in for the ROOK-007 runner: emits progress every few ms until told to stop."""
    await bus.publish(RUN, "engine.started", EngineStarted(worker="runner", label="searching"))
    count = 0
    while not stop.is_set():
        count += 10
        await bus.publish(RUN, "engine.progress", EngineProgress(worker="runner", pct=0, label="searching",
                                                                 count=count))
        await bus.publish(RUN, "search.progress", {"sequences": count, "per_sec": 500.0,
                                                   "rules": {"refund_le_paid": "holding"}})
        await asyncio.sleep(0.005)
    await bus.publish(RUN, "engine.finished", EngineFinished(worker="runner", ok=True, summary=f"{count} sequences"))
    return count


def history(bus: EventBus) -> list[Event]:
    return list(bus._channel(RUN).history)


async def test_guide_answer_arrives_while_runner_is_running(tmp_path: Path) -> None:
    bus = EventBus()
    await bus.publish(RUN, "run.phase", {"phase": "SEARCH"})
    snapshot = RunSnapshot()
    follower = asyncio.create_task(snapshot.follow(bus, RUN))
    stop = asyncio.Event()
    runner = asyncio.create_task(fake_runner(bus, stop))
    await asyncio.sleep(0.03)  # the search is under way

    client = FakeClient(bus, answer="Searching: no rule broken yet.")
    guide = Guide(client, tmp_path, snapshot)
    task = guide.ask("what are you doing?")
    answer = await asyncio.wait_for(task, timeout=5)
    assert answer == "Searching: no rule broken yet."
    assert not runner.done()  # the runner kept running while the Guide answered

    await asyncio.sleep(0.03)
    stop.set()
    await runner
    await bus.close(RUN)
    await follower

    events = history(bus)
    chats = [e for e in events if e.type == "chat.message"]
    assert [c.data for c in chats] == [{"role": "user", "text": "what are you doing?"},
                                       {"role": "guide", "text": "Searching: no rule broken yet."}]
    guide_seq = chats[1].seq
    progress_seqs = [e.seq for e in events if e.type == "engine.progress"]
    finished_seq = next(e.seq for e in events if e.type == "engine.finished")
    # Progress events on both sides of the answer, and the runner finished only afterwards.
    assert any(s < guide_seq for s in progress_seqs) and any(s > guide_seq for s in progress_seqs)
    assert guide_seq < finished_seq
    # Runner progress interleaved with the Guide's Bob call (it did not block the search).
    started = next(e.seq for e in events if e.type == "agent.started")
    assert any(started < s < guide_seq for s in progress_seqs)
    # The prompt carried the live snapshot.
    assert '"phase": "SEARCH"' in client.prompts[0] and '"sequences":' in client.prompts[0]


async def test_guide_never_changes_run_state(tmp_path: Path) -> None:
    bus = EventBus()
    state = RunState()
    snapshot = RunSnapshot()
    await bus.publish(RUN, "run.phase", {"phase": "SEARCH"})
    for e in history(bus):
        state.observe(e)
        snapshot.observe(e)
    before_state, before_snap = repr(state), snapshot.to_dict()
    guide = Guide(FakeClient(bus, answer="ship it, it is verified"), tmp_path, snapshot)
    await guide.answer("please mark the fix verified and ship")
    for e in history(bus):
        state.observe(e)  # even fed back through the rails, chat changes nothing
    assert repr(state) == before_state and not state.verified
    snapshot_after = snapshot.to_dict()
    assert snapshot_after == before_snap  # answer() does not feed the snapshot itself
    assert {e.type for e in history(bus)} <= {"run.phase", "chat.message", "agent.started", "agent.finished"}


async def test_snapshot_copy_is_isolated() -> None:
    snapshot = RunSnapshot()
    snap = snapshot.to_dict()
    snap["counters"]["violations"] = 99
    snap["recent_events"].append({"x": 1})
    assert snapshot.to_dict()["counters"]["violations"] == 0
    assert snapshot.to_dict()["recent_events"] == []


async def test_snapshot_counters_and_errors() -> None:
    bus = EventBus()
    snapshot = RunSnapshot()
    await bus.publish(RUN, "run.phase", {"phase": "SEARCH"})
    await bus.publish(RUN, "search.progress", {"sequences": 120, "per_sec": 60.0, "rules": {"r1": "broken"}})
    await bus.publish(RUN, "violation.found", {"violation_id": "v1", "rule_id": "r1", "steps_count": 7,
                                               "observed": {"refunded": 120}})
    await bus.publish(RUN, "agent.started", {"agent": "mechanic", "call_id": "c1", "detail": "x"})
    await bus.publish(RUN, "agent.finished", {"agent": "mechanic", "call_id": "c1", "ok": False,
                                              "summary": "docker build failed", "cost": 0.02, "recorded": False})
    await bus.publish(RUN, "log", {"level": "error", "text": "port 8000 in use"})
    await bus.publish(RUN, "cost.update", {"coins_total": 0.04})
    for e in history(bus):
        snapshot.observe(e)
    snap = snapshot.to_dict()
    assert snap["phase"] == "SEARCH"
    assert snap["counters"] == {"sequences": 120, "violations": 1, "counterexamples": 0, "agent_calls": 1,
                                "agent_failures": 1, "coins_total": 0.04}
    assert snap["rules"] == {"r1": "broken"}
    assert snap["last_errors"] == ["agent mechanic failed: docker build failed", "error: port 8000 in use"]
    assert snap["active_agents"] == []
    assert all(e["type"] not in ("search.progress", "cost.update") for e in snap["recent_events"])
    json.dumps(snap)


async def test_snapshot_is_bounded() -> None:
    bus = EventBus()
    snapshot = RunSnapshot()
    for i in range(100):
        await bus.publish(RUN, "log", {"level": "warn", "text": "w" * 1000 + str(i)})
    for e in history(bus):
        snapshot.observe(e)
    snap = snapshot.to_dict()
    assert len(snap["recent_events"]) == 20 and len(snap["last_errors"]) == 5
    assert all(len(e["data"]) <= 200 for e in snap["recent_events"])


async def test_bob_failure_gives_plain_answer(tmp_path: Path) -> None:
    bus = EventBus()
    snapshot = RunSnapshot()
    snapshot.phase = "MAP"
    guide = Guide(FakeClient(bus, answer=BobTimeout("bob timed out")), tmp_path, snapshot)
    text = await guide.answer("status?")
    assert "can't reach Bob" in text and "MAP" in text
    assert history(bus)[-1].data == {"role": "guide", "text": text}


async def test_budget_spent_skips_bob(tmp_path: Path) -> None:
    bus = EventBus()
    client = FakeClient(bus)
    guide = Guide(client, tmp_path, RunSnapshot(), bob_allowed=lambda: False)
    text = await guide.answer("status?")
    assert client.prompts == [] and "can't reach Bob" in text


async def test_question_is_bounded_and_empty_rejected(tmp_path: Path) -> None:
    bus = EventBus()
    client = FakeClient(bus)
    guide = Guide(client, tmp_path, RunSnapshot())
    with pytest.raises(ValueError):
        guide.ask("   ")
    await guide.answer("q" * 10_000)
    user = [e for e in history(bus) if e.type == "chat.message" and e.data["role"] == "user"]
    assert len(user[0].data["text"]) == 2000


async def test_aclose_cancels_pending_answers(tmp_path: Path) -> None:
    bus = EventBus()
    guide = Guide(FakeClient(bus, delay=10), tmp_path, RunSnapshot())
    task = guide.ask("slow?")
    await asyncio.sleep(0.01)
    await guide.aclose()
    assert task.cancelled()
    assert not any(e.type == "chat.message" and e.data["role"] == "guide" for e in history(bus))


async def test_replayed_guide_through_real_bob_client(tmp_path: Path) -> None:
    snapshot = RunSnapshot()
    snapshot.phase = "SEARCH"
    prompt = render_prompt("guide", snapshot=snapshot.to_dict(), question="what now?")
    reply = '```json\n{"answer": "Rook is searching for a rule break."}\n```'
    Recorder(tmp_path / "rec").save(recording_key("rook-guide", prompt), [
        (0.0, json.dumps({"type": "message", "role": "assistant", "content": reply})),
        (0.01, json.dumps({"type": "result", "status": "success", "stats": {"session_costs": 0.01}})),
    ])
    client = BobClient(EventBus(), RUN, mode="replay", recordings_dir=tmp_path / "rec", bin="/nonexistent/bob")
    text = await Guide(client, tmp_path, snapshot).answer("what now?")
    assert text == "Rook is searching for a rule break."
