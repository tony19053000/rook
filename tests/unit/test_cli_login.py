"""ROOK-030: `rook login` (localhost callback with a state check, device code), the credentials file (mode 600)
and `rook logout`. The loopback listener is real (127.0.0.1); the server is an httpx MockTransport."""

from __future__ import annotations

import json
import stat
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from typer.testing import CliRunner

from rook.cli import login as auth
from rook.cli import main as cli_main
from rook.cli.main import app
from rook.cli.tui.auth import SavedAuth

runner = CliRunner()
SERVER = "https://rook.example.app"
CREDS = auth.Credentials(server=SERVER, email="owner@example.com", access_token="acc", refresh_token="ref",
                         expires_at=2_000_000_000)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --- credentials file ------------------------------------------------------------------------------------


def test_credentials_are_saved_with_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "home" / ".rook" / "credentials.json"
    auth.save_credentials(path, CREDS)
    assert mode(path) == 0o600 and mode(path.parent) == 0o700
    assert auth.load_credentials(path) == CREDS
    assert [p.name for p in path.parent.iterdir()] == ["credentials.json"]  # no temp file left


def test_saving_over_a_readable_file_makes_it_600(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text("{}")
    path.chmod(0o644)
    auth.save_credentials(path, CREDS)
    assert mode(path) == 0o600 and json.loads(path.read_text())["access_token"] == "acc"


def test_saving_replaces_a_symlink_instead_of_writing_through_it(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    path = tmp_path / "credentials.json"
    path.symlink_to(outside)
    assert auth.load_credentials(path) is None
    auth.save_credentials(path, CREDS)
    assert outside.read_text() == "keep" and not path.is_symlink() and mode(path) == 0o600


def test_broken_credentials_read_as_none(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text("not json")
    assert auth.load_credentials(path) is None
    assert auth.load_credentials(tmp_path / "missing.json") is None


# --- the localhost callback ------------------------------------------------------------------------------

STATE = "s" * 43


def test_read_callback_checks_the_state() -> None:
    status, outcome = auth.read_callback(f"/cb?token=t&refresh_token=r&expires_at=5&state={'x' * 43}", STATE)
    assert status == 400 and isinstance(outcome, auth.LoginError) and "state" in str(outcome)
    status, outcome = auth.read_callback("/cb?token=t", STATE)  # no state at all
    assert status == 400 and isinstance(outcome, auth.LoginError)
    status, outcome = auth.read_callback(f"/cb?token=t&refresh_token=r&expires_at=5&state={STATE}", STATE)
    assert status == 200 and outcome == auth.Tokens("t", "r", 5)
    assert auth.read_callback(f"/cb?error=sign_in_failed&state={STATE}", STATE)[0] == 400
    assert auth.read_callback("/favicon.ico", STATE) == (404, None)


def _hit(url: str) -> httpx.Response:
    return httpx.get(url, timeout=5)


def test_the_listener_rejects_a_bad_state_and_closes(tmp_path: Path) -> None:
    listener = auth.LoopbackListener(STATE)
    base = f"http://127.0.0.1:{listener.port}"
    responses: list[httpx.Response] = []

    def browser() -> None:
        responses.append(_hit(f"{base}/favicon.ico"))  # ignored, the listener keeps waiting
        responses.append(_hit(f"{base}/cb?token=stolen&state=wrong"))

    thread = threading.Thread(target=browser)
    thread.start()
    with pytest.raises(auth.LoginError, match="wrong state"):
        listener.wait(timeout=10)
    thread.join()
    assert [r.status_code for r in responses] == [404, 400]
    with pytest.raises(httpx.ConnectError):  # exactly one callback: the port is closed now
        _hit(f"{base}/cb?token=t&state={STATE}")


def test_login_in_browser_gets_the_tokens_from_the_loopback() -> None:
    opened: list[str] = []
    replies: list[httpx.Response] = []

    def open_browser(url: str) -> None:
        opened.append(url)
        query = parse_qs(urlsplit(url).query)
        port, state = query["port"][0], query["state"][0]
        # stands in for the server's redirect to http://127.0.0.1:<port>/cb
        target = f"http://127.0.0.1:{port}/cb?token=acc&refresh_token=ref&expires_at=9&state={state}"
        threading.Thread(target=lambda: replies.append(_hit(target))).start()

    lines: list[str] = []
    tokens = auth.login_in_browser(SERVER, lines.append, open_browser=open_browser, timeout=10)
    assert tokens == auth.Tokens("acc", "ref", 9)
    (url,) = opened
    assert url.startswith(f"{SERVER}/api/v1/auth/cli/start?port=")
    assert len(parse_qs(urlsplit(url).query)["state"][0]) >= 32
    assert url in "\n".join(lines)


def test_the_listener_times_out() -> None:
    ticks = iter([0.0, 0.0, 1000.0])
    listener = auth.LoopbackListener(STATE)
    with pytest.raises(auth.LoginError, match="timed out"):
        listener.wait(timeout=5, clock=lambda: next(ticks))


# --- device code -----------------------------------------------------------------------------------------


def mock_server(polls: list[dict[str, Any]], seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/auth/device/start":
            return httpx.Response(200, json={"device_code": "d" * 40, "user_code": "ABCD-EFGH", "interval": 5,
                                             "expires_in": 600,
                                             "verification_url": f"{SERVER}/api/v1/auth/device/verify?code=ABCD-EFGH"})
        if request.url.path == "/api/v1/auth/device/poll":
            return httpx.Response(200, json=polls.pop(0))
        if request.url.path == "/api/v1/me":
            if request.headers.get("authorization") != "Bearer acc":
                return httpx.Response(401, json={"detail": "no"})
            return httpx.Response(200, json={"id": "u", "email": "owner@example.com", "github_connected": False})
        if request.url.path == "/api/v1/auth/logout":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_device_code_polls_until_done() -> None:
    seen: list[httpx.Request] = []
    client = mock_server([{"status": "pending"}, {"status": "done", "token": "acc", "refresh_token": "ref",
                                                  "expires_at": 7}], seen)
    lines: list[str] = []
    sleeps: list[float] = []
    tokens = auth.login_with_device_code(SERVER, client, lines.append, sleep=sleeps.append, clock=lambda: 0.0)
    assert tokens == auth.Tokens("acc", "ref", 7) and sleeps == [5, 5]
    assert "ABCD-EFGH" in "\n".join(lines)
    assert json.loads(seen[1].content) == {"device_code": "d" * 40}


def test_device_code_stops_when_expired() -> None:
    client = mock_server([{"status": "expired"}], [])
    with pytest.raises(auth.LoginError, match="expired"):
        auth.login_with_device_code(SERVER, client, lambda _: None, sleep=lambda _: None, clock=lambda: 0.0)


def test_server_url_validation() -> None:
    assert auth.server_url(None, {}) == auth.DEFAULT_SERVER
    assert auth.server_url(None, {"ROOK_SERVER": "http://127.0.0.1:8000/"}) == "http://127.0.0.1:8000"
    for bad in ("http://rook.example.app", "https://x.io/path", "file:///etc/passwd"):
        with pytest.raises(auth.LoginError):
            auth.server_url(bad, {})


# --- the commands ----------------------------------------------------------------------------------------


@pytest.fixture
def creds_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".rook" / "credentials.json"
    monkeypatch.setattr(cli_main, "CREDENTIALS", path)
    return path


def test_rook_login_saves_the_credentials_600(creds_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []
    monkeypatch.setattr(auth, "http_client", lambda: mock_server([], seen))
    monkeypatch.setattr(auth, "login_in_browser", lambda server, echo: auth.Tokens("acc", "ref", 9))
    result = runner.invoke(app, ["login", "--server", SERVER])
    assert result.exit_code == 0, result.output
    assert "Signed in as owner@example.com" in result.output and "acc" not in result.output
    assert mode(creds_path) == 0o600
    assert auth.load_credentials(creds_path) == auth.Credentials(SERVER, "owner@example.com", "acc", "ref", 9)


def test_rook_login_device_and_a_refused_token(creds_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "http_client", lambda: mock_server([], []))
    monkeypatch.setattr(auth, "login_with_device_code",
                        lambda server, client, echo: auth.Tokens("not-accepted", "", 0))
    result = runner.invoke(app, ["login", "--device", "--server", SERVER])
    assert result.exit_code == 1 and "did not accept" in result.output and not creds_path.exists()


def test_rook_login_reports_a_failed_sign_in(creds_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(server: str, echo: Any) -> auth.Tokens:
        raise auth.LoginError("the sign-in callback had the wrong state (possible CSRF); try again")

    monkeypatch.setattr(auth, "login_in_browser", fail)
    result = runner.invoke(app, ["login", "--server", SERVER])
    assert result.exit_code == 1 and "wrong state" in result.output and not creds_path.exists()


def test_rook_logout_revokes_and_deletes(creds_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth.save_credentials(creds_path, CREDS)
    seen: list[httpx.Request] = []
    monkeypatch.setattr(auth, "http_client", lambda: mock_server([], seen))
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0 and result.output.strip() == "Signed out: removed the saved credentials."
    assert not creds_path.exists()
    (request,) = seen
    assert request.url.path == "/api/v1/auth/logout" and request.headers["authorization"] == "Bearer acc"


def test_rook_logout_deletes_even_when_the_server_is_down(creds_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth.save_credentials(creds_path, CREDS)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(down)))
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0 and "could not be revoked" in result.output and not creds_path.exists()


def test_the_shell_shows_the_saved_sign_in(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    assert not SavedAuth(path).state().signed_in
    auth.save_credentials(path, CREDS)
    assert SavedAuth(path).state().user == "owner@example.com"
