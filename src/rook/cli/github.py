"""GitHub repos in the CLI (ROOK-031): an installation token from the Rook server, for the clone and the PR.

`rook run owner/name` needs `rook login` and the Rook GitHub App installed on that repo. The CLI asks the server
(`POST /github/token`, with the saved sign-in) for a token scoped to that one repo: once for the clone, and again
at SHIP (a run can outlive a token). The token is kept in memory only, registered with the redaction filter and
never printed.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from rook.cli import login
from rook.core.events import register_secret

INSTALL_HINT = "connect GitHub from the Rook web app (Connect GitHub) and share the repo with the Rook app"


class GitHubTokenError(ValueError):
    """No token for this repo; the message says what to do (never holds a token)."""


class ServerTokens:
    """Fetches installation tokens for `repo` from the server the user signed in to."""

    def __init__(self, repo: str, credentials: Path,
                 client_factory: Callable[[], httpx.Client] = login.http_client,
                 clock: Callable[[], float] = time.time) -> None:
        self.repo = repo
        self.credentials = credentials
        self._client_factory = client_factory
        self._clock = clock

    def fetch(self) -> str:
        creds = login.load_credentials(self.credentials)
        if creds is None:
            raise GitHubTokenError(f"GitHub repos need a sign-in: run `rook login`, then {INSTALL_HINT}")
        if creds.expires_at and creds.expires_at <= self._clock():
            raise GitHubTokenError("your sign-in has expired: run `rook login` again")
        try:
            server = login.server_url(creds.server)
        except login.LoginError as exc:
            raise GitHubTokenError(str(exc)) from None
        try:
            with self._client_factory() as client:
                response = client.post(f"{server}{login.API}/github/token", json={"repo": self.repo},
                                       headers={"Authorization": f"Bearer {creds.access_token}"})
        except httpx.HTTPError as exc:
            raise GitHubTokenError(f"the Rook server is unreachable ({type(exc).__name__})") from None
        if response.status_code == 401:
            raise GitHubTokenError("the server did not accept your sign-in: run `rook login` again")
        if response.status_code != 200:
            raise GitHubTokenError(f"no GitHub token for {self.repo}: {_detail(response)} ({INSTALL_HINT})")
        try:
            token = response.json()["token"]
        except (ValueError, KeyError, TypeError):
            raise GitHubTokenError("the server sent an unexpected answer") from None
        if not isinstance(token, str) or not token:
            raise GitHubTokenError("the server sent an unexpected answer")
        register_secret(token)
        return token

    async def __call__(self) -> str:
        return await asyncio.to_thread(self.fetch)


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    return detail[:200] if isinstance(detail, str) else f"HTTP {response.status_code}"
