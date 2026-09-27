"""ROOK-030: Supabase JWT verification (HS256 + JWKS), `/me`, and the CLI sign-in routes (`/auth/*`).

Every token is signed locally; Supabase's HTTP API is an httpx MockTransport, the JWKS a recording fetcher."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from rook.server.app import create_app
from rook.server.config import ServerSettings
from rook.server.logins import LOGIN_COOKIE, LoginFlows
from rook.server.supabase import (
    JWKS_MISS_COOLDOWN,
    JwksCache,
    SupabaseOAuth,
    SupabaseVerifier,
    TokenSet,
    jwks_url,
    pkce_challenge,
)

SUPABASE = "https://proj.supabase.co"
ISSUER = f"{SUPABASE}/auth/v1"
SECRET = "test-hs256-secret-" + "x" * 30
PUBLIC = "https://rook.example.app"
API = "/api/v1"


def claims(**overrides: Any) -> dict[str, Any]:
    base = {"sub": "u-123", "email": "owner@example.com", "aud": "authenticated", "iss": ISSUER,
            "exp": int(time.time()) + 3600, "role": "authenticated"}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


class Jwks:
    """A recording JWKS fetcher: the URLs asked for, and the keys it serves."""

    def __init__(self, keys: list[dict[str, Any]]) -> None:
        self.keys = keys
        self.urls: list[str] = []

    def __call__(self, url: str) -> dict[str, Any]:
        self.urls.append(url)
        return {"keys": self.keys}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def ec_key(kid: str = "ec-1") -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    return private, {**jwk, "kid": kid, "alg": "ES256", "use": "sig"}


def rsa_key(kid: str = "rsa-1") -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return private, {**jwk, "kid": kid, "alg": "RS256", "use": "sig"}


def verifier_with(keys: list[dict[str, Any]], secret: str | None = SECRET) -> tuple[SupabaseVerifier, Jwks]:
    fetch = Jwks(keys)
    return SupabaseVerifier(SUPABASE, secret, JwksCache(jwks_url(SUPABASE), fetch=fetch)), fetch


# --- HS256 -----------------------------------------------------------------------------------------------


def test_hs256_good_token_gives_the_user() -> None:
    verifier, fetch = verifier_with([])
    user = verifier.verify(jwt.encode(claims(), SECRET, algorithm="HS256"))
    assert user is not None and user.id == "u-123" and user.email == "owner@example.com"
    assert fetch.urls == []  # HS256 never needs the JWKS


@pytest.mark.parametrize("token_claims", [
    claims(exp=int(time.time()) - 120),  # expired (beyond the 10 s leeway)
    claims(aud="anon"),
    claims(iss="https://evil.supabase.co/auth/v1"),
    claims(exp=None),  # exp is required
    claims(sub=None),
    claims(sub=""),
], ids=["expired", "wrong-aud", "wrong-iss", "no-exp", "no-sub", "empty-sub"])
def test_hs256_bad_claims_are_rejected(token_claims: dict[str, Any]) -> None:
    verifier, _ = verifier_with([])
    assert verifier.verify(jwt.encode(token_claims, SECRET, algorithm="HS256")) is None


def test_hs256_with_the_wrong_secret_or_no_secret_is_rejected() -> None:
    verifier, _ = verifier_with([])
    assert verifier.verify(jwt.encode(claims(), "another-secret-" + "y" * 30, algorithm="HS256")) is None
    no_secret, _ = verifier_with([], secret=None)
    assert no_secret.verify(jwt.encode(claims(), SECRET, algorithm="HS256")) is None


def test_alg_none_and_garbage_are_rejected() -> None:
    verifier, _ = verifier_with([])
    unsigned = jwt.encode(claims(), None, algorithm="none")
    assert verifier.verify(unsigned) is None
    assert verifier.verify("not-a-jwt") is None
    assert verifier.verify("") is None
    for alg in ("HS384", "HS512"):
        assert verifier.verify(jwt.encode(claims(), SECRET, algorithm=alg)) is None


# --- ES256 / RS256 through the JWKS ---------------------------------------------------------------------


def test_es256_token_verifies_against_the_jwks() -> None:
    private, jwk = ec_key()
    verifier, fetch = verifier_with([jwk])
    token = jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "ec-1"})
    user = verifier.verify(token)
    assert user is not None and user.id == "u-123"
    assert fetch.urls == [f"{SUPABASE}/auth/v1/.well-known/jwks.json"]


def test_rs256_token_verifies_against_the_jwks() -> None:
    private, jwk = rsa_key()
    verifier, _ = verifier_with([jwk])
    assert verifier.verify(jwt.encode(claims(), private, algorithm="RS256", headers={"kid": "rsa-1"})) is not None


def test_es256_bad_signature_expiry_and_unknown_kid_are_rejected() -> None:
    private, jwk = ec_key()
    other, _ = ec_key("other")
    verifier, _ = verifier_with([jwk])
    assert verifier.verify(jwt.encode(claims(), other, algorithm="ES256", headers={"kid": "ec-1"})) is None
    assert verifier.verify(jwt.encode(claims(exp=int(time.time()) - 120), private, algorithm="ES256",
                                      headers={"kid": "ec-1"})) is None
    assert verifier.verify(jwt.encode(claims(aud="x"), private, algorithm="ES256", headers={"kid": "ec-1"})) is None
    assert verifier.verify(jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "nope"})) is None
    assert verifier.verify(jwt.encode(claims(), private, algorithm="ES256")) is None  # no kid


def test_the_jwks_url_never_comes_from_the_token() -> None:
    attacker, attacker_jwk = ec_key("evil")
    verifier, fetch = verifier_with([])
    token = jwt.encode(claims(), attacker, algorithm="ES256",
                       headers={"kid": "evil", "jku": "https://evil.example/jwks.json",
                                "x5u": "https://evil.example/cert", "jwk": attacker_jwk})
    assert verifier.verify(token) is None
    assert fetch.urls and set(fetch.urls) == {jwks_url(SUPABASE)}


def test_alg_confusion_is_rejected() -> None:
    """A token can't pick a key of another type: HS256 signed with the public key, or RS256 on an EC kid."""
    private, jwk = ec_key()
    rsa_private, _ = rsa_key()
    verifier, _ = verifier_with([jwk])
    public_pem = private.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo)
    forged = _hs256_raw(claims(), public_pem, kid="ec-1")
    assert verifier.verify(forged) is None
    assert verifier.verify(jwt.encode(claims(), rsa_private, algorithm="RS256", headers={"kid": "ec-1"})) is None


def _hs256_raw(payload: dict[str, Any], key: bytes, kid: str) -> str:
    """HS256 over raw bytes (PyJWT refuses PEM keys for HMAC, which is exactly the attack)."""
    import base64
    import hashlib
    import hmac

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    signing = f"{b64(json.dumps({'alg': 'HS256', 'typ': 'JWT', 'kid': kid}).encode())}.{b64(json.dumps(payload).encode())}"
    return f"{signing}.{b64(hmac.new(key, signing.encode(), hashlib.sha256).digest())}"


def test_the_jwks_is_cached_and_an_unknown_kid_refetches_at_most_every_cooldown() -> None:
    private, jwk = ec_key()
    fetch = Jwks([jwk])
    clock = Clock()
    verifier = SupabaseVerifier(SUPABASE, None, JwksCache(jwks_url(SUPABASE), fetch=fetch, clock=clock))
    token = jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "ec-1"})
    for _ in range(5):
        assert verifier.verify(token) is not None
    assert len(fetch.urls) == 1
    unknown = jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "rotated"})
    assert verifier.verify(unknown) is None and verifier.verify(unknown) is None
    assert len(fetch.urls) == 1  # within the cooldown
    clock.now += JWKS_MISS_COOLDOWN
    rotated_private, rotated = ec_key("rotated")
    fetch.keys = [jwk, rotated]
    assert verifier.verify(jwt.encode(claims(), rotated_private, algorithm="ES256", headers={"kid": "rotated"}))
    assert len(fetch.urls) == 2


def test_a_failing_jwks_fetch_rejects_the_token_without_raising() -> None:
    private, _ = ec_key()

    def broken(url: str) -> dict[str, Any]:
        raise httpx.ConnectError("down")

    verifier = SupabaseVerifier(SUPABASE, None, JwksCache(jwks_url(SUPABASE), fetch=broken))
    assert verifier.verify(jwt.encode(claims(), private, algorithm="ES256", headers={"kid": "ec-1"})) is None


# --- settings ---------------------------------------------------------------------------------------------


def test_settings_read_supabase_from_the_environment(tmp_path: Path) -> None:
    settings = ServerSettings.from_env({"SUPABASE_URL": SUPABASE + "/", "SUPABASE_JWT_SECRET": SECRET,
                                        "SUPABASE_ANON_KEY": "sb_publishable_abc", "ROOK_PUBLIC_URL": PUBLIC})
    assert settings.supabase_url == SUPABASE and settings.public_url == PUBLIC
    assert settings.supabase_jwt_secret is not None and settings.supabase_anon_key == "sb_publishable_abc"
    assert SECRET not in repr(settings)
    for bad in ("http://proj.supabase.co", "https://proj.supabase.co/path", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            ServerSettings(supabase_url=bad)
    assert ServerSettings(public_url="http://127.0.0.1:8000").public_url == "http://127.0.0.1:8000"


# --- the app: /me and the sign-in routes ------------------------------------------------------------------


class FakeSupabase:
    """Supabase's /token and /logout endpoints behind an httpx MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "proj.supabase.co"
        if request.url.path == "/auth/v1/token":
            body = json.loads(request.content)
            ok = (request.url.params.get("grant_type") == "pkce" and body["auth_code"] == "the-code"
                  and request.headers.get("apikey") == "sb_publishable_abc")
            if self.token_status != 200 or not ok:
                return httpx.Response(self.token_status if self.token_status != 200 else 400, json={})
            return httpx.Response(200, json={"access_token": "acc.tok.en", "refresh_token": "ref",
                                             "expires_at": 2_000_000_000, "expires_in": 3600})
        if request.url.path == "/auth/v1/logout":
            return httpx.Response(204)
        return httpx.Response(404)


def make_client(tmp_path: Path, **overrides: Any) -> tuple[TestClient, FakeSupabase]:
    values: dict[str, Any] = {"db_path": tmp_path / "server.db", "workspaces_root": tmp_path / "ws",
                              "guest_secret": "s" * 40, "bob_mode": "replay", "supabase_url": SUPABASE,
                              "supabase_jwt_secret": SECRET, "supabase_anon_key": "sb_publishable_abc",
                              "public_url": PUBLIC, **overrides}
    fake = FakeSupabase()
    settings = ServerSettings.model_validate(values)
    oauth = SupabaseOAuth(SUPABASE, "sb_publishable_abc", transport=httpx.MockTransport(fake.handler)) \
        if settings.public_url else None
    app = create_app(settings, oauth=oauth)
    return TestClient(app, base_url="https://testserver", follow_redirects=False), fake


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_me_verifies_the_supabase_token(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        good = client.get(f"{API}/me", headers=bearer(jwt.encode(claims(), SECRET, algorithm="HS256")))
        assert good.status_code == 200
        assert good.json() == {"id": "u-123", "email": "owner@example.com", "github_connected": False}
        expired = jwt.encode(claims(exp=int(time.time()) - 120), SECRET, algorithm="HS256")
        assert client.get(f"{API}/me", headers=bearer(expired)).status_code == 401
        assert client.get(f"{API}/me").status_code == 401  # a guest
        # a bad bearer is a 401 even on guest routes; no token keeps the guest flow as it was
        assert client.get(f"{API}/repos", headers=bearer("junk")).status_code == 401
        guest = client.get(f"{API}/repos")
        assert guest.status_code == 200 and "rook_guest" in guest.cookies


def test_without_supabase_every_bearer_token_is_refused(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, supabase_url=None, public_url=None)
    with client:
        assert client.get(f"{API}/me", headers=bearer(jwt.encode(claims(), SECRET, algorithm="HS256"))).status_code == 401
        assert client.get(f"{API}/auth/cli/start", params={"port": 5000, "state": "s" * 20}).status_code == 501
        assert client.post(f"{API}/auth/device/start").status_code == 501


STATE = "abcdefghijklmnopqrstuvwxyz012345"


def test_cli_start_redirects_to_google_with_pkce_and_a_login_cookie(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        start = client.get(f"{API}/auth/cli/start", params={"port": 53682, "state": STATE})
    assert start.status_code == 302
    target = urlsplit(start.headers["location"])
    query = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{SUPABASE}/auth/v1/authorize"
    assert query["provider"] == ["google"] and query["code_challenge_method"] == ["s256"]
    assert query["redirect_to"] == [f"{PUBLIC}/api/v1/auth/cli/callback"]  # exact: the Supabase allowlist
    assert len(query["code_challenge"][0]) == 43 and STATE not in start.headers["location"]
    cookie = start.headers["set-cookie"]
    assert cookie.startswith(f"{LOGIN_COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    assert "Path=/api/v1/auth" in cookie and "samesite=lax" in cookie.lower()


@pytest.mark.parametrize("params", [
    {"port": 80, "state": STATE}, {"port": 70000, "state": STATE}, {"port": 5000, "state": "short"},
    {"port": 5000, "state": "has spaces in it!!!!!"}, {"port": 5000},
])
def test_cli_start_rejects_bad_ports_and_states(tmp_path: Path, params: dict[str, Any]) -> None:
    client, _ = make_client(tmp_path)
    with client:
        assert client.get(f"{API}/auth/cli/start", params=params).status_code == 400


def test_cli_callback_exchanges_the_code_and_redirects_to_the_loopback_once(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    with client:
        start = client.get(f"{API}/auth/cli/start", params={"port": 53682, "state": STATE})
        challenge = parse_qs(urlsplit(start.headers["location"]).query)["code_challenge"][0]
        callback = client.get(f"{API}/auth/cli/callback", params={"code": "the-code"})
        assert callback.status_code == 302
        target = urlsplit(callback.headers["location"])
        assert (target.scheme, target.hostname, target.port, target.path) == ("http", "127.0.0.1", 53682, "/cb")
        assert parse_qs(target.query) == {"token": ["acc.tok.en"], "refresh_token": ["ref"],
                                          "expires_at": ["2000000000"], "state": [STATE]}
        (exchange,) = fake.requests
        assert pkce_challenge(json.loads(exchange.content)["code_verifier"]) == challenge
        # the flow is consumed: a replayed callback (same cookie) gets nothing
        client.cookies.set(LOGIN_COOKIE, start.cookies[LOGIN_COOKIE], domain="testserver", path="/api/v1/auth")
        again = client.get(f"{API}/auth/cli/callback", params={"code": "the-code"})
        assert again.status_code == 400 and "acc.tok.en" not in again.text


def test_cli_callback_without_a_valid_cookie_is_rejected(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    with client:
        client.get(f"{API}/auth/cli/start", params={"port": 53682, "state": STATE})
        client.cookies.clear()
        assert client.get(f"{API}/auth/cli/callback", params={"code": "the-code"}).status_code == 400
        client.cookies.set(LOGIN_COOKIE, "forged.0000", domain="testserver", path="/api/v1/auth")
        assert client.get(f"{API}/auth/cli/callback", params={"code": "the-code"}).status_code == 400
    assert fake.requests == []


def test_cli_callback_reports_a_failed_exchange_to_the_loopback(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    fake.token_status = 400
    with client:
        client.get(f"{API}/auth/cli/start", params={"port": 53682, "state": STATE})
        callback = client.get(f"{API}/auth/cli/callback", params={"code": "the-code"})
    query = parse_qs(urlsplit(callback.headers["location"]).query)
    assert query == {"error": ["sign_in_failed"], "state": [STATE]}


def test_device_flow_end_to_end(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        start = client.post(f"{API}/auth/device/start").json()
        assert start["interval"] == 5 and start["expires_in"] == 600
        assert start["verification_url"].startswith(f"{PUBLIC}/api/v1/auth/device/verify?code=")
        poll = {"device_code": start["device_code"]}
        assert client.post(f"{API}/auth/device/poll", json=poll).json() == {"status": "pending"}
        code = start["user_code"]
        confirm = client.get(f"{API}/auth/device/verify", params={"code": code})
        assert confirm.status_code == 200 and code in confirm.text and "default-src 'none'" in \
            confirm.headers["content-security-policy"]
        assert client.get(f"{API}/auth/device/verify", params={"code": code, "confirm": 1}).status_code == 302
        # a code starts one sign-in only
        assert client.get(f"{API}/auth/device/verify", params={"code": code, "confirm": 1}).status_code == 404
        done = client.get(f"{API}/auth/cli/callback", params={"code": "the-code"})
        assert done.status_code == 200 and "acc.tok.en" not in done.text
        assert client.post(f"{API}/auth/device/poll", json=poll).json() == {
            "status": "done", "token": "acc.tok.en", "refresh_token": "ref", "expires_at": 2_000_000_000}
        assert client.post(f"{API}/auth/device/poll", json=poll).json() == {"status": "expired"}


def test_device_verify_rejects_unknown_codes_and_polls_validate(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    with client:
        assert client.get(f"{API}/auth/device/verify", params={"code": "ABCD-EFGH"}).status_code == 404
        assert client.get(f"{API}/auth/device/verify", params={"code": "<script>"}).status_code == 404
        assert client.post(f"{API}/auth/device/poll", json={"device_code": "x" * 30}).json() == {"status": "expired"}
        assert client.post(f"{API}/auth/device/poll", json={"device_code": "x"}).status_code == 400


def test_logout_revokes_the_supabase_session(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    token = jwt.encode(claims(), SECRET, algorithm="HS256")
    with client:
        assert client.post(f"{API}/auth/logout", headers=bearer(token)).json() == {"ok": True}
        assert client.post(f"{API}/auth/logout").status_code == 401
    (request,) = fake.requests
    assert request.url.path == "/auth/v1/logout" and request.headers["authorization"] == f"Bearer {token}"


def test_login_flows_expire_and_are_bounded() -> None:
    clock = Clock()
    flows = LoginFlows("k" * 40, clock=clock)
    from rook.server.logins import FLOW_TTL, MAX_PENDING, LoginFlow

    flow_id = flows.start(LoginFlow(verifier="v", kind="cli", port=5000, state=STATE))
    assert flow_id is not None and flows.flow_id_from_cookie(flows.cookie_value(flow_id)) == flow_id
    assert flows.flow_id_from_cookie(f"{flow_id}.bad") is None
    clock.now += FLOW_TTL
    assert flows.take(flow_id) is None
    for _ in range(MAX_PENDING):
        assert flows.start(LoginFlow(verifier="v", kind="cli")) is not None
    assert flows.start(LoginFlow(verifier="v", kind="cli")) is None
    device = flows.new_device()
    assert device is not None and flows.complete_device(device.user_code, TokenSet("a", "r", 1))
