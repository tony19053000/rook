"""Supabase auth for the server (03 §6): JWT verification, and the OAuth (PKCE) calls behind the CLI login.

Verification accepts HS256 (the project's legacy `SUPABASE_JWT_SECRET`) and ES256 / RS256 (the project's
signing keys, read from `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, cached). The JWKS URL comes only from
the settings: `jku` / `x5u` / `jwk` headers in a token are ignored. Every token must carry `exp`, `sub`,
`aud == "authenticated"` and `iss == <SUPABASE_URL>/auth/v1`.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from rook.server.auth import AuthUser

log = logging.getLogger(__name__)

AUDIENCE = "authenticated"
LEEWAY_SECONDS = 10
# alg -> the JWK key type it must use: a token can never pick a key of another type (alg confusion).
ASYMMETRIC_ALGS = {"ES256": "EC", "RS256": "RSA"}
JWKS_TTL_SECONDS = 600.0
JWKS_MISS_COOLDOWN = 30.0  # an unknown `kid` refetches at most this often

JwksFetcher = Callable[[str], dict[str, Any]]


def jwks_url(supabase_url: str) -> str:
    return f"{supabase_url}/auth/v1/.well-known/jwks.json"


def _http_get_json(url: str) -> dict[str, Any]:
    response = httpx.get(url, timeout=5.0, follow_redirects=False)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


class JwksCache:
    """The project's public signing keys by `kid`, refreshed every JWKS_TTL_SECONDS (thread-safe)."""

    def __init__(self, url: str, fetch: JwksFetcher = _http_get_json,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.url = url
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float | None = None

    def _refresh(self) -> None:
        try:
            data = self._fetch(self.url)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("could not fetch the Supabase JWKS: %s", type(exc).__name__)
            self._fetched_at = self._clock()  # back off; keep the old keys
            return
        keys = data.get("keys")
        self._keys = {k["kid"]: k for k in keys if isinstance(k, dict) and isinstance(k.get("kid"), str)} \
            if isinstance(keys, list) else {}
        self._fetched_at = self._clock()

    def get(self, kid: str) -> dict[str, Any] | None:
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at >= JWKS_TTL_SECONDS
            missing = kid not in self._keys and (self._fetched_at is None
                                                 or now - self._fetched_at >= JWKS_MISS_COOLDOWN)
            if stale or missing:
                self._refresh()
            return self._keys.get(kid)


class SupabaseVerifier:
    """`TokenVerifier` for Supabase access tokens; `verify` never raises, it returns None for a bad token."""

    def __init__(self, supabase_url: str, jwt_secret: str | None, jwks: JwksCache | None = None) -> None:
        self.issuer = f"{supabase_url}/auth/v1"
        self._secret = jwt_secret or None
        self._jwks = jwks or JwksCache(jwks_url(supabase_url))

    def _key(self, header: dict[str, Any]) -> Any:
        alg = header.get("alg")
        if alg == "HS256":
            return self._secret
        key_type = ASYMMETRIC_ALGS.get(alg) if isinstance(alg, str) else None
        kid = header.get("kid")
        if key_type is None or not isinstance(kid, str):
            return None
        jwk = self._jwks.get(kid)
        if jwk is None or jwk.get("kty") != key_type or jwk.get("alg", alg) != alg or jwk.get("use", "sig") != "sig":
            return None
        try:
            return jwt.PyJWK(jwk, algorithm=alg).key
        except jwt.PyJWTError:
            return None

    def verify(self, token: str) -> AuthUser | None:
        try:
            header = jwt.get_unverified_header(token)
            key = self._key(header)
            if key is None:
                return None
            claims = jwt.decode(token, key, algorithms=[header["alg"]], audience=AUDIENCE, issuer=self.issuer,
                                leeway=LEEWAY_SECONDS, options={"require": ["exp", "sub", "aud", "iss"]})
        except jwt.PyJWTError:
            return None
        sub, email = claims.get("sub"), claims.get("email")
        if not isinstance(sub, str) or not sub:
            return None
        return AuthUser(id=sub, email=email if isinstance(email, str) else "")


# ---------------------------------------------------------------------------------------------------------
# OAuth (PKCE) for the CLI login, 03 §6
# ---------------------------------------------------------------------------------------------------------


def pkce_challenge(verifier: str) -> str:
    """S256: base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: int


class SupabaseError(Exception):
    """Supabase refused or could not be reached; the message never holds a token."""


class SupabaseOAuth:
    """Google sign-in through Supabase with PKCE; every call goes to the configured SUPABASE_URL only."""

    def __init__(self, supabase_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base = f"{supabase_url}/auth/v1"
        self._headers = {"apikey": api_key}
        self._transport = transport

    def authorize_url(self, redirect_to: str, challenge: str) -> str:
        query = {"provider": "google", "redirect_to": redirect_to, "code_challenge": challenge,
                 "code_challenge_method": "s256"}
        return f"{self.base}/authorize?{urlencode(query)}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=10.0, follow_redirects=False)

    async def exchange(self, code: str, verifier: str) -> TokenSet:
        try:
            async with self._client() as client:
                response = await client.post(f"{self.base}/token", params={"grant_type": "pkce"},
                                             json={"auth_code": code, "code_verifier": verifier},
                                             headers=self._headers)
        except httpx.HTTPError as exc:
            raise SupabaseError(f"Supabase is unreachable ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise SupabaseError(f"Supabase refused the sign-in (HTTP {response.status_code})")
        try:
            data = response.json()
            access, refresh = data["access_token"], data.get("refresh_token", "")
            expires_at = int(data.get("expires_at") or time.time() + int(data.get("expires_in", 3600)))
        except (ValueError, KeyError, TypeError):
            raise SupabaseError("Supabase sent an unexpected token response") from None
        if not isinstance(access, str) or not isinstance(refresh, str):
            raise SupabaseError("Supabase sent an unexpected token response")
        return TokenSet(access_token=access, refresh_token=refresh, expires_at=expires_at)

    async def logout(self, access_token: str) -> bool:
        """Revoke the session behind `access_token` (its refresh tokens stop working)."""
        try:
            async with self._client() as client:
                response = await client.post(f"{self.base}/logout", params={"scope": "local"},
                                             headers={**self._headers, "Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError:
            return False
        return response.status_code in (200, 204)
