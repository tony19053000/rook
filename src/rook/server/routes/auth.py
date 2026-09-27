"""The CLI sign-in routes of 02 §11 / 03 §6: `/auth/cli/*` (localhost callback), `/auth/device/*` (device code)
and `/auth/logout`.

Both flows use Supabase Google OAuth with PKCE. The server keeps the code verifier; the browser only carries a
signed, short-lived `rook_login` cookie that points at its pending flow, so the OAuth `redirect_to` is the
fixed callback URL (it must match the Supabase redirect allowlist exactly). Tokens go only to the loopback
address the CLI listens on (`127.0.0.1:<port>`) or to the device-code poller.
"""

from __future__ import annotations

import html
import re
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from rook.server.auth import bearer_token
from rook.server.deps import ServerState, State, UserCaller
from rook.server.logins import DEVICE_TTL, FLOW_TTL, LOGIN_COOKIE, LoginFlow
from rook.server.schemas import DevicePoll, DevicePollBody, DeviceStart, Ok
from rook.server.supabase import SupabaseError, SupabaseOAuth, pkce_challenge

router = APIRouter()

COOKIE_PATH = "/api/v1/auth"
CALLBACK_PATH = "/api/v1/auth/cli/callback"
POLL_INTERVAL = 5
_STATE = r"^[A-Za-z0-9_-]{16,128}$"
_USER_CODE = re.compile(r"[A-Z2-9]{4}-[A-Z2-9]{4}")
NOT_CONFIGURED = "Sign-in is not configured on this server"
# Sign-in pages hold nothing but fixed text: no scripts, no external loads, never cached, no referrer.
_PAGE_HEADERS = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'",
                 "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _page(title: str, body_html: str, status: int = 200) -> HTMLResponse:
    page = (f"<!doctype html><html lang=en><head><meta charset=utf-8><title>{html.escape(title)} · Rook</title>"
            "<meta name=viewport content='width=device-width,initial-scale=1'></head>"
            "<body style='font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;"
            f"line-height:1.5'><h1 style='font-weight:500'>{html.escape(title)}</h1>{body_html}</body></html>")
    return HTMLResponse(page, status_code=status, headers=_PAGE_HEADERS)


def _oauth(state: ServerState) -> tuple[SupabaseOAuth, str]:
    """The OAuth client and this server's public URL; 501 when sign-in isn't configured."""
    public_url = state.settings.public_url
    if state.oauth is None or public_url is None:
        raise HTTPException(501, NOT_CONFIGURED)
    return state.oauth, public_url


def _begin(state: ServerState, flow: LoginFlow) -> Response:
    """Remember the flow, set its cookie, and send the browser to Supabase's Google sign-in."""
    oauth, public_url = _oauth(state)
    flow_id = state.logins.start(flow)
    if flow_id is None:
        raise HTTPException(429, "Too many sign-ins in progress, try again in a few minutes",
                            headers={"Retry-After": "60"})
    target = oauth.authorize_url(f"{public_url}{CALLBACK_PATH}", pkce_challenge(flow.verifier))
    response = RedirectResponse(target, status_code=302,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    response.set_cookie(LOGIN_COOKIE, state.logins.cookie_value(flow_id), max_age=int(FLOW_TTL), httponly=True,
                        samesite="lax", secure=state.settings.cookie_secure, path=COOKIE_PATH)
    return response


def _new_verifier() -> str:
    return secrets.token_urlsafe(48)  # 64 chars, within PKCE's 43-128


@router.get("/auth/cli/start")
def cli_start(
    state: State,
    port: Annotated[int, Query(ge=1024, le=65535)],
    login_state: Annotated[str, Query(alias="state", pattern=_STATE)],
) -> Response:
    """Step 1 of `rook login`: the CLI listens on 127.0.0.1:<port> and opens this URL in the browser."""
    return _begin(state, LoginFlow(verifier=_new_verifier(), kind="cli", port=port, state=login_state))


@router.get("/auth/cli/callback")
async def cli_callback(
    request: Request,
    state: State,
    code: Annotated[str | None, Query(max_length=512)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    """Supabase sends the browser here with `?code=`; the code is exchanged (with the verifier) for tokens."""
    oauth, _ = _oauth(state)
    response: Response
    flow = state.logins.take(state.logins.flow_id_from_cookie(request.cookies.get(LOGIN_COOKIE)))
    if flow is None:
        response = _page("Sign-in expired", "<p>This sign-in link is no longer valid. Start again from your "
                         "terminal with <code>rook login</code>.</p>", 400)
        response.delete_cookie(LOGIN_COOKIE, path=COOKIE_PATH)
        return response
    tokens = None
    if code and not error:
        try:
            tokens = await oauth.exchange(code, flow.verifier)
        except SupabaseError:
            tokens = None
    if flow.kind == "cli":
        query = ({"token": tokens.access_token, "refresh_token": tokens.refresh_token,
                  "expires_at": str(tokens.expires_at), "state": flow.state} if tokens is not None
                 else {"error": "sign_in_failed", "state": flow.state})
        response = RedirectResponse(f"http://127.0.0.1:{flow.port}/cb?{urlencode(query)}", status_code=302,
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    elif tokens is not None and state.logins.complete_device(flow.user_code, tokens):
        response = _page("Signed in", "<p>The Rook CLI is signed in. You can close this tab and go back to "
                         "your terminal.</p>")
    else:
        state.logins.fail_device(flow.user_code)
        response = _page("Sign-in failed", "<p>Start again from your terminal with "
                         "<code>rook login --device</code>.</p>", 400)
    response.delete_cookie(LOGIN_COOKIE, path=COOKIE_PATH)
    return response


@router.post("/auth/device/start", response_model=DeviceStart)
def device_start(state: State) -> DeviceStart:
    """For machines without a browser: the user opens `verification_url` on any device and signs in."""
    _, public_url = _oauth(state)
    device = state.logins.new_device()
    if device is None:
        raise HTTPException(429, "Too many sign-ins in progress, try again in a few minutes",
                            headers={"Retry-After": "60"})
    url = f"{public_url}/api/v1/auth/device/verify?{urlencode({'code': device.user_code})}"
    return DeviceStart(device_code=device.device_code, user_code=device.user_code, verification_url=url,
                       expires_in=int(DEVICE_TTL), interval=POLL_INTERVAL)


@router.get("/auth/device/verify")
def device_verify(
    state: State,
    code: Annotated[str, Query(max_length=20)],
    confirm: Annotated[bool, Query()] = False,
) -> Response:
    """A confirmation page first (the code must match the terminal: a stranger's link can't sign you in
    unnoticed); `confirm=1` starts the Google sign-in for that code, once."""
    _oauth(state)
    user_code = code.strip().upper()
    if not _USER_CODE.fullmatch(user_code) or state.logins.device_for_user_code(user_code) is None:
        return _page("Code not valid", "<p>This code is unknown, expired or already used. Run "
                     "<code>rook login --device</code> again.</p>", 404)
    if not confirm:
        shown = html.escape(user_code)
        link = html.escape(f"?{urlencode({'code': user_code, 'confirm': 1})}")
        return _page("Sign in the Rook CLI?",
                     f"<p>Your terminal should show the code <strong><code>{shown}</code></strong>.</p>"
                     "<p>Continue only if you ran <code>rook login --device</code> yourself and the codes match. "
                     "Otherwise close this tab.</p>"
                     f"<p><a href='{link}'>Continue with Google</a></p>")
    if not state.logins.claim_device(user_code):
        return _page("Code not valid", "<p>This code was already used. Run <code>rook login --device</code> "
                     "again.</p>", 404)
    return _begin(state, LoginFlow(verifier=_new_verifier(), kind="device", user_code=user_code))


@router.post("/auth/device/poll", response_model=DevicePoll, response_model_exclude_none=True)
def device_poll(body: DevicePollBody, state: State) -> DevicePoll:
    _oauth(state)
    status, tokens = state.logins.poll(body.device_code)
    if tokens is None:
        return DevicePoll(status=status)
    return DevicePoll(status=status, token=tokens.access_token, refresh_token=tokens.refresh_token,
                      expires_at=tokens.expires_at)


@router.post("/auth/logout", response_model=Ok)
async def logout(request: Request, caller: UserCaller, state: State) -> Ok:
    """`rook logout`: revoke the caller's Supabase session (its refresh token stops working)."""
    oauth, _ = _oauth(state)
    token = bearer_token(request)
    return Ok(ok=token is not None and await oauth.logout(token))
