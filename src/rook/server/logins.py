"""Pending CLI sign-ins (03 §6): the localhost-callback flow and the device-code flow, in memory.

A flow is created by `/auth/cli/start` or `/auth/device/verify`, remembered for FLOW_TTL seconds under a
random id that the browser carries in the signed `rook_login` cookie, and consumed exactly once by
`/auth/cli/callback`. Device codes live DEVICE_TTL seconds; their tokens are handed out once by
`/auth/device/poll`. Everything is bounded, so a flood of starts can't grow memory without limit.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from rook.server.supabase import TokenSet

LOGIN_COOKIE = "rook_login"
FLOW_TTL = 600.0
DEVICE_TTL = 600.0
MAX_PENDING = 1000
# No 0/O/1/I: the user may have to read the code off a terminal.
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class LoginFlow:
    verifier: str  # the PKCE code verifier, never sent to the browser
    kind: Literal["cli", "device"]
    port: int = 0
    state: str = ""
    user_code: str = ""
    created: float = 0.0


@dataclass
class DeviceLogin:
    device_code: str
    user_code: str
    created: float
    tokens: TokenSet | None = None
    started: bool = False  # a browser has claimed the code (one sign-in per code)


def new_user_code() -> str:
    raw = "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


class LoginFlows:
    def __init__(self, cookie_secret: str, clock: Callable[[], float] = time.monotonic) -> None:
        self._key = hashlib.sha256(b"rook-login-cookie:" + cookie_secret.encode()).digest()
        self._clock = clock
        self._lock = threading.Lock()
        self._flows: dict[str, LoginFlow] = {}
        self._devices: dict[str, DeviceLogin] = {}  # by device_code
        self._by_user_code: dict[str, str] = {}  # user_code -> device_code

    # -- the signed cookie that ties the browser to its flow -------------------------------------------

    def _sign(self, flow_id: str) -> str:
        return hmac.new(self._key, flow_id.encode(), hashlib.sha256).hexdigest()

    def cookie_value(self, flow_id: str) -> str:
        return f"{flow_id}.{self._sign(flow_id)}"

    def flow_id_from_cookie(self, value: str | None) -> str | None:
        if not value or value.count(".") != 1:
            return None
        flow_id, signature = value.split(".")
        return flow_id if hmac.compare_digest(signature, self._sign(flow_id)) else None

    # -- flows ------------------------------------------------------------------------------------------

    def _prune(self, now: float) -> None:
        for fid in [k for k, f in self._flows.items() if now - f.created >= FLOW_TTL]:
            del self._flows[fid]
        for code in [k for k, d in self._devices.items() if now - d.created >= DEVICE_TTL]:
            self._by_user_code.pop(self._devices.pop(code).user_code, None)

    def start(self, flow: LoginFlow) -> str | None:
        """Remember `flow`; its id (for the cookie), or None when too many sign-ins are pending."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            if len(self._flows) >= MAX_PENDING:
                return None
            flow.created = now
            flow_id = secrets.token_urlsafe(24)
            self._flows[flow_id] = flow
            return flow_id

    def take(self, flow_id: str | None) -> LoginFlow | None:
        """The flow, removed (a callback is accepted once), or None when it is unknown or expired."""
        if flow_id is None:
            return None
        with self._lock:
            self._prune(self._clock())
            return self._flows.pop(flow_id, None)

    # -- device codes -----------------------------------------------------------------------------------

    def new_device(self) -> DeviceLogin | None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            if len(self._devices) >= MAX_PENDING:
                return None
            user_code = new_user_code()
            while user_code in self._by_user_code:
                user_code = new_user_code()
            device = DeviceLogin(device_code=secrets.token_urlsafe(32), user_code=user_code, created=now)
            self._devices[device.device_code] = device
            self._by_user_code[user_code] = device.device_code
            return device

    def device_for_user_code(self, user_code: str) -> DeviceLogin | None:
        """The pending device for a code a user opened; a code can start one sign-in only."""
        with self._lock:
            self._prune(self._clock())
            code = self._by_user_code.get(user_code)
            device = self._devices.get(code) if code else None
            if device is None or device.started or device.tokens is not None:
                return None
            return device

    def claim_device(self, user_code: str) -> bool:
        """Start the one sign-in a code allows; False when the code is unknown, expired or already used."""
        with self._lock:
            self._prune(self._clock())
            code = self._by_user_code.get(user_code)
            device = self._devices.get(code) if code else None
            if device is None or device.started:
                return False
            device.started = True
            return True

    def complete_device(self, user_code: str, tokens: TokenSet) -> bool:
        with self._lock:
            self._prune(self._clock())
            code = self._by_user_code.get(user_code)
            device = self._devices.get(code) if code else None
            if device is None or device.tokens is not None:
                return False
            device.tokens = tokens
            return True

    def fail_device(self, user_code: str) -> None:
        """A failed or cancelled browser sign-in ends the device code (the poller sees `expired`)."""
        with self._lock:
            code = self._by_user_code.pop(user_code, None)
            if code is not None:
                self._devices.pop(code, None)

    def poll(self, device_code: str) -> tuple[Literal["pending", "done", "expired"], TokenSet | None]:
        """`done` hands the tokens out once and forgets the device; an unknown code is `expired`."""
        with self._lock:
            self._prune(self._clock())
            device = self._devices.get(device_code)
            if device is None:
                return "expired", None
            if device.tokens is None:
                return "pending", None
            del self._devices[device_code]
            self._by_user_code.pop(device.user_code, None)
            return "done", device.tokens
