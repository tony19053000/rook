"""`GET /runs/{id}/events?after=N` as text/event-stream (02 §9, §11).

Each message is `id: <seq>` + one `data: <envelope JSON>` line (the JSON has no newlines). A `: ping`
comment goes out when nothing happened for `ping_seconds`, so proxies keep the connection open.

A `: flush` comment follows each burst of events once the stream has been quiet for `flush_seconds`. The
Vercel rewrite proxy holds back the tail of a burst until the next bytes arrive from the server (measured: a
3 KB `question.asked` sat there until the next ping, 15 s later), so this small, separate write pushes the
burst through at once.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from rook.core.events import Event

SSE_HEADERS = {"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"}


def format_event(event: Event) -> str:
    return f"id: {event.seq}\ndata: {event.model_dump_json()}\n\n"


async def stored_events(events: list[Event]) -> AsyncIterator[Event]:
    for event in events:
        yield event


async def sse_stream(events: AsyncIterator[Event], ping_seconds: float,
                     flush_seconds: float = 0.25) -> AsyncIterator[str]:
    """Format `events`, with pings and flushes in between; ends after `run.finished` or when `events` ends."""
    queue: asyncio.Queue[Event | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in events:
                await queue.put(event)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        yield ": connected\n\n"
        unflushed = False
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), flush_seconds if unflushed else ping_seconds)
            except TimeoutError:
                yield ": flush\n\n" if unflushed else ": ping\n\n"
                unflushed = False
                continue
            if item is None:
                return
            yield format_event(item)
            if item.type == "run.finished":
                return
            unflushed = True
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
