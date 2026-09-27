"""The run routes of 02 §11: create, list, read, stream, answer, chat, cancel, replay a counterexample."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from rook.core.session import SessionOptions
from rook.core.workspace import RepoSpec
from rook.sandbox.allowlist import REFUSED_MESSAGE
from rook.server.auth import Caller
from rook.server.deps import NOT_FOUND, AnyCaller, OwnedRun, ServerState, State, existing_caller
from rook.server.limits import client_ip
from rook.server.runs import LiveRun, QueueFull, RunSession, RunSpec, SessionFactory
from rook.server.schemas import (
    AnswerBody,
    ChatBody,
    CreateRun,
    Ok,
    RunCreatedResponse,
    RunDetail,
    RunRepo,
    RunStatusName,
    RunSummary,
)
from rook.server.sse import SSE_HEADERS, sse_stream, stored_events
from rook.store.repo import RunRecord

router = APIRouter()

_CX_ID = re.compile(r"[A-Za-z0-9_]{1,80}")
_STATUSES: frozenset[str] = frozenset({"queued", "running", "done", "failed", "cancelled"})
_HEADLINE_MAX = 120
GUEST_LIMIT_MESSAGE = ("Demo limit reached for today. Install the CLI to run on your own repos: "
                       "uv tool install rook-cli")
LIST_LIMIT = 50


# --- admission: which repo may run, and whether there is room for it ---

# A replay-mode run replays recorded Bob calls, so its search must be the recorded one: a fixed seed, one sequence
# at a time (with parallel sequences the app's own counters, such as order numbers, depend on thread timing), so
# the counterexample and the Detective's evidence (its recording key) are the same on every run. A shorter
# fresh search in VERIFY keeps a demo run near a minute; no Bob prompt depends on it.
REPLAY_SEARCH: dict[str, int | float] = {"seed": 7, "concurrency": 1, "verify_seconds": 30.0}


def _demo_repo(state: ServerState, caller: Caller, kind: str, ref: str) -> RepoSpec:
    """Only allowlisted demo repos run on the hosted server (03 §3)."""
    if kind != "demo" and caller.is_guest:
        raise HTTPException(403, "Guests can only run the demo repos")
    demo = state.settings.demo(ref) if kind == "demo" else None
    if demo is None:
        raise HTTPException(403, f"This repo {REFUSED_MESSAGE}")  # never echo the input
    return RepoSpec(kind="demo", ref=demo.ref, commit=demo.commit)


def _seconds_to_midnight(now: datetime) -> int:
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


def _admit(state: ServerState, caller: Caller, request: Request, auto: bool) -> SessionOptions:
    """Checks the daily coin cap, the queue and (for a guest) the daily quota; returns the run options.
    The quota is counted last, so a refused request never uses it up."""
    settings = state.settings
    now = datetime.now(UTC)
    day = now.strftime("%Y-%m-%d")
    retry = {"Retry-After": str(_seconds_to_midnight(now))}
    spent = state.db.coins_since(day)
    cap = settings.daily_coin_cap
    if cap is not None and settings.bob_mode != "replay" and spent >= cap:
        raise HTTPException(429, "Today's AI budget is spent; try again tomorrow", headers=retry)
    if state.runs.is_full():
        raise HTTPException(429, "The server is busy; try again in a few minutes", headers={"Retry-After": "60"})
    if caller.is_guest:
        peer = request.client.host if request.client else None
        ip = client_ip(request.headers, peer, settings.trusted_proxy_hops, settings.proxy_secret_value())
        limits = {f"guest:{caller.id}": settings.guest_runs_per_day, f"ip:{ip}": settings.guest_runs_per_ip_per_day}
        if not state.db.consume_run(limits, day):
            raise HTTPException(429, GUEST_LIMIT_MESSAGE, headers=retry)
    options = SessionOptions(auto=auto, hosted=True, daily_cap=cap, daily_spent=spent)
    return options.model_copy(update=REPLAY_SEARCH) if settings.bob_mode == "replay" else options


def _start(state: ServerState, repo: RepoSpec, request_text: str, options: SessionOptions, owner: str,
           factory: SessionFactory | None = None) -> str:
    try:
        return state.runs.start(repo, request_text, options, owner, factory=factory)
    except QueueFull as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "60"}) from exc


# --- reading runs ---


def _headline(request_text: str | None, name: str) -> str:
    text = " ".join((request_text or "").split()) or name
    return text if len(text) <= _HEADLINE_MAX else text[: _HEADLINE_MAX - 1] + "…"


def _result(state: ServerState, run_id: str) -> Literal["broken", "fixed"] | None:
    statuses = [cx.status for cx in state.store.list_counterexamples(run_id)]
    if "open" in statuses:
        return "broken"
    return "fixed" if statuses else None


def _status(value: str) -> RunStatusName:
    return value if value in _STATUSES else "failed"  # type: ignore[return-value]


def _stored_summary(state: ServerState, record: RunRecord) -> RunSummary:
    name = RepoSpec(kind="demo", ref=record.repo_ref).name if "/" in record.repo_ref else record.repo_ref
    return RunSummary(
        id=record.id, repo=RunRepo(kind=record.repo_kind, ref=record.repo_ref, name=name),
        status=_status(record.status), created_at=record.created_at, finished_at=record.finished_at,
        headline=_headline(state.db.run_request(record.id), name), result=_result(state, record.id),
        coins=record.coins, last_seq=state.store.last_seq(record.id))


def _queued_summary(run_id: str, live: LiveRun) -> RunSummary:
    name = live.repo.name
    return RunSummary(
        id=run_id, repo=RunRepo(kind=live.repo.kind, ref=live.repo.ref, name=name), status="queued",
        created_at=live.created_at, finished_at=None, headline=_headline(live.request, name), result=None,
        coins=0.0, last_seq=0)


def _summary(state: ServerState, run_id: str) -> RunSummary:
    record = state.store.get_run(run_id)
    if record is not None:
        return _stored_summary(state, record)
    live = state.runs.live(run_id)
    if live is None:
        raise HTTPException(404, NOT_FOUND)
    return _queued_summary(run_id, live)


def _cx_item(data: dict[str, Any], cx_id: str, status: str, rule_id: str) -> dict[str, Any]:
    rule = data.get("rule")
    rule_text = rule.get("text", "") if isinstance(rule, dict) else ""
    return {**data, "id": cx_id, "status": status, "rule_id": rule_id, "rule_text": rule_text}


# --- routes ---


@router.post("/runs", response_model=RunCreatedResponse)
async def create_run(body: CreateRun, request: Request, caller: AnyCaller, state: State) -> RunCreatedResponse:
    repo = _demo_repo(state, caller, body.repo.kind, body.repo.ref)
    options = _admit(state, caller, request, body.options.auto)
    return RunCreatedResponse(run_id=_start(state, repo, body.request, options, caller.id))


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(caller: AnyCaller, state: State) -> list[RunSummary]:
    stored = state.store.list_runs(user_id=caller.id, limit=LIST_LIMIT)
    seen = {r.id for r in stored}
    queued = [_queued_summary(run_id, live) for run_id, live in state.runs.live_of(caller.id) if run_id not in seen]
    items = queued + [_stored_summary(state, r) for r in stored]
    items.sort(key=lambda s: s.created_at, reverse=True)
    return items[:LIST_LIMIT]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: OwnedRun, state: State) -> RunDetail:
    cxs = [_cx_item(cx.data, cx.id, cx.status, cx.rule_id) for cx in state.store.list_counterexamples(run_id)]
    return RunDetail(run=_summary(state, run_id), counterexamples=cxs)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: OwnedRun, state: State,
               after: Annotated[int, Query(ge=0, le=2**53)] = 0) -> StreamingResponse:
    """A live run streams from the bus (stored replay, then the tail); a finished one from the store."""
    if state.runs.live(run_id) is not None:
        source = state.bus.subscribe(run_id, after)
    else:
        source = stored_events(state.store.events_after(run_id, after))
    stream = sse_stream(source, state.settings.ping_seconds, state.settings.flush_seconds)
    return StreamingResponse(stream, media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/runs/{run_id}/answers", response_model=Ok)
async def answer(run_id: OwnedRun, body: AnswerBody, state: State) -> Ok:
    live = state.runs.live(run_id)
    return Ok(ok=live is not None and live.session.answer(body.question_id, body.answer))


@router.post("/runs/{run_id}/chat", response_model=Ok)
async def chat(run_id: OwnedRun, body: ChatBody, state: State) -> Ok:
    live = state.runs.live(run_id)
    return Ok(ok=live is not None and live.session.chat(body.text))


@router.post("/runs/{run_id}/cancel", response_model=Ok)
async def cancel(run_id: OwnedRun, state: State) -> Ok:
    return Ok(ok=state.runs.cancel(run_id))


@router.post("/counterexamples/{cx_id}/replay", response_model=RunCreatedResponse)
async def replay(cx_id: str, request: Request, state: State,
                 caller: Annotated[Caller, Depends(existing_caller)]) -> RunCreatedResponse:
    """A new run that replays a stored counterexample on a fresh copy of the same demo repo."""
    cx = state.store.get_counterexample(cx_id) if _CX_ID.fullmatch(cx_id) else None
    if cx is None or state.runs.owner_of(cx.run_id) != caller.id:
        raise HTTPException(404, "Counterexample not found")
    record = state.store.get_run(cx.run_id)
    factory = state.replay_factory
    if factory is None or record is None:
        raise HTTPException(501, "Replaying a counterexample on the server is not available yet")
    repo = _demo_repo(state, caller, record.repo_kind, record.repo_ref)
    options = _admit(state, caller, request, auto=False)

    def make(spec: RunSpec) -> RunSession:
        return factory(spec, cx)

    run_id = _start(state, repo, f"Replay {cx.data.get('cx_id', cx_id)}", options, caller.id, factory=make)
    return RunCreatedResponse(run_id=run_id)
