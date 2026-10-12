"""`/health`, `/me`, `DELETE /me/data`, `/repos` (02 §11)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from rook.server.deps import AnyCaller, SameSite, State, UserCaller
from rook.server.github_link import AppGitHub
from rook.server.github_runs import not_configured
from rook.server.limits import proxy_verified
from rook.server.schemas import DataDeleted, Health, Me, RepoOption

router = APIRouter()


@router.get("/health", response_model=Health)
def health(request: Request, state: State) -> Health:
    """`proxied` lets an operator check the Vercel proxy secret end to end (02 §14)."""
    proxied = proxy_verified(request.headers, state.settings.proxy_secret_value())
    return Health(ok=True, version=state.settings.version, bob_mode=state.settings.bob_mode, proxied=proxied)


@router.get("/me", response_model=Me)
def me(caller: UserCaller, state: State) -> Me:
    """`can_run_github`: linked to the GitHub App, and this server can run GitHub repos (App, BOB_API_KEY,
    Docker). A sync route: the (cached) Docker probe runs in the thread pool."""
    connected = state.github.connected(caller)
    can_run = connected and not not_configured(state.settings, isinstance(state.github, AppGitHub),
                                               state.docker_ready)
    return Me(id=caller.id, email=caller.email, github_connected=connected, can_run_github=can_run)


@router.delete("/me/data", response_model=DataDeleted, dependencies=[SameSite])
async def delete_my_data(caller: UserCaller, state: State) -> DataDeleted:
    """Every run of the caller and their `users` row (ROOK-051). The Supabase account is deleted on request by
    email: this server holds no Supabase service key."""
    runs_deleted = await asyncio.shield(state.deleter.delete_user(caller.id))
    return DataDeleted(ok=True, runs_deleted=runs_deleted)


@router.get("/repos", response_model=list[RepoOption])
async def repos(caller: AnyCaller, state: State) -> list[RepoOption]:
    """Guests see only the demo repos; users also see their GitHub repos (ROOK-031)."""
    demos = [RepoOption(kind="demo", ref=d.ref, name=d.name, private=False, language=d.language)
             for d in state.settings.demo_repos]
    if caller.is_guest:
        return demos
    return [*await state.github.list_repos(caller), *demos]
