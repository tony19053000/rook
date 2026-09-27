"""Request-size and rate limits (03 §8), as plain ASGI middleware."""

from __future__ import annotations

import hmac
import json
import math
import time
from collections import deque
from collections.abc import Callable, Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


PROXY_SECRET_HEADER = "x-rook-proxy-secret"


def proxy_verified(headers: Mapping[str, str], proxy_secret: str | None) -> bool:
    """True when the request carries the shared secret the web proxy (Vercel middleware) adds (03 §8)."""
    if not proxy_secret:
        return False
    given = headers.get(PROXY_SECRET_HEADER, "")
    return hmac.compare_digest(given.encode("utf-8", "replace"), proxy_secret.encode())


def client_ip(headers: Mapping[str, str], peer: str | None, trusted_hops: int,
              proxy_secret: str | None = None) -> str:
    """The caller's IP. Behind `trusted_hops` proxies, the entry that many places from the right of
    X-Forwarded-For (each proxy appends the address it saw); the left-most entries are client-controlled.
    With a `proxy_secret`, the outermost proxy (Vercel) is trusted only when the request proves it came through
    it; otherwise that hop is dropped, so a caller that skips it is counted by the address our own proxy saw."""
    if proxy_secret and trusted_hops > 0 and not proxy_verified(headers, proxy_secret):
        trusted_hops -= 1
    if trusted_hops > 0:
        forwarded = [p.strip() for p in headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if forwarded:
            return forwarded[-min(trusted_hops, len(forwarded))]
    return peer or "unknown"


class RateLimiter:
    """A sliding window: at most `limit` hits per `window` seconds per key."""

    def __init__(self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 50_000) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float:
        """Count one hit. Returns 0 when allowed, else the seconds until the next hit is allowed."""
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= self._max_keys:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return max(0.0, hits[0] + self.window - now)
        hits.append(now)
        return 0.0

    def _prune(self, now: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
            del self._hits[key]


async def send_json(send: Send, status: int, detail: str, headers: Mapping[str, str] | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    raw += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimit:
    """Refuses bodies over `max_bytes` with 413: by Content-Length up front, else while reading (chunked).
    The (small) body is buffered, then handed to the app."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return
        too_big = "Request body is larger than the limit"
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            await send_json(send, 413, too_big)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                await send_json(send, 413, too_big)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class RateLimit:
    """60 requests/min per IP on the API and 10/min on `POST /runs` (03 §8); `exempt` paths skip it."""

    def __init__(self, app: ASGIApp, *, prefix: str, per_minute: int, runs_per_minute: int, trusted_hops: int,
                 proxy_secret: str | None = None, exempt: frozenset[str] = frozenset(),
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.prefix = prefix
        self.trusted_hops = trusted_hops
        self.proxy_secret = proxy_secret
        self.exempt = exempt
        self.api = RateLimiter(per_minute, clock=clock)
        self.runs = RateLimiter(runs_per_minute, clock=clock)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith(self.prefix) or path in self.exempt \
                or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        peer = scope["client"][0] if scope.get("client") else None
        ip = client_ip(headers, peer, self.trusted_hops, self.proxy_secret)
        wait = self.api.hit(ip)
        if not wait and scope["method"] == "POST" and path.rstrip("/") == f"{self.prefix}/runs":
            wait = self.runs.hit(ip)
        if wait:
            await send_json(send, 429, "Too many requests; slow down",
                            {"Retry-After": str(max(1, math.ceil(wait)))})
            return
        await self.app(scope, receive, send)
