"""The Guide: answers user chat from a snapshot of the run, concurrently with the run (02_ARCHITECTURE.md §4).

It only reads a copy of the snapshot and publishes `chat.message` events; it never changes run state.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from collections.abc import Callable
from typing import Any, Literal

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.schemas import GuideAnswer
from rook.core.events import ChatMessage, Event, EventBus, Log

QUESTION_MAX = 2000
_RECENT = 20
_ERRORS = 5
_DETAIL_MAX = 200
# High-rate events are folded into the counters instead of the recent list.
_NOISY = frozenset({"engine.progress", "search.progress", "agent.progress", "cost.update", "chat.message"})


def _detail(data: dict[str, Any]) -> str:
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= _DETAIL_MAX else text[: _DETAIL_MAX - 1] + "…"


class RunSnapshot:
    """A small, JSON-ready picture of a run, built from its (already redacted) events."""

    def __init__(self) -> None:
        self.phase = "PREPARE"
        self.status = "running"
        self.counters: dict[str, Any] = {
            "sequences": 0, "violations": 0, "counterexamples": 0, "agent_calls": 0, "agent_failures": 0,
            "coins_total": 0.0,
        }
        self.rules: dict[str, str] = {}
        self.active_agents: dict[str, str] = {}  # call_id -> agent
        self.recent: deque[dict[str, Any]] = deque(maxlen=_RECENT)
        self.errors: deque[str] = deque(maxlen=_ERRORS)

    def observe(self, event: Event) -> None:
        d = event.data
        c = self.counters
        match event.type:
            case "run.phase":
                self.phase = d["phase"]
            case "run.finished":
                self.status = d["status"]
            case "search.progress":
                c["sequences"] = d["sequences"]
                self.rules = dict(d["rules"])
            case "violation.found":
                c["violations"] += 1
            case "counterexample.saved":
                c["counterexamples"] += 1
            case "cost.update":
                c["coins_total"] = d["coins_total"]
            case "agent.started":
                c["agent_calls"] += 1
                self.active_agents[d["call_id"]] = d["agent"]
            case "agent.finished":
                self.active_agents.pop(d["call_id"], None)
                if not d["ok"]:
                    c["agent_failures"] += 1
                    self.errors.append(f"agent {d['agent']} failed: {d['summary']}")
            case "engine.finished" if not d["ok"]:
                self.errors.append(f"engine {d['worker']} failed: {d['summary']}")
            case "verify.step" if d["status"] == "failed":
                self.errors.append(f"verify {d['check']} failed: {d['detail']}")
            case "log" if d["level"] in ("warn", "error"):
                self.errors.append(f"{d['level']}: {d['text']}")
        if event.type not in _NOISY:
            self.recent.append({"seq": event.seq, "type": event.type, "data": _detail(d)})

    def to_dict(self) -> dict[str, Any]:
        """A deep copy: the Guide can never reach back into the live snapshot."""
        return {
            "phase": self.phase,
            "status": self.status,
            "counters": dict(self.counters),
            "rules": dict(self.rules),
            "active_agents": sorted(set(self.active_agents.values())),
            "recent_events": [dict(e) for e in self.recent],
            "last_errors": list(self.errors),
        }

    async def follow(self, bus: EventBus, run_id: str, after: int = 0) -> None:
        """Observe every event of the run until the bus closes it (run as a background task)."""
        async for event in bus.subscribe(run_id, after=after):
            self.observe(event)


def fallback_answer(snapshot: dict[str, Any]) -> str:
    c = snapshot["counters"]
    return (f"I can't reach Bob right now. Rook is in {snapshot['phase']}: {c['sequences']} sequences run, "
            f"{c['violations']} violation(s) found.")


class Guide:
    """Each question runs as its own task, so answers arrive while the run keeps going."""

    def __init__(
        self,
        client: AgentCaller,
        workspace: str | os.PathLike[str],
        snapshot: RunSnapshot,
        *,
        bob_allowed: Callable[[], bool] | None = None,
    ) -> None:
        self.client = client
        self.workspace = workspace
        self.snapshot = snapshot
        self.bob_allowed = bob_allowed or (lambda: True)
        self._tasks: set[asyncio.Task[str]] = set()

    def ask(self, question: str) -> asyncio.Task[str]:
        """Start answering in the background; the answer is published as `chat.message{role: guide}`."""
        if not question.strip():
            raise ValueError("empty question")
        task = asyncio.create_task(self.answer(question))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def answer(self, question: str) -> str:
        question = question.strip()[:QUESTION_MAX]
        await self._say("user", question)
        snap = self.snapshot.to_dict()
        text = fallback_answer(snap)
        if self.bob_allowed():
            try:
                result = await call_agent(self.client, "guide", self.workspace, snapshot=snap, question=question)
                output = result.output
                assert isinstance(output, GuideAnswer)
                text = output.answer
            except BOB_FAILURES as exc:  # fall back to a plain answer from the snapshot
                await self.client.bus.publish(self.client.run_id, "log", Log(
                    level="warn", text=f"Guide failed ({type(exc).__name__}); answered from the snapshot"))
        await self._say("guide", text)
        return text

    async def aclose(self) -> None:
        """Cancel unanswered questions (e.g. when the run is cancelled)."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _say(self, role: Literal["user", "guide"], text: str) -> None:
        await self.client.bus.publish(self.client.run_id, "chat.message", ChatMessage(role=role, text=text))
