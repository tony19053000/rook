"""`GET /runs/{id}/events?after=N` as text/event-stream (02 §9, §11).

Each message is `id: <seq>` + one `data: <envelope JSON>` line (the JSON has no newlines). A `: ping`
comment goes out when nothing happened for `ping_seconds`, so proxies keep the connection open.
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


async def sse_stream(events: AsyncIterator[Event], ping_seconds: float) -> AsyncIterator[str]:
    """Format `events`, with pings in between; ends after `run.finished` or when `events` ends."""
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
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), ping_seconds)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                return
            yield format_event(item)
            if item.type == "run.finished":
                return
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            with contextlib.suppress(Exception):
                await aclose()
