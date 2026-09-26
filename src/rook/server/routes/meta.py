"""`/health`, `/me`, `/repos` (02 §11)."""

from __future__ import annotations

from fastapi import APIRouter

from rook.server.deps import AnyCaller, State, UserCaller
from rook.server.schemas import Health, Me, RepoOption

router = APIRouter()


@router.get("/health", response_model=Health)
def health(state: State) -> Health:
    return Health(ok=True, version=state.settings.version, bob_mode=state.settings.bob_mode)


@router.get("/me", response_model=Me)
def me(caller: UserCaller, state: State) -> Me:
    return Me(id=caller.id, email=caller.email, github_connected=state.github.connected(caller))


@router.get("/repos", response_model=list[RepoOption])
async def repos(caller: AnyCaller, state: State) -> list[RepoOption]:
    """Guests see only the demo repos; users also see their GitHub repos (ROOK-031)."""
    demos = [RepoOption(kind="demo", ref=d.ref, name=d.name, private=False, language=d.language)
             for d in state.settings.demo_repos]
    if caller.is_guest:
        return demos
    return [*await state.github.list_repos(caller), *demos]
