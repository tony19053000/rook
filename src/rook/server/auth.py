"""Who is calling: a signed-in user (bearer token) or a guest (signed `rook_guest` cookie), 02 §11 / 03 §6.

ROOK-030 plugs Supabase JWT verification in through `TokenVerifier`; until then `RejectAllTokens` turns
every bearer token into a 401, so nothing is ever trusted by accident.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

from fastapi import HTTPException, Request, Response

GUEST_COOKIE = "rook_guest"
GUEST_MAX_AGE = 30 * 24 * 3600
_GUEST_ID = re.compile(r"g_[A-Za-z0-9_-]{16,64}")


@dataclass(frozen=True)
class AuthUser:
    """A verified user: `id` is the Supabase `sub`."""

    id: str
    email: str


@dataclass(frozen=True)
class Caller:
    id: str
    kind: Literal["user", "guest"]
    email: str = ""

    @property
    def is_guest(self) -> bool:
        return self.kind == "guest"


class TokenVerifier(Protocol):
    """Checks a bearer token (signature, `exp`, `aud`); None when it is not valid. ROOK-030 implements it."""

    def verify(self, token: str) -> AuthUser | None: ...


class RejectAllTokens:
    """The default until Supabase auth (ROOK-030) is configured: no bearer token is valid."""

    def verify(self, token: str) -> AuthUser | None:
        return None


class GuestCookies:
    """`<guest_id>.<hex HMAC-SHA256(guest_id)>`: a guest can't forge another guest's id."""

    def __init__(self, secret: str, secure: bool = True) -> None:
        self._key = secret.encode()
        self.secure = secure

    def _sign(self, guest_id: str) -> str:
        return hmac.new(self._key, guest_id.encode(), hashlib.sha256).hexdigest()

    def issue(self) -> tuple[str, str]:
        """A new guest id and its cookie value."""
        guest_id = "g_" + secrets.token_urlsafe(18)
        return guest_id, f"{guest_id}.{self._sign(guest_id)}"

    def read(self, value: str | None) -> str | None:
        """The guest id of a valid cookie value, else None."""
        if not value or value.count(".") != 1:
            return None
        guest_id, signature = value.split(".")
        if not _GUEST_ID.fullmatch(guest_id):
            return None
        return guest_id if hmac.compare_digest(signature, self._sign(guest_id)) else None

    def set(self, response: Response, value: str) -> None:
        response.set_cookie(GUEST_COOKIE, value, max_age=GUEST_MAX_AGE, httponly=True, samesite="lax",
                            secure=self.secure, path="/")


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Invalid authorization header")
    return token.strip()


def resolve_caller(request: Request, response: Response, verifier: TokenVerifier, cookies: GuestCookies,
                   *, allow_guest: bool, issue_guest: bool) -> Caller:
    """A bearer token must be valid (401 otherwise, even with a guest cookie). Without one, a valid guest
    cookie makes a guest; `issue_guest` creates a new guest when there is no valid cookie."""
    token = bearer_token(request)
    if token is not None:
        user = verifier.verify(token)
        if user is None:
            raise HTTPException(401, "Invalid or expired token")
        return Caller(id=user.id, kind="user", email=user.email)
    if not allow_guest:
        raise HTTPException(401, "Sign in required")
    guest_id = cookies.read(request.cookies.get(GUEST_COOKIE))
    if guest_id is None:
        if not issue_guest:
            raise HTTPException(401, "Sign in or start the demo first")
        guest_id, value = cookies.issue()
        cookies.set(response, value)
    return Caller(id=guest_id, kind="guest")
