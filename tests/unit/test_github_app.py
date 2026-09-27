"""ROOK-031: the GitHub App. App JWT, installation tokens (cached, redacted), repo listing, the install URL and
setup callback (forged state, someone else's installation, OAuth proof), `/github/token`, the webhook signature,
the push + PR shipper and the CLI token fetch. GitHub is an httpx MockTransport; no network, no real keys."""

from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from server_helpers import ALICE, BOB, client_for, guest_headers, make_app, state_of

from rook.cli.github import GitHubTokenError, ServerTokens
from rook.cli.login import Credentials, save_credentials
from rook.core.events import REDACTED, clear_secrets, redact_text
from rook.core.workspace import RepoSpec, ShipRequest, git, prepare_workspace
from rook.github.app import GitHubApp, GitHubError, app_jwt, load_private_key
from rook.github.pr import FOOTER, GitHubShipper, pr_body
from rook.server.config import ServerSettings
from rook.server.github_link import AppGitHub, InstallStates

API = "https://api.github.com"
WEB = "https://github.com"
APP_ID = 5093123
HOOK_SECRET = "hook-secret-for-tests-" + "h" * 20
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = _KEY.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                         serialization.NoEncryption()).decode()
PUBLIC = _KEY.public_key()


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGitHub:
    """A MockTransport handler: installations of the App, access tokens, repos, OAuth and PRs."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.installations: dict[int, dict[str, Any]] = {}
        self.repos: dict[int, list[dict[str, Any]]] = {}
        self.user_installs: dict[str, list[int]] = {}  # OAuth code -> installation ids of that GitHub user
        self.minted = 0
        self.token_status = 201

    def install(self, installation_id: int, created: float | None = None, **extra: Any) -> None:
        self.installations[installation_id] = {
            "id": installation_id, "app_id": APP_ID, "account": {"login": f"user{installation_id}"},
            "created_at": iso(time.time() if created is None else created), "suspended_at": None, **extra}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        auth = request.headers.get("authorization", "")
        if path.startswith("/app/"):
            claims = jwt.decode(auth.removeprefix("Bearer "), PUBLIC, algorithms=["RS256"], leeway=3600)
            assert claims["iss"] == str(APP_ID)
        parts = path.strip("/").split("/")
        if parts[:2] == ["app", "installations"] and len(parts) == 3:
            found = self.installations.get(int(parts[2]))
            return httpx.Response(200, json=found) if found else httpx.Response(404, json={"message": "Not Found"})
        if parts[:2] == ["app", "installations"] and parts[3:] == ["access_tokens"]:
            if int(parts[2]) not in self.installations:
                return httpx.Response(404, json={})
            if self.token_status != 201:
                return httpx.Response(self.token_status, json={})
            self.minted += 1
            return httpx.Response(201, json={"token": f"ghs_minted{self.minted:04d}xyzXYZ",
                                             "expires_at": iso(time.time() + 3600)})
        if path == "/installation/repositories":
            assert auth.startswith("Bearer ghs_minted")  # an installation token, not the App JWT
            page = int(request.url.params["page"])
            items = next(iter(self.repos.values()), [])
            chunk = items[(page - 1) * 100: page * 100]
            return httpx.Response(200, json={"total_count": len(items), "repositories": chunk})
        if path == "/login/oauth/access_token":
            form = parse_qs(request.content.decode())
            code = form["code"][0]
            if code not in self.user_installs or form["client_secret"] != ["client-secret-xyz-123"]:
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": f"ghu_user{code}"})
        if path == "/user/installations":
            code = auth.removeprefix("Bearer ghu_user")
            ids = self.user_installs.get(code, [])
            return httpx.Response(200, json={"installations": [{"id": i, "app_id": APP_ID} for i in ids]})
        return httpx.Response(404, json={})


def github_app(fake: FakeGitHub, **kwargs: Any) -> GitHubApp:
    return GitHubApp(APP_ID, PEM, api_url=API, web_url=WEB, transport=httpx.MockTransport(fake), **kwargs)


# --- App JWT and installation tokens ---


def test_the_app_jwt_is_rs256_signed_by_the_app_key_and_short_lived() -> None:
    now = 1_800_000_000.0
    token = app_jwt(APP_ID, PEM, now)
    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    claims = jwt.decode(token, PUBLIC, algorithms=["RS256"], options={"verify_exp": False, "verify_iat": False})
    assert claims["iss"] == str(APP_ID)
    assert claims["iat"] == int(now) - 60 and claims["exp"] - int(now) <= 600
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, other, algorithms=["RS256"], options={"verify_exp": False})


def test_a_key_stored_with_escaped_newlines_is_restored() -> None:
    assert load_private_key(PEM.strip().replace("\n", "\\n")) == PEM.strip()
    assert load_private_key(PEM) == PEM.strip()


async def test_installation_tokens_are_scoped_cached_and_redacted() -> None:
    fake = FakeGitHub()
    fake.install(42)
    app = github_app(fake)
    first = await app.installation_token(42, "acme/shop")
    again = await app.installation_token(42, "ACME/shop")
    assert first == again and fake.minted == 1  # cached
    body = json.loads(fake.requests[0].content)
    assert body == {"repositories": ["shop"],
                    "permissions": {"contents": "write", "pull_requests": "write", "metadata": "read"}}
    assert redact_text(f"token={first.token}") == f"token={REDACTED}"  # registered with the redaction filter
    assert redact_text(PEM).strip() == REDACTED
    whole = await app.installation_token(42)
    assert whole.token != first.token and fake.minted == 2  # another scope, another token
    assert fake.requests[-1].content == b""
    app.forget(42)
    await app.installation_token(42, "acme/shop")
    assert fake.minted == 3


async def test_a_cached_token_is_replaced_when_too_little_time_is_left() -> None:
    fake = FakeGitHub()
    fake.install(42)
    now = [time.time()]
    app = github_app(fake, clock=lambda: now[0])
    await app.installation_token(42, "acme/shop")
    now[0] += 31 * 60  # under 30 minutes left
    await app.installation_token(42, "acme/shop")
    assert fake.minted == 2


async def test_github_errors_carry_the_status_and_never_the_token() -> None:
    fake = FakeGitHub()
    app = github_app(fake)
    with pytest.raises(GitHubError) as info:
        await app.installation_token(99)
    assert info.value.status == 404 and "Bearer" not in str(info.value) and "eyJ" not in str(info.value)


async def test_repo_listing_pages_through_the_installation_repos() -> None:
    fake = FakeGitHub()
    fake.install(42)
    fake.repos[42] = [{"full_name": f"acme/r{i}", "private": i % 2 == 0, "language": "Go" if i else None}
                      for i in range(150)] + [{"bad": True}]
    repos = await github_app(fake).repos(42)
    assert len(repos) == 150 and repos[0].language == "" and repos[1].language == "Go" and repos[0].private
    pages = [r.url.params["page"] for r in fake.requests if r.url.path == "/installation/repositories"]
    assert pages == ["1", "2"]


# --- server routes: install URL and setup callback ---


def settings_for(**extra: Any) -> dict[str, Any]:
    return {"github_app_id": APP_ID, "github_app_private_key": PEM, "github_webhook_secret": HOOK_SECRET, **extra}


def gh_app(tmp_path: Path, fake: FakeGitHub, **extra: Any) -> Any:
    return make_app(tmp_path, github_transport=httpx.MockTransport(fake), **settings_for(**extra))


async def start_install(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get("/api/v1/github/install-url", headers=headers)
    assert response.status_code == 200, response.text
    url = urlsplit(response.json()["url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == "https://github.com/apps/rook-invariants/installations/new"
    return parse_qs(url.query)["state"][0]


async def callback(client: httpx.AsyncClient, headers: dict[str, str], installation_id: int, state: str,
                   **extra: str) -> httpx.Response:
    params = {"installation_id": str(installation_id), "setup_action": "install", "state": state, **extra}
    return await client.get("/api/v1/github/callback", params=params, headers=headers)


def test_settings_read_the_github_env() -> None:
    settings = ServerSettings.from_env({"GITHUB_APP_ID": "5093123", "GITHUB_APP_PRIVATE_KEY": PEM,
                                        "GITHUB_WEBHOOK_SECRET": HOOK_SECRET, "GITHUB_CLIENT_ID": "Iv1.abc",
                                        "GITHUB_CLIENT_SECRET": "client-secret-xyz-123"})
    assert settings.github_app_id == APP_ID and settings.github_app_slug == "rook-invariants"
    assert settings.github_app_configured and settings.github_client_id == "Iv1.abc"
    assert HOOK_SECRET not in repr(settings) and "client-secret" not in repr(settings)
    with pytest.raises(ValueError):
        ServerSettings.from_env({"GITHUB_APP_SLUG": "Bad Slug/../x"})


async def test_github_routes_answer_501_without_the_app(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with client_for(app) as client:
        assert (await client.get("/api/v1/github/install-url", headers=ALICE)).status_code == 501
        assert (await client.post("/api/v1/github/token", json={"repo": "a/b"}, headers=ALICE)).status_code == 501
        assert (await client.post("/api/v1/github/webhook", content=b"{}")).status_code == 501


async def test_a_fresh_install_links_the_user_and_lists_their_repos(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        _, guest = guest_headers(app)
        assert (await client.get("/api/v1/github/install-url", headers=guest)).status_code == 401
        state = await start_install(client, ALICE)
        fake.install(4242)
        fake.repos[4242] = [{"full_name": "alice/shop", "private": True, "language": "TypeScript"}]
        response = await callback(client, ALICE, 4242, state)
        assert response.status_code == 200 and response.json() == {"ok": True}
        me = await client.get("/api/v1/me", headers=ALICE)
        assert me.json()["github_connected"] is True
        repos = (await client.get("/api/v1/repos", headers=ALICE)).json()
        assert repos[0] == {"kind": "github", "ref": "alice/shop", "name": "shop", "private": True,
                            "language": "TypeScript"}
        assert (await client.get("/api/v1/me", headers=BOB)).json()["github_connected"] is False
        assert [r["kind"] for r in (await client.get("/api/v1/repos", headers=BOB)).json()] == ["demo"]
        # the state is one-time
        assert (await callback(client, ALICE, 4242, state)).status_code == 400


async def test_a_forged_or_foreign_state_is_refused(tmp_path: Path) -> None:
    fake = FakeGitHub()
    fake.install(4242)
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        forged = await callback(client, ALICE, 4242, "x" * 43)
        assert forged.status_code == 400 and "expired" in forged.json()["detail"]
        bobs = await start_install(client, BOB)
        assert (await callback(client, ALICE, 4242, bobs)).status_code == 400  # CSRF: not Alice's state
        assert (await callback(client, BOB, 4242, bobs)).status_code == 400  # and it was used up
        assert (await client.get("/api/v1/github/callback", params={"installation_id": "4242", "state": "short"},
                                 headers=ALICE)).status_code == 400
        assert not state_of(app).db.installation_of("u_alice")


async def test_someone_elses_installation_can_not_be_claimed(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        state = await start_install(client, BOB)
        fake.install(7)
        assert (await callback(client, BOB, 7, state)).status_code == 200
        # Alice guesses Bob's installation id: it is already linked to Bob
        state = await start_install(client, ALICE)
        response = await callback(client, ALICE, 7, state)
        assert response.status_code == 403 and "could not verify" in response.json()["detail"]
        # an installation made before Alice's flow started (someone else's, not linked yet)
        fake.install(8, created=time.time() - 3600)
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 8, state)).status_code == 403
        # an installation of another App, or none at all
        fake.install(9, app_id=1)
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 9, state)).status_code == 403
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 10, state)).status_code == 403
        assert state_of(app).db.installation_of("u_alice") is None
        assert state_of(app).db.installation_of("u_bob") == 7
        # 5 failures in an hour: locked out
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 11, state)).status_code == 403
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 7, state)).status_code == 429


async def test_relinking_your_own_installation_is_allowed(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        state = await start_install(client, ALICE)
        fake.install(5, created=time.time())
        assert (await callback(client, ALICE, 5, state)).status_code == 200
        fake.installations[5]["created_at"] = iso(time.time() - 7200)
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 5, state, setup_action="update")).status_code == 200


async def test_with_the_oauth_client_the_code_must_prove_the_installation(tmp_path: Path) -> None:
    fake = FakeGitHub()
    fake.install(21, created=time.time() - 3600)  # an older installation: fine, the code proves it
    fake.install(22)
    fake.user_installs = {"alicecode": [21], "evecode": [99]}
    app = gh_app(tmp_path, fake, github_client_id="Iv1.abc", github_client_secret="client-secret-xyz-123")
    async with client_for(app) as client:
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 22, state)).status_code == 403  # no code
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 22, state, code="evecode")).status_code == 403  # not in the list
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 21, state, code="badcode")).status_code == 403
        state = await start_install(client, ALICE)
        assert (await callback(client, ALICE, 21, state, code="alicecode")).status_code == 200
        assert state_of(app).db.installation_of("u_alice") == 21
    exchange = next(r for r in fake.requests if r.url.path == "/login/oauth/access_token")
    assert exchange.url.host == "github.com"
    assert redact_text("ghu_useralicecode") == REDACTED


def test_install_states_are_bounded_per_user_and_expire() -> None:
    now = [1000.0]
    states = InstallStates(clock=lambda: now[0])
    issued = [states.issue("u1") for _ in range(7)]
    assert all(issued)
    assert states.take(issued[0] or "", "u1") is None  # only the newest 5 are kept
    assert states.take(issued[-1] or "", "u1") == 1000.0
    late = states.issue("u1") or ""
    now[0] += 15 * 60
    assert states.take(late, "u1") is None


# --- /github/token ---


async def test_the_cli_token_is_scoped_to_the_users_own_installation(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        no = await client.post("/api/v1/github/token", json={"repo": "alice/shop"}, headers=ALICE)
        assert no.status_code == 403 and "Connect GitHub" in no.json()["detail"]
        state = await start_install(client, ALICE)
        fake.install(31)
        assert (await callback(client, ALICE, 31, state)).status_code == 200
        response = await client.post("/api/v1/github/token", json={"repo": "alice/shop"}, headers=ALICE)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["token"].startswith("ghs_") and data["repo"] == "alice/shop" and data["expires_at"] > time.time()
        minted = next(r for r in fake.requests if r.url.path.endswith("/access_tokens"))
        assert minted.url.path == "/app/installations/31/access_tokens"
        assert json.loads(minted.content)["repositories"] == ["shop"]
        bad = await client.post("/api/v1/github/token", json={"repo": "../etc"}, headers=ALICE)
        assert bad.status_code == 400
        fake.token_status = 422
        state_of(app).github.app.forget(31)  # type: ignore[attr-defined]
        unshared = await client.post("/api/v1/github/token", json={"repo": "alice/other"}, headers=ALICE)
        assert unshared.status_code == 404 and "not shared" in unshared.json()["detail"]
        _, guest = guest_headers(app)
        assert (await client.post("/api/v1/github/token", json={"repo": "a/b"}, headers=guest)).status_code == 401


async def test_an_uninstalled_app_unlinks_the_user_on_the_next_token(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        state = await start_install(client, ALICE)
        fake.install(32)
        await callback(client, ALICE, 32, state)
        del fake.installations[32]
        response = await client.post("/api/v1/github/token", json={"repo": "alice/shop"}, headers=ALICE)
        assert response.status_code == 403
        assert (await client.get("/api/v1/me", headers=ALICE)).json()["github_connected"] is False


# --- webhook ---


def signed(body: bytes, secret: str = HOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_the_webhook_checks_the_signature_and_unlinks_deleted_installations(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_app(tmp_path, fake)
    async with client_for(app) as client:
        state = await start_install(client, ALICE)
        fake.install(41)
        await callback(client, ALICE, 41, state)
        body = json.dumps({"action": "deleted", "installation": {"id": 41},
                           "repositories": [{"full_name": f"a/r{i}" * 20} for i in range(600)]}).encode()
        assert len(body) > 64 * 1024  # bigger than the API's usual body limit
        hook = "/api/v1/github/webhook"
        event = {"X-GitHub-Event": "installation", "Content-Type": "application/json"}
        missing = await client.post(hook, content=body, headers=event)
        assert missing.status_code == 401
        wrong = await client.post(hook, content=body, headers={**event, "X-Hub-Signature-256": signed(body, "nope")})
        assert wrong.status_code == 401
        tampered = await client.post(hook, content=body + b" ",
                                     headers={**event, "X-Hub-Signature-256": signed(body)})
        assert tampered.status_code == 401
        sha1 = "sha1=" + hmac.new(HOOK_SECRET.encode(), body, hashlib.sha1).hexdigest()
        assert (await client.post(hook, content=body, headers={**event, "X-Hub-Signature-256": sha1})).status_code == 401
        assert state_of(app).db.installation_of("u_alice") == 41
        good = await client.post(hook, content=body, headers={**event, "X-Hub-Signature-256": signed(body)})
        assert good.status_code == 200 and good.json() == {"ok": True}
        assert state_of(app).db.installation_of("u_alice") is None
        created = json.dumps({"action": "created", "installation": {"id": 43}}).encode()
        ok = await client.post(hook, content=created, headers={**event, "X-Hub-Signature-256": signed(created)})
        assert ok.status_code == 200  # acknowledged; linking happens only in the setup callback
        assert state_of(app).db.installation_owner(43) is None
        junk = b"not json"
        assert (await client.post(hook, content=junk, headers={**event, "X-Hub-Signature-256": signed(junk)})
                ).status_code == 400


async def test_the_webhook_is_off_without_its_secret(tmp_path: Path) -> None:
    app = gh_app(tmp_path, FakeGitHub(), github_webhook_secret=None)
    async with client_for(app) as client:
        body = b"{}"
        response = await client.post("/api/v1/github/webhook", content=body,
                                      headers={"X-Hub-Signature-256": signed(body)})
        assert response.status_code == 501


def test_webhook_events_drop_caches() -> None:
    class Db:
        def __init__(self) -> None:
            self.unbound: list[int] = []

        def unbind_installation(self, installation_id: int) -> int:
            self.unbound.append(installation_id)
            return 1

    fake = FakeGitHub()
    db = Db()
    link = AppGitHub(github_app(fake), db, slug="rook-invariants")  # type: ignore[arg-type]
    assert link.handle_event("installation", {"action": "suspend", "installation": {"id": 5}}) == "suspended"
    assert link.handle_event("installation_repositories", {"installation": {"id": 5}}) == "repos_changed"
    assert link.handle_event("installation", {"action": "deleted", "installation": {"id": 5}}) == "unlinked"
    assert link.handle_event("push", ["not a dict"]) == "ignored"
    assert db.unbound == [5]


# --- push + PR ---


class PrApi:
    def __init__(self, default: str = "main") -> None:
        self.default = default
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and request.url.path == "/repos/acme/shop":
            return httpx.Response(200, json={"full_name": "acme/shop", "default_branch": self.default})
        if request.method == "POST" and request.url.path == "/repos/acme/shop/pulls":
            return httpx.Response(201, json={"html_url": "https://github.com/acme/shop/pull/12", "number": 12})
        return httpx.Response(404, json={})


def cloned_workspace(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("bug\n")
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "upstream")
    origin = tmp_path / "server" / "acme" / "shop.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(origin)], check=True, capture_output=True)
    ws = prepare_workspace(RepoSpec(kind="github", ref="acme/shop"), "r_abcdefghijkl", root=tmp_path / "w",
                           github_url=f"file://{tmp_path / 'server'}").path
    return ws, origin


EVIDENCE = ShipRequest(cx_id="cx_001", files=["app.py"], title="Rook: fix refund_le_paid (cx_001)",
                       body="Rule: a refund never exceeds the payment\nCounterexample: 3 steps, reproduced 10/10.\n"
                            "Regression test: tests/test_rook_cx_001.py\nVerified by Rook: replay passed.")


async def test_the_shipper_pushes_the_fix_branch_and_opens_a_pr_with_the_evidence(tmp_path: Path,
                                                                                  monkeypatch: Any) -> None:
    ws, origin = cloned_workspace(tmp_path)
    (ws / "app.py").write_text("fixed\n")
    api = PrApi()
    fetched: list[int] = []

    async def token() -> str:
        fetched.append(1)
        return "ghs_" + "PushT0kenForTestsOnly"

    calls: list[list[str]] = []
    real_popen = subprocess.Popen

    def spy(argv: list[str], **kwargs: Any) -> Any:
        calls.append(list(argv))
        return real_popen(argv, **kwargs)

    monkeypatch.setattr("rook.core.workspace.subprocess.Popen", spy)
    shipper = GitHubShipper("acme/shop", token, api_url=API, github_url=f"file://{tmp_path / 'server'}",
                            transport=httpx.MockTransport(api))
    shipped = await shipper.ship(ws, EVIDENCE)
    assert shipped.pushed and shipped.pr_url == "https://github.com/acme/shop/pull/12" and shipped.pr_number == 12
    assert shipped.branch == "rook/fix-cx-001" and fetched == [1]
    assert git(origin, "rev-parse", "refs/heads/rook/fix-cx-001") == shipped.commit
    assert git(origin, "show", "main:app.py") == "bug"  # the default branch is untouched
    push = next(c for c in calls if "push" in c)
    assert "--force" not in push and not any("PushT0ken" in a for a in push)
    pr = json.loads(api.requests[-1].content)
    assert pr["head"] == "rook/fix-cx-001" and pr["base"] == "main" and pr["title"] == EVIDENCE.title
    assert "- Counterexample: 3 steps, reproduced 10/10." in pr["body"] and "`app.py`" in pr["body"]
    assert "Verified by Rook" in pr["body"] and pr["body"].endswith(FOOTER)
    assert all(r.headers["authorization"] == "Bearer ghs_PushT0kenForTestsOnly" for r in api.requests)


async def test_the_shipper_never_pushes_to_the_base_branch(tmp_path: Path) -> None:
    ws, origin = cloned_workspace(tmp_path)
    (ws / "app.py").write_text("fixed\n")

    async def token() -> str:
        return "ghs_" + "PushT0kenForTestsOnly"

    shipper = GitHubShipper("acme/shop", token, api_url=API, github_url=f"file://{tmp_path / 'server'}",
                            transport=httpx.MockTransport(PrApi(default="rook/fix-cx-001")))
    with pytest.raises(GitHubError, match="refusing to push"):
        await shipper.ship(ws, EVIDENCE)
    assert "rook/fix-cx-001" not in git(origin, "branch", "--list")
    with pytest.raises(ValueError):
        GitHubShipper("--upload-pack=x/y", token)


def test_the_pr_body_is_redacted() -> None:
    body = pr_body(ShipRequest("cx_1", ["a.py"], "t", "Observed: Bearer abc.def.ghi and ghp_leakedTOKEN123"), ["a.py"])
    assert "ghp_leaked" not in body and "abc.def.ghi" not in body


# --- CLI token fetch ---


def cli_client(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.Client]:
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def saved(tmp_path: Path, expires_at: int | None = None) -> Path:
    path = tmp_path / "credentials.json"
    save_credentials(path, Credentials(server="https://rook.example.app", email="a@example.com",
                                       access_token="supabase-access-token-xyz", refresh_token="r",
                                       expires_at=int(time.time()) + 3600 if expires_at is None else expires_at))
    return path


async def test_the_cli_asks_the_signed_in_server_for_a_repo_token(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"token": "ghs_cliT0kenForTests", "expires_at": 1, "repo": "acme/shop"})

    tokens = ServerTokens("acme/shop", saved(tmp_path), client_factory=cli_client(handler))
    assert await tokens() == "ghs_cliT0kenForTests"
    assert str(seen[0].url) == "https://rook.example.app/api/v1/github/token"
    assert json.loads(seen[0].content) == {"repo": "acme/shop"}
    assert seen[0].headers["authorization"] == "Bearer supabase-access-token-xyz"
    assert redact_text("ghs_cliT0kenForTests") == REDACTED


def test_the_cli_explains_why_there_is_no_token(tmp_path: Path) -> None:
    def refuse(status: int, detail: str) -> Callable[[], httpx.Client]:
        return cli_client(lambda request: httpx.Response(status, json={"detail": detail}))

    with pytest.raises(GitHubTokenError, match="rook login"):
        ServerTokens("acme/shop", tmp_path / "none.json").fetch()
    with pytest.raises(GitHubTokenError, match="expired"):
        ServerTokens("acme/shop", saved(tmp_path, expires_at=1)).fetch()
    creds = saved(tmp_path)
    with pytest.raises(GitHubTokenError, match="not shared"):
        ServerTokens("acme/shop", creds, client_factory=refuse(404, "acme/shop is not shared")).fetch()
    with pytest.raises(GitHubTokenError, match="rook login"):
        ServerTokens("acme/shop", creds, client_factory=refuse(401, "no")).fetch()


def test_rook_run_on_a_github_repo_without_a_sign_in_fails_clearly(tmp_path: Path, monkeypatch: Any) -> None:
    from typer.testing import CliRunner

    from rook.cli import main as cli_main
    from rook.cli import runs

    monkeypatch.setattr(runs, "CREDENTIALS", tmp_path / "missing.json")
    result = CliRunner().invoke(cli_main.app, ["run", "acme/shop", "--ci"])
    assert result.exit_code == 2 and "rook login" in result.output
