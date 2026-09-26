"""Event contract (02_ARCHITECTURE.md §9), secret redaction (03_SECURITY_ACCESS.md §2) and the EventBus."""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"
_MIN_SECRET_LEN = 4  # shorter values would scrub ordinary text

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # A full PEM block first, then any unterminated "-----BEGIN" up to the end of the string.
    (re.compile(r"-----BEGIN [A-Z0-9 ]*-----.*?-----END [A-Z0-9 ]*-----", re.DOTALL), REDACTED),
    (re.compile(r"-----BEGIN[\s\S]*"), REDACTED),
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), f"Bearer {REDACTED}"),
    (re.compile(r"bob_prod_[A-Za-z0-9_\-]+"), REDACTED),
    (re.compile(r"\bgh[ps]_[A-Za-z0-9]+"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]*){0,2}"), REDACTED),
]

_secrets: set[str] = set()
_secrets_lock = threading.Lock()


def register_secret(value: str | None) -> None:
    """Register a known secret value (e.g. BOB_API_KEY) so it is scrubbed from every event."""
    if value and len(value) >= _MIN_SECRET_LEN:
        with _secrets_lock:
            _secrets.add(value)


def clear_secrets() -> None:
    """Forget every registered secret value (used by tests)."""
    with _secrets_lock:
        _secrets.clear()


def redact_text(text: str) -> str:
    with _secrets_lock:
        known = sorted(_secrets, key=len, reverse=True)
    for value in known:
        text = text.replace(value, REDACTED)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact(obj: Any) -> Any:
    """Return a copy of `obj` with every string (including dict keys) scrubbed of secrets."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {redact(k): redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact(v) for v in obj)
    return obj


# ---------------------------------------------------------------------------
# Event data models (one per event type in 02 §9)
# ---------------------------------------------------------------------------

Phase = Literal[
    "PREPARE", "SCOUT", "START_APP", "MAP", "RULES", "APPROVE", "DESIGN", "SEARCH", "SHRINK", "REPLAY",
    "SAVE", "DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE",
]
Worker = Literal["runner", "judge", "shrinker", "replayer", "testrunner", "verifier"]


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RepoRef(_Data):
    kind: str
    ref: str
    name: str


class RunOptions(_Data):
    auto: bool
    budget: float


class RunCreated(_Data):
    repo: RepoRef
    request: str
    options: RunOptions


class RunPhase(_Data):
    phase: Phase


class AgentStarted(_Data):
    agent: str
    call_id: str
    detail: str


class AgentProgress(_Data):
    agent: str
    call_id: str
    detail: str


class AgentFinished(_Data):
    agent: str
    call_id: str
    ok: bool
    summary: str
    cost: float
    recorded: bool


class EngineStarted(_Data):
    worker: Worker
    label: str


class EngineProgress(_Data):
    worker: Worker
    pct: float
    label: str
    count: int | None = None


class EngineFinished(_Data):
    worker: Worker
    ok: bool
    summary: str


class QuestionOption(_Data):
    id: str
    label: str


class QuestionAsked(_Data):
    question_id: str
    kind: Literal["approve_rules", "fix", "pr", "setup_value", "menu", "repo"]
    text: str
    options: list[QuestionOption]
    payload: Any = None


class QuestionAnswered(_Data):
    question_id: str
    answer: Any
    by: Literal["user", "auto"]


class RepoSummary(_Data):
    language: str
    framework: str
    entrypoints: list[str]
    routes_files: list[str]
    models_files: list[str]
    test_command: str | None
    run_hints: Any = None
    business_summary: str


class SandboxReady(_Data):
    base_url_redacted: str
    mode: str


class ModelActions(_Data):
    actors: list[Any]
    actions: list[Any]
    state: list[Any]


class RulesProposed(_Data):
    rules: list[Any]


class RulesReviewed(_Data):
    verdicts: list[Any]


class RulesApproved(_Data):
    rule_ids: list[str]


class SearchProgress(_Data):
    sequences: int
    per_sec: float
    rules: dict[str, Literal["holding", "broken"]]


class ViolationFound(_Data):
    violation_id: str
    rule_id: str
    steps_count: int
    observed: Any


class ShrinkStep(_Data):
    violation_id: str
    steps_count: int


class CounterexampleSaved(_Data):
    cx_id: str
    rule_id: str
    rule_text: str
    steps: list[Any]
    observed: Any
    expected: Any
    reproduced: str = Field(pattern=r"^\d+/\d+$")
    flaky: bool
    test_path: str | None


class DiagnosisReady(_Data):
    cx_id: str
    file: str
    line: int | None
    explanation: str
    reviewed: bool


class FixReady(_Data):
    cx_id: str
    files: list[str]
    diff: str
    reviewed: bool


class VerifyStep(_Data):
    cx_id: str
    check: Literal["replay", "project_tests", "regression_test", "fresh_search"]
    status: Literal["running", "passed", "failed"]
    detail: str


class VerifyDone(_Data):
    cx_id: str
    verified: bool
    summary: str


class PrOpened(_Data):
    url: str
    number: int
    branch: str


class ChatMessage(_Data):
    role: Literal["user", "guide"]
    text: str


class CostUpdate(_Data):
    coins_total: float


class Log(_Data):
    level: Literal["info", "warn", "error"]
    text: str


class RunFinished(_Data):
    status: Literal["done", "failed", "cancelled"]
    summary: str


EVENT_TYPES: dict[str, type[BaseModel]] = {
    "run.created": RunCreated,
    "run.phase": RunPhase,
    "agent.started": AgentStarted,
    "agent.progress": AgentProgress,
    "agent.finished": AgentFinished,
    "engine.started": EngineStarted,
    "engine.progress": EngineProgress,
    "engine.finished": EngineFinished,
    "question.asked": QuestionAsked,
    "question.answered": QuestionAnswered,
    "repo.summary": RepoSummary,
    "sandbox.ready": SandboxReady,
    "model.actions": ModelActions,
    "rules.proposed": RulesProposed,
    "rules.reviewed": RulesReviewed,
    "rules.approved": RulesApproved,
    "search.progress": SearchProgress,
    "violation.found": ViolationFound,
    "shrink.step": ShrinkStep,
    "counterexample.saved": CounterexampleSaved,
    "diagnosis.ready": DiagnosisReady,
    "fix.ready": FixReady,
    "verify.step": VerifyStep,
    "verify.done": VerifyDone,
    "pr.opened": PrOpened,
    "chat.message": ChatMessage,
    "cost.update": CostUpdate,
    "log": Log,
    "run.finished": RunFinished,
}

EventType = Literal[
    "run.created", "run.phase", "agent.started", "agent.progress", "agent.finished", "engine.started",
    "engine.progress", "engine.finished", "question.asked", "question.answered", "repo.summary",
    "sandbox.ready", "model.actions", "rules.proposed", "rules.reviewed", "rules.approved",
    "search.progress", "violation.found", "shrink.step", "counterexample.saved", "diagnosis.ready",
    "fix.ready", "verify.step", "verify.done", "pr.opened", "chat.message", "cost.update", "log",
    "run.finished",
]


def validate_data(event_type: str, data: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Validate `data` against the model for `event_type` and return its redacted JSON form."""
    model = EVENT_TYPES.get(event_type)
    if model is None:
        raise ValueError(f"unknown event type: {event_type!r}")
    raw = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
    return redact(model.model_validate(raw).model_dump(mode="json"))


class Event(BaseModel):
    """The envelope: one JSON object per event."""

    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = 1
    seq: int = Field(ge=1)
    ts: str
    run_id: str
    type: EventType
    data: dict[str, Any]

    def typed_data(self) -> BaseModel:
        return EVENT_TYPES[self.type].model_validate(self.data)


def now_ts() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventStore(Protocol):
    def append_event(self, event: Event) -> None: ...

    def events_after(self, run_id: str, seq: int) -> list[Event]: ...

    def last_seq(self, run_id: str) -> int: ...


class _RunChannel:
    def __init__(self, last_seq: int) -> None:
        self.lock = asyncio.Lock()
        self.seq = last_seq
        self.history: list[Event] = []
        self.subscribers: set[asyncio.Queue[Event | None]] = set()
        self.closed = False


class EventBus:
    """Async per-run pub/sub. Every event is validated, redacted, given the next seq, stored, then delivered.

    Without a store, history is kept in memory so late subscribers can replay.
    """

    def __init__(self, store: EventStore | None = None) -> None:
        self._store = store
        self._runs: dict[str, _RunChannel] = {}

    def _channel(self, run_id: str) -> _RunChannel:
        channel = self._runs.get(run_id)
        if channel is None:
            channel = _RunChannel(self._store.last_seq(run_id) if self._store else 0)
            self._runs[run_id] = channel
        return channel

    async def publish(self, run_id: str, event_type: str, data: BaseModel | dict[str, Any]) -> Event:
        payload = validate_data(event_type, data)
        channel = self._channel(run_id)
        async with channel.lock:
            if channel.closed:
                raise RuntimeError(f"run {run_id!r} is closed")
            channel.seq += 1
            event = Event(seq=channel.seq, ts=now_ts(), run_id=run_id, type=event_type, data=payload)
            if self._store is not None:
                self._store.append_event(event)
            else:
                channel.history.append(event)
            for queue in channel.subscribers:
                queue.put_nowait(event)
        return event

    async def close(self, run_id: str) -> None:
        """End the run's stream: current subscribers finish; late subscribers get the replay only."""
        channel = self._channel(run_id)
        async with channel.lock:
            channel.closed = True
            for queue in channel.subscribers:
                queue.put_nowait(None)

    async def subscribe(self, run_id: str, after: int = 0) -> AsyncIterator[Event]:
        """Yield every event with seq > `after`: the stored replay first, then the live tail."""
        channel = self._channel(run_id)
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        # No await between snapshot and registration, so no event can fall in the gap.
        if self._store is not None:
            replay = self._store.events_after(run_id, after)
        else:
            replay = [e for e in channel.history if e.seq > after]
        closed = channel.closed
        if not closed:
            channel.subscribers.add(queue)
        last = after
        try:
            for event in replay:
                last = event.seq
                yield event
            if closed:
                return
            while True:
                item = await queue.get()
                if item is None:
                    return
                if item.seq > last:
                    last = item.seq
                    yield item
        finally:
            channel.subscribers.discard(queue)
