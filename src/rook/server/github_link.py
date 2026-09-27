"""The GitHub App on the server (ROOK-031, 02 §11, 03 §6): whether a user is connected, their repos, the
install URL and setup callback, installation tokens for the CLI, and installation webhooks.

`NoGitHub` (no App configured) answers "not connected", lists nothing and makes no GitHub call.

Linking an installation to a user (the setup callback) must not let anyone claim someone else's installation
(installation ids are small integers that are easy to guess). So:
- the `state` is one-time, bound to the signed-in user who asked for the install URL, and expires in 15 min
  (CSRF: a forged or replayed callback fails);
- the installation must exist for this App (`GET /app/installations/{id}` with the App JWT), not be suspended
  and not be linked to another user;
- with the OAuth client configured (GITHUB_CLIENT_ID + GITHUB_CLIENT_SECRET, "Request user authorization during
  installation"), the callback's `code` must prove that the GitHub user who installed can access it
  (`GET /user/installations`). Without it, the installation must have been created after that user's `state`
  was issued (a fresh install in this flow); re-linking an installation the user already has is always allowed;
- a user gets at most 5 failed callbacks per hour.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlencode

from rook.github.app import GitHubApp, GitHubError, InstallationToken
from rook.server.auth import Caller
from rook.server.db import ServerDb
from rook.server.schemas import RepoOption

log = logging.getLogger(__name__)

STATE_TTL = 15 * 60.0
MAX_STATES = 1000
STATES_PER_USER = 5
CLOCK_SKEW = 120.0  # an installation's created_at may be this much before the state (clock drift)
MAX_FAILURES = 5
FAILURE_WINDOW = 3600.0
REPOS_TTL = 60.0
NOT_VERIFIED = "Rook could not verify that this GitHub installation is yours. Connect GitHub again from Rook."


class GitHubLink(Protocol):
    def connected(self, user: Caller) -> bool: ...

    async def list_repos(self, user: Caller) -> list[RepoOption]: ...


class NoGitHub:
    def connected(self, user: Caller) -> bool:
        return False

    async def list_repos(self, user: Caller) -> list[RepoOption]:
        return []


class SetupError(Exception):
    """The setup callback is refused; `status` is the HTTP status, the message is safe to show."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class _State:
    user_id: str
    issued_at: float


class InstallStates:
    """One-time install `state` values, each bound to the user who asked for it (in memory, one process)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._states: dict[str, _State] = {}

    def issue(self, user_id: str) -> str | None:
        now = self._clock()
        self._states = {k: v for k, v in self._states.items() if now - v.issued_at < STATE_TTL}
        mine = [k for k, v in self._states.items() if v.user_id == user_id]  # oldest first (insertion order)
        for key in mine[:max(0, len(mine) - STATES_PER_USER + 1)]:
            del self._states[key]
        if len(self._states) >= MAX_STATES:
            return None
        state = secrets.token_urlsafe(32)
        self._states[state] = _State(user_id, now)
        return state

    def take(self, state: str, user_id: str) -> float | None:
        """When the state was issued, if it is this user's and fresh; it is used up either way."""
        found = self._states.pop(state, None)
        if found is None or found.user_id != user_id or self._clock() - found.issued_at >= STATE_TTL:
            return None
        return found.issued_at


class AppGitHub:
    """The GitHub App seam for a configured server (see the module docstring for the linking rules)."""

    def __init__(self, app: GitHubApp, db: ServerDb, *, slug: str, web_url: str = "https://github.com",
                 clock: Callable[[], float] = time.time) -> None:
        self.app = app
        self.db = db
        self.slug = slug
        self.web_url = web_url.rstrip("/")
        self._clock = clock
        self.states = InstallStates(clock)
        self._failures: dict[str, deque[float]] = {}
        self._repos: dict[int, tuple[float, list[RepoOption]]] = {}

    # --- GitHubLink ---

    def connected(self, user: Caller) -> bool:
        return self.db.installation_of(user.id) is not None

    async def list_repos(self, user: Caller) -> list[RepoOption]:
        installation = self.db.installation_of(user.id)
        if installation is None:
            return []
        cached = self._repos.get(installation)
        if cached is not None and self._clock() - cached[0] < REPOS_TTL:
            return cached[1]
        try:
            repos = await self.app.repos(installation)
        except GitHubError as exc:
            if exc.status == 404:  # uninstalled and the webhook was missed
                self._forget(installation, unlink=True)
            log.warning("could not list the GitHub repos of an installation: %s", exc)
            return []
        options = [RepoOption(kind="github", ref=r.full_name, name=r.full_name.rsplit("/", 1)[-1],
                              private=r.private, language=r.language) for r in repos]
        self._repos[installation] = (self._clock(), options)
        return options

    # --- install URL and setup callback ---

    def install_url(self, user: Caller) -> str | None:
        """`https://github.com/apps/<slug>/installations/new?state=…`; None when too many are pending."""
        state = self.states.issue(user.id)
        if state is None:
            return None
        return f"{self.web_url}/apps/{self.slug}/installations/new?{urlencode({'state': state})}"

    def _failed(self, user_id: str) -> None:
        self._failures.setdefault(user_id, deque()).append(self._clock())

    def _blocked(self, user_id: str) -> bool:
        hits = self._failures.get(user_id)
        if hits is None:
            return False
        while hits and hits[0] <= self._clock() - FAILURE_WINDOW:
            hits.popleft()
        return len(hits) >= MAX_FAILURES

    async def complete_setup(self, user: Caller, installation_id: int, state: str, code: str | None) -> None:
        """Link the installation to `user`, or raise SetupError (400 bad state, 403 not verified, 429)."""
        if self._blocked(user.id):
            raise SetupError(429, "Too many failed GitHub connections, try again in an hour")
        issued = self.states.take(state, user.id)
        if issued is None:
            self._failed(user.id)
            raise SetupError(400, "This GitHub connection link expired or was not started here. "
                                  "Connect GitHub again from Rook.")
        try:
            await self._verify(user, installation_id, issued, code)
        except SetupError:
            self._failed(user.id)
            raise
        now = datetime.now(UTC).isoformat()
        if not self.db.bind_installation(user.id, user.email, installation_id, now):
            self._failed(user.id)
            raise SetupError(403, NOT_VERIFIED)
        self._repos.pop(installation_id, None)

    async def _verify(self, user: Caller, installation_id: int, issued: float, code: str | None) -> None:
        owner = self.db.installation_owner(installation_id)
        if owner is not None and owner != user.id:
            raise SetupError(403, NOT_VERIFIED)
        try:
            info = await self.app.installation(installation_id)
        except GitHubError as exc:
            if exc.status == 404:
                raise SetupError(403, NOT_VERIFIED) from None
            raise SetupError(502, "GitHub could not be reached, try again") from None
        if (info.app_id and info.app_id != self.app.app_id) or info.suspended:
            raise SetupError(403, NOT_VERIFIED)
        if self.app.oauth_configured:
            if not code:
                raise SetupError(403, NOT_VERIFIED)
            try:
                mine = await self.app.user_installation_ids(code)
            except GitHubError:
                raise SetupError(403, NOT_VERIFIED) from None
            if installation_id not in mine:
                raise SetupError(403, NOT_VERIFIED)
        elif owner != user.id and info.created_at < issued - CLOCK_SKEW:
            raise SetupError(403, NOT_VERIFIED)

    # --- tokens for the CLI ---

    async def token_for(self, user: Caller, repo: str) -> InstallationToken:
        """A token scoped to `repo` (contents + pull requests) of the user's own installation."""
        installation = self.db.installation_of(user.id)
        if installation is None:
            raise SetupError(403, "Connect GitHub first (the Rook GitHub App is not installed for you)")
        try:
            return await self.app.installation_token(installation, repo)
        except GitHubError as exc:
            if exc.status == 404:
                self._forget(installation, unlink=True)
                raise SetupError(403, "The Rook GitHub App is no longer installed; connect GitHub again") from None
            if exc.status == 422:
                raise SetupError(404, f"{repo} is not shared with the Rook GitHub App") from None
            raise SetupError(502, "GitHub could not be reached, try again") from None

    # --- webhooks ---

    def handle_event(self, event: str, payload: Any) -> str:
        """Act on a verified webhook; returns what was done (for the response, never payload data)."""
        installation = payload.get("installation") if isinstance(payload, dict) else None
        installation_id = installation.get("id") if isinstance(installation, dict) else None
        action = payload.get("action") if isinstance(payload, dict) else None
        if not isinstance(installation_id, int):
            return "ignored"
        if event == "installation" and action == "deleted":
            self._forget(installation_id, unlink=True)
            return "unlinked"
        if event == "installation" and action == "suspend":
            self._forget(installation_id, unlink=False)
            return "suspended"
        if event == "installation_repositories":
            self._repos.pop(installation_id, None)
            return "repos_changed"
        return "ignored"

    def _forget(self, installation_id: int, *, unlink: bool) -> None:
        self.app.forget(installation_id)
        self._repos.pop(installation_id, None)
        if unlink:
            self.db.unbind_installation(installation_id)
