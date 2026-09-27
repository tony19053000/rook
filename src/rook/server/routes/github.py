"""`/github/*` (02 §11, 03 §6, ROOK-031): the install URL, the setup callback, CLI tokens and the webhook.

Every route answers 501 when the GitHub App is not configured on this server. The webhook is the only route
without a user: it is authenticated by its HMAC-SHA256 signature (`X-Hub-Signature-256`, GITHUB_WEBHOOK_SECRET),
compared in constant time over the raw body before the body is parsed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from rook.server.deps import ServerState, State, UserCaller
from rook.server.github_link import AppGitHub, SetupError
from rook.server.schemas import GitHubToken, GitHubTokenBody, InstallUrl, Ok

router = APIRouter()

NOT_CONFIGURED = "GitHub is not configured on this server"


def _github(state: ServerState) -> AppGitHub:
    if not isinstance(state.github, AppGitHub):
        raise HTTPException(501, NOT_CONFIGURED)
    return state.github


def signature_ok(secret: str, body: bytes, header: str | None) -> bool:
    """`sha256=<hex HMAC-SHA256(body)>`, constant-time."""
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.strip().encode())


@router.get("/github/install-url", response_model=InstallUrl)
def install_url(caller: UserCaller, state: State) -> InstallUrl:
    url = _github(state).install_url(caller)
    if url is None:
        raise HTTPException(429, "Too many GitHub connections in progress, try again in a few minutes",
                            headers={"Retry-After": "60"})
    return InstallUrl(url=url)


@router.get("/github/callback", response_model=Ok)
async def callback(
    caller: UserCaller,
    state: State,
    installation_id: Annotated[int, Query(ge=1, le=2**53)],
    setup_state: Annotated[str, Query(alias="state", pattern=r"^[A-Za-z0-9_-]{20,100}$")],
    setup_action: Annotated[str | None, Query(max_length=20)] = None,
    code: Annotated[str | None, Query(max_length=200, pattern=r"^[A-Za-z0-9_-]+$")] = None,
) -> Ok:
    """The web's setup page calls this with GitHub's query (`installation_id`, `state`, `setup_action`, `code`)."""
    try:
        await _github(state).complete_setup(caller, installation_id, setup_state, code)
    except SetupError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    return Ok(ok=True)


@router.post("/github/token", response_model=GitHubToken)
async def token(body: GitHubTokenBody, caller: UserCaller, state: State, response: Response) -> GitHubToken:
    """A token for one repo of the caller's own installation, for the CLI (clone, push, PR). Never cached
    by a proxy, never logged."""
    try:
        minted = await _github(state).token_for(caller, body.repo)
    except SetupError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    response.headers["Cache-Control"] = "no-store"
    return GitHubToken(token=minted.token, expires_at=int(minted.expires_at), repo=body.repo)


@router.post("/github/webhook", response_model=Ok)
async def webhook(
    request: Request,
    state: State,
    x_hub_signature_256: Annotated[str | None, Header()] = None,
    x_github_event: Annotated[str | None, Header()] = None,
) -> Ok:
    github = _github(state)
    secret = state.settings.github_webhook_secret
    if secret is None:
        raise HTTPException(501, "The GitHub webhook secret is not configured on this server")
    body = await request.body()
    if not signature_ok(secret.get_secret_value(), body, x_hub_signature_256):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Invalid webhook body") from None
    github.handle_event(x_github_event or "", payload)
    return Ok(ok=True)
