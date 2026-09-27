"""First-run auth seam: `SavedAuth` reads the credentials `rook login` saved (ROOK-030); GitHub is ROOK-031."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


class SavedAuth(StubAuth):
    """Signed in when `rook login` saved credentials. The shell never opens a browser by itself: signing in
    is optional (everything runs locally without it), so the first run points at `rook login` instead."""

    def __init__(self, credentials: Path) -> None:
        from rook.cli.login import load_credentials

        creds = load_credentials(credentials)
        super().__init__(AuthState(user=(creds.email or "you") if creds else None))
