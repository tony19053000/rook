"""The seam for the GitHub App (ROOK-031): whether a user is connected and which repos they can pick.

Until ROOK-031 is in, `NoGitHub` answers "not connected" and lists nothing; no GitHub call is made.
"""

from __future__ import annotations

from typing import Protocol

from rook.server.auth import Caller
from rook.server.schemas import RepoOption


class GitHubLink(Protocol):
    def connected(self, user: Caller) -> bool: ...

    async def list_repos(self, user: Caller) -> list[RepoOption]: ...


class NoGitHub:
    def connected(self, user: Caller) -> bool:
        return False

    async def list_repos(self, user: Caller) -> list[RepoOption]:
        return []
