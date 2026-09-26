"""First-run auth seam. ROOK-030 replaces `StubAuth` with the real Google + GitHub flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthState:
    user: str | None = None
    github_repos: int | None = None  # None: GitHub not connected

    @property
    def signed_in(self) -> bool:
        return self.user is not None

    @property
    def github_connected(self) -> bool:
        return self.github_repos is not None


class AuthProvider(Protocol):
    def state(self) -> AuthState:
        """The saved credentials, read without any network call."""
        ...

    async def sign_in(self) -> str | None:
        """Sign in with Google; the user name, or None if it failed or isn't available."""
        ...

    async def connect_github(self) -> int | None:
        """Connect GitHub; the number of shared repos, or None."""
        ...


class StubAuth:
    """No credentials and no sign-in yet: the TUI shows the steps and continues offline."""

    def __init__(self, state: AuthState | None = None) -> None:
        self._state = state or AuthState()

    def state(self) -> AuthState:
        return self._state

    async def sign_in(self) -> str | None:
        return None

    async def connect_github(self) -> int | None:
        return None
