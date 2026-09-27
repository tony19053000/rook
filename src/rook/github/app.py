"""The GitHub App's side of the GitHub API (ROOK-031, 03 §6): the App JWT, installation tokens, installation
lookups and the optional OAuth check that an installation belongs to the user.

- The App JWT is RS256, signed with GITHUB_APP_PRIVATE_KEY (iat 60 s in the past for clock drift, exp 9 min).
- Installation tokens (1 hour) are cached in memory per (installation, repos) and handed out only while at
  least `min_remaining` seconds are left. Every token is registered with the redaction filter as soon as it
  is received and is never logged.
- Calls go only to the configured API origin (`https://api.github.com`) and, for the OAuth code exchange, to the
  configured web origin (`https://github.com`). No redirects are followed.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import jwt

from rook.core.events import register_secret

API_VERSION = "2022-11-28"
USER_AGENT = "rook-invariants"
JWT_LIFETIME = 540  # GitHub allows at most 10 minutes
JWT_BACKDATE = 60
TOKEN_MIN_REMAINING = 30 * 60.0
MAX_PAGES = 5
PER_PAGE = 100


_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
_NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}")


def valid_repo(ref: str) -> bool:
    """`owner/name` as GitHub allows it (so it is safe inside an API path or a clone URL)."""
    owner, _, name = ref.partition("/")
    return bool(_OWNER.fullmatch(owner) and _NAME.fullmatch(name) and name not in (".", ".."))


class GitHubError(RuntimeError):
    """A GitHub call failed. The message never holds a token or a key; `status` is GitHub's HTTP status."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: float  # unix seconds


@dataclass(frozen=True)
class Installation:
    id: int
    app_id: int
    account: str
    created_at: float  # unix seconds
    suspended: bool


@dataclass(frozen=True)
class Repo:
    full_name: str
    private: bool
    language: str
    default_branch: str


def load_private_key(pem: str) -> str:
    """The PEM as the server sees it; a key stored with literal `\\n` escapes is turned back into lines."""
    pem = pem.strip()
    if "\n" not in pem and "\\n" in pem:
        pem = pem.replace("\\n", "\n")
    return pem


def app_jwt(app_id: int, private_key: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    claims = {"iat": int(now) - JWT_BACKDATE, "exp": int(now) + JWT_LIFETIME, "iss": str(app_id)}
    return jwt.encode(claims, private_key, algorithm="RS256")


def _timestamp(value: Any) -> float:
    if not isinstance(value, str):
        raise GitHubError("GitHub sent an unexpected answer")
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        raise GitHubError("GitHub sent an unexpected answer") from None


def to_repo(item: Any) -> Repo | None:
    if not isinstance(item, dict) or not isinstance(item.get("full_name"), str):
        return None
    language, branch = item.get("language"), item.get("default_branch")
    return Repo(full_name=item["full_name"], private=item.get("private") is True,
                language=language if isinstance(language, str) else "",
                default_branch=branch if isinstance(branch, str) else "main")


class GitHubApi:
    """A small async GitHub REST client for one origin; `token` is sent as `Bearer`."""

    def __init__(self, api_url: str = "https://api.github.com", transport: httpx.AsyncBaseTransport | None = None,
                 timeout: float = 15.0) -> None:
        self.api_url = api_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout, follow_redirects=False)

    async def call(self, method: str, path: str, token: str, *, json: dict[str, Any] | None = None,
                   params: dict[str, Any] | None = None, expect: tuple[int, ...] = (200,)) -> Any:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
        try:
            async with self.client() as client:
                response = await client.request(method, f"{self.api_url}{path}", headers=headers, json=json,
                                                params=params)
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub is unreachable ({type(exc).__name__})") from None
        if response.status_code not in expect:
            raise GitHubError(f"GitHub answered HTTP {response.status_code} to {method} {path.split('?')[0]}",
                              response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise GitHubError("GitHub sent an unexpected answer") from None


class GitHubApp:
    """The App: JWT, installation tokens (cached), installation details, installation repos, OAuth check."""

    def __init__(self, app_id: int, private_key: str, *, api_url: str = "https://api.github.com",
                 web_url: str = "https://github.com", client_id: str | None = None,
                 client_secret: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.app_id = app_id
        self._key = load_private_key(private_key)
        register_secret(self._key)
        self.api = GitHubApi(api_url, transport)
        self.web_url = web_url.rstrip("/")
        self.client_id = client_id
        self._client_secret = client_secret
        register_secret(client_secret)
        self._transport = transport
        self._clock = clock
        self._tokens: dict[tuple[int, str | None], InstallationToken] = {}
        self._lock = asyncio.Lock()

    @property
    def oauth_configured(self) -> bool:
        return bool(self.client_id and self._client_secret)

    def jwt(self) -> str:
        return app_jwt(self.app_id, self._key, self._clock())

    async def installation(self, installation_id: int) -> Installation:
        """`GET /app/installations/{id}`: only installations of this App exist (404 for any other id)."""
        data = await self.api.call("GET", f"/app/installations/{installation_id}", self.jwt())
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise GitHubError("GitHub sent an unexpected answer")
        raw_account = data.get("account")
        account: dict[str, Any] = raw_account if isinstance(raw_account, dict) else {}
        return Installation(id=data["id"], app_id=int(data.get("app_id") or 0),
                            account=str(account.get("login") or ""), created_at=_timestamp(data.get("created_at")),
                            suspended=data.get("suspended_at") is not None)

    async def installation_token(self, installation_id: int, repo: str | None = None,
                                 min_remaining: float = TOKEN_MIN_REMAINING) -> InstallationToken:
        """A token for the installation (all its repos), or for one `owner/name` only (least privilege).
        Cached until fewer than `min_remaining` seconds are left."""
        key = (installation_id, repo.lower() if repo else None)
        async with self._lock:
            cached = self._tokens.get(key)
            if cached is not None and cached.expires_at - self._clock() >= min_remaining:
                return cached
            body: dict[str, Any] | None = None
            if repo is not None:
                body = {"repositories": [repo.split("/", 1)[1]],
                        "permissions": {"contents": "write", "pull_requests": "write", "metadata": "read"}}
            data = await self.api.call("POST", f"/app/installations/{installation_id}/access_tokens", self.jwt(),
                                       json=body, expect=(201,))
            if not isinstance(data, dict) or not isinstance(data.get("token"), str):
                raise GitHubError("GitHub sent an unexpected token answer")
            register_secret(data["token"])
            token = InstallationToken(token=data["token"], expires_at=_timestamp(data.get("expires_at")))
            self._tokens = {k: v for k, v in self._tokens.items() if v.expires_at > self._clock()}
            self._tokens[key] = token
            return token

    def forget(self, installation_id: int) -> None:
        """Drop the cached tokens of an installation (it was deleted or suspended)."""
        self._tokens = {k: v for k, v in self._tokens.items() if k[0] != installation_id}

    async def repos(self, installation_id: int) -> list[Repo]:
        """The repos the user shared with the App (`GET /installation/repositories`, at most 500)."""
        token = (await self.installation_token(installation_id, min_remaining=60.0)).token
        out: list[Repo] = []
        for page in range(1, MAX_PAGES + 1):
            data = await self.api.call("GET", "/installation/repositories", token,
                                       params={"per_page": PER_PAGE, "page": page})
            items = data.get("repositories") if isinstance(data, dict) else None
            if not isinstance(items, list):
                raise GitHubError("GitHub sent an unexpected answer")
            out.extend(r for r in map(to_repo, items) if r is not None)
            if len(items) < PER_PAGE:
                break
        return out

    async def user_installation_ids(self, code: str) -> set[int]:
        """The OAuth check: exchange the setup `code` for a user token, then list the installations of this
        App that the GitHub user can access (`GET /user/installations`). The user token is then dropped."""
        if not self.oauth_configured:
            raise GitHubError("the GitHub OAuth client is not configured")
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=15.0, follow_redirects=False) as client:
                response = await client.post(f"{self.web_url}/login/oauth/access_token",
                                             headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                                             data={"client_id": self.client_id, "client_secret": self._client_secret,
                                                   "code": code})
        except httpx.HTTPError as exc:
            raise GitHubError(f"GitHub is unreachable ({type(exc).__name__})") from None
        try:
            data = response.json()
        except ValueError:
            data = None
        user_token = data.get("access_token") if isinstance(data, dict) else None
        if response.status_code != 200 or not isinstance(user_token, str) or not user_token:
            raise GitHubError("GitHub refused the authorization code", response.status_code)
        register_secret(user_token)
        ids: set[int] = set()
        for page in range(1, MAX_PAGES + 1):
            listing = await self.api.call("GET", "/user/installations", user_token,
                                          params={"per_page": PER_PAGE, "page": page})
            items = listing.get("installations") if isinstance(listing, dict) else None
            if not isinstance(items, list):
                raise GitHubError("GitHub sent an unexpected answer")
            ids.update(i["id"] for i in items
                       if isinstance(i, dict) and isinstance(i.get("id"), int) and i.get("app_id") in (None, self.app_id))
            if len(items) < PER_PAGE:
                break
        return ids
