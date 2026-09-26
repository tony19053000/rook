"""Shared server state and the FastAPI dependencies that resolve the caller and check run ownership."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response

from rook.core.events import EventBus
from rook.server.auth import Caller, GuestCookies, TokenVerifier, resolve_caller
from rook.server.config import ServerSettings
from rook.server.db import ServerDb
from rook.server.github_link import GitHubLink
from rook.server.runs import ReplayFactory, RunManager
from rook.store.repo import Store

_RUN_ID = re.compile(r"r_[a-z2-7]{12}")
NOT_FOUND = "Run not found"


@dataclass
class ServerState:
    settings: ServerSettings
    store: Store
    db: ServerDb
    bus: EventBus
    runs: RunManager
    verifier: TokenVerifier
    cookies: GuestCookies
    github: GitHubLink
    replay_factory: ReplayFactory | None


def get_state(request: Request) -> ServerState:
    state: ServerState = request.app.state.rook
    return state


State = Annotated[ServerState, Depends(get_state)]


def user_or_guest(request: Request, response: Response, state: State) -> Caller:
    """A user, or a guest (a new guest cookie is issued when there is none)."""
    return resolve_caller(request, response, state.verifier, state.cookies, allow_guest=True, issue_guest=True)


def user_only(request: Request, response: Response, state: State) -> Caller:
    return resolve_caller(request, response, state.verifier, state.cookies, allow_guest=False, issue_guest=False)


def existing_caller(request: Request, response: Response, state: State) -> Caller:
    """A user or an existing guest; owner routes never mint a guest (it could own nothing)."""
    return resolve_caller(request, response, state.verifier, state.cookies, allow_guest=True, issue_guest=False)


AnyCaller = Annotated[Caller, Depends(user_or_guest)]
UserCaller = Annotated[Caller, Depends(user_only)]


def owned_run(run_id: str, state: State, caller: Annotated[Caller, Depends(existing_caller)]) -> str:
    """The run id when the caller owns it; 404 otherwise (a stranger's run looks missing, 03 §7)."""
    if not _RUN_ID.fullmatch(run_id) or state.runs.owner_of(run_id) != caller.id:
        raise HTTPException(404, NOT_FOUND)
    return run_id


OwnedRun = Annotated[str, Depends(owned_run)]
