"""`rook login` / `rook logout` (03 §6, 01 FR-C6): sign in with Google through the Rook server.

- Localhost callback (default): a one-shot listener on 127.0.0.1:<random port> and a random `state`; the
  browser goes to `<server>/api/v1/auth/cli/start?port&state`, and the server redirects it back to
  `http://127.0.0.1:<port>/cb?token=…&state=…`. The first `/cb` request ends the listener: a wrong `state`
  is rejected (CSRF), a right one gives the tokens.
- Device code (`--device`), for machines without a browser: open the printed URL anywhere and sign in there.

Credentials go to `~/.rook/credentials.json`, created with mode 600 (the folder 700).
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

DEFAULT_SERVER = "https://44-239-185-88.sslip.io"
API = "/api/v1"
LOGIN_TIMEOUT = 300.0
_SERVER = re.compile(r"(https://[A-Za-z0-9.-]+(:\d{1,5})?|http://(127\.0\.0\.1|localhost)(:\d{1,5})?)")

Echo = Callable[[str], None]


class LoginError(Exception):
    """The sign-in did not finish; the message is safe to show (it never holds a token)."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: int


@dataclass(frozen=True)
class Credentials:
    server: str
    email: str
    access_token: str
    refresh_token: str
    expires_at: int


def server_url(explicit: str | None = None, env: dict[str, str] | None = None) -> str:
    """`--server`, else ROOK_SERVER, else the hosted server; an https origin (http only for localhost)."""
    env = dict(os.environ) if env is None else env
    value = (explicit or env.get("ROOK_SERVER") or DEFAULT_SERVER).strip().rstrip("/")
    if not _SERVER.fullmatch(value):
        raise LoginError(f"the server must be an https origin like {DEFAULT_SERVER}")
    return value


# --- credentials file --------------------------------------------------------------------------------


def save_credentials(path: Path, creds: Credentials) -> None:
    """Write atomically with mode 600: a temp file created 600 (never readable by others), then renamed."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            json.dump(asdict(creds), fh)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_credentials(path: Path) -> Credentials | None:
    """The saved credentials, or None when there are none or the file is not ours."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Credentials(server=str(data["server"]), email=str(data.get("email", "")),
                           access_token=str(data["access_token"]), refresh_token=str(data.get("refresh_token", "")),
                           expires_at=int(data.get("expires_at", 0)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


# --- localhost callback ------------------------------------------------------------------------------

_DONE_PAGE = b"<!doctype html><meta charset=utf-8><title>Rook</title><p>Rook CLI: %s You can close this tab."


def read_callback(path: str, expected_state: str) -> tuple[int, Tokens | LoginError | None]:
    """The HTTP status for one request to the listener, and its outcome (None: not the callback, keep waiting)."""
    parts = urlsplit(path)
    if parts.path != "/cb":
        return 404, None
    query = {k: v[0] for k, v in parse_qs(parts.query, max_num_fields=10).items()}
    if not hmac.compare_digest(query.get("state", "").encode(), expected_state.encode()):
        return 400, LoginError("the sign-in callback had the wrong state (possible CSRF); try again")
    if "error" in query or not query.get("token"):
        return 400, LoginError("the sign-in was cancelled or failed; try again")
    try:
        expires_at = int(query.get("expires_at", "0"))
    except ValueError:
        expires_at = 0
    return 200, Tokens(access_token=query["token"], refresh_token=query.get("refresh_token", ""),
                       expires_at=expires_at)


class LoopbackListener:
    """Listens on 127.0.0.1 (a random port) for the one `/cb` redirect of a sign-in."""

    def __init__(self, state: str) -> None:
        self.state = state
        self.outcome: Tokens | LoginError | None = None
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if listener.outcome is not None:
                    self.send_error(410)
                    return
                status, outcome = read_callback(self.path, listener.state)
                listener.outcome = outcome
                message = b"Signed in." if isinstance(outcome, Tokens) else b"Sign-in failed."
                body = _DONE_PAGE % message if status != 404 else b"Not found"
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return  # the request line holds the token: never log it

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._server.timeout = 0.5
        self.port: int = self._server.server_address[1]

    def wait(self, timeout: float = LOGIN_TIMEOUT, clock: Callable[[], float] = time.monotonic) -> Tokens:
        deadline = clock() + timeout
        try:
            while self.outcome is None:
                if clock() >= deadline:
                    raise LoginError("timed out waiting for the browser sign-in; try `rook login --device`")
                self._server.handle_request()
        finally:
            self._server.server_close()
        if isinstance(self.outcome, LoginError):
            raise self.outcome
        return self.outcome


def login_in_browser(server: str, echo: Echo, open_browser: Callable[[str], Any] = webbrowser.open,
                     timeout: float = LOGIN_TIMEOUT) -> Tokens:
    state = secrets.token_urlsafe(32)
    listener = LoopbackListener(state)
    url = f"{server}{API}/auth/cli/start?{urlencode({'port': listener.port, 'state': state})}"
    echo("Opening your browser to sign in with Google. If it doesn't open, visit:")
    echo(f"  {url}")
    open_browser(url)
    return listener.wait(timeout)


# --- device code -------------------------------------------------------------------------------------


def _json(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 501:
        raise LoginError("sign-in is not configured on this server")
    if response.status_code != 200:
        raise LoginError(f"the server answered HTTP {response.status_code}")
    data = response.json()
    if not isinstance(data, dict):
        raise LoginError("the server sent an unexpected answer")
    return data


def login_with_device_code(server: str, client: httpx.Client, echo: Echo,
                           sleep: Callable[[float], None] = time.sleep,
                           clock: Callable[[], float] = time.monotonic) -> Tokens:
    start = _json(client.post(f"{server}{API}/auth/device/start"))
    try:
        device_code, user_code, url = str(start["device_code"]), str(start["user_code"]), str(start["verification_url"])
        interval = max(1, int(start.get("interval", 5)))
        deadline = clock() + int(start.get("expires_in", 600))
    except (KeyError, ValueError, TypeError):
        raise LoginError("the server sent an unexpected answer") from None
    echo(f"On any device, open {url}")
    echo(f"and check that it shows the code {user_code}, then sign in with Google.")
    while clock() < deadline:
        sleep(interval)
        poll = _json(client.post(f"{server}{API}/auth/device/poll", json={"device_code": device_code}))
        if poll.get("status") == "done" and isinstance(poll.get("token"), str):
            return Tokens(access_token=poll["token"], refresh_token=str(poll.get("refresh_token") or ""),
                          expires_at=int(poll.get("expires_at") or 0))
        if poll.get("status") != "pending":
            break
    raise LoginError("the code expired or the sign-in failed; run `rook login --device` again")


# --- the signed-in user, and sign-out -----------------------------------------------------------------


def fetch_email(server: str, client: httpx.Client, token: str) -> str:
    """`GET /me`: proves the server accepts the token."""
    response = client.get(f"{server}{API}/me", headers={"Authorization": f"Bearer {token}"})
    if response.status_code == 401:
        raise LoginError("the server did not accept the sign-in token")
    return str(_json(response).get("email", ""))


def revoke(server: str, client: httpx.Client, token: str) -> bool:
    """`POST /auth/logout`: best effort, a failure never keeps the credentials on disk."""
    try:
        response = client.post(f"{server}{API}/auth/logout", headers={"Authorization": f"Bearer {token}"})
        return response.status_code == 200 and response.json().get("ok") is True
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def http_client() -> httpx.Client:
    return httpx.Client(timeout=15.0, follow_redirects=False)
