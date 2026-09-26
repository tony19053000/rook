"""Record and replay raw `bob run` NDJSON streams (02_ARCHITECTURE.md §5.1).

A recording is `<recordings_dir>/<key>.ndjson`. Each line is `{"t": <seconds since start>, "raw": <line>}`.
The key is `sha256(slug + "\\0" + prompt)`, so callers must build deterministic prompts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

from rook.core.events import redact_text

DEFAULT_RECORDINGS_DIR = Path.home() / ".rook" / "recordings"


class RecordingMissing(LookupError):
    """Replay mode was asked for a call that has no recording."""


def recording_key(slug: str, prompt: str) -> str:
    return hashlib.sha256(f"{slug}\0{prompt}".encode()).hexdigest()


class RecordingWriter:
    """Collects raw lines with their offset from creation time."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self.entries: list[tuple[float, str]] = []

    def add(self, raw: str) -> None:
        self.entries.append((round(time.monotonic() - self._start, 3), raw))


class Recorder:
    def __init__(self, recordings_dir: Path | str | None = None) -> None:
        self.dir = Path(recordings_dir) if recordings_dir is not None else DEFAULT_RECORDINGS_DIR

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.ndjson"

    def save(self, key: str, entries: list[tuple[float, str]]) -> Path:
        """Write atomically. Lines are redacted so no secret ever lands on disk."""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.path(key)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for offset, raw in entries:
                fh.write(json.dumps({"t": offset, "raw": redact_text(raw)}) + "\n")
        os.replace(tmp, path)
        return path

    def load(self, key: str) -> list[tuple[float, str]]:
        path = self.path(key)
        if not path.is_file():
            raise RecordingMissing(f"no recording for key {key} in {self.dir}")
        entries: list[tuple[float, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                entries.append((float(item["t"]), str(item["raw"])))
        return entries


async def replay_lines(
    entries: list[tuple[float, str]], *, speed: float = 3.0, max_gap: float = 1.5
) -> AsyncIterator[str]:
    """Yield recorded lines, sleeping the original gap divided by `speed`, never more than `max_gap`."""
    previous = 0.0
    for offset, raw in entries:
        gap = max(0.0, offset - previous)
        previous = offset
        delay = min(gap / speed if speed > 0 else 0.0, max_gap)
        if delay > 0:
            await asyncio.sleep(delay)
        yield raw
