"""A lean httpx transport that calls an ASGI app in the same process (tests and in-process search).

It does what `httpx.ASGITransport` does for one request/response, without its per-request async
library detection (which retries a failing `import sniffio` on every request when sniffio is not
installed and costs about a third of a small request). asyncio only.
"""

import asyncio
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import httpx

ASGIApp = Callable[
    [
        MutableMapping[str, Any],
        Callable[[], Awaitable[MutableMapping[str, Any]]],
        Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ],
    Awaitable[None],
]


class InProcessTransport(httpx.AsyncBaseTransport):
    def __init__(self, app: ASGIApp, client: tuple[str, int] = ("127.0.0.1", 123)) -> None:
        self.app = app
        self.client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        url = request.url
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
            "scheme": url.scheme,
            "path": url.path,
            "raw_path": url.raw_path.split(b"?")[0],
            "query_string": url.query,
            "server": (url.host, url.port),
            "client": self.client,
            "root_path": "",
        }
        request_sent = False
        status: int | None = None
        headers: list[tuple[bytes, bytes]] = []
        parts: list[bytes] = []
        done: asyncio.Event | None = None  # created only if the app waits for a disconnect
        complete = False

        async def receive() -> dict[str, Any]:
            nonlocal request_sent, done
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            if not complete:
                done = done or asyncio.Event()
                await done.wait()
            return {"type": "http.disconnect"}

        async def send(message: MutableMapping[str, Any]) -> None:
            nonlocal status, headers, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk and request.method != "HEAD":
                    parts.append(chunk)
                if not message.get("more_body", False):
                    complete = True
                    if done is not None:
                        done.set()

        await self.app(scope, receive, send)
        if status is None or not complete:
            raise httpx.RemoteProtocolError("ASGI app returned without a complete response", request=request)
        return httpx.Response(status, headers=headers, content=b"".join(parts), request=request)
