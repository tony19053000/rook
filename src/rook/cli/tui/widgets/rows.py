"""AgentRow, EngineRow and LiveRows: inline transcript rows driven by agent.* / engine.* events (04 §1.3).

An agent row shows `[sprite] Name  Verb… (3.2s)` / `⎿ detail` while working and collapses to
`● Name ✓ summary` on agent.finished. An engine row shows `■ Runner  ████░░░░ 1,700 sequences` and ends as
`■ Runner ✗ summary`. Only engine rows carry the engine's verdict; agent ✓/✗ is just how the call went.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Literal

from rich.style import Style
from rich.text import Text

from rook.cli.tui.safe_text import clean
from rook.cli.tui.widgets.characters import Character, character
from rook.cli.tui.widgets.sprite import SPRITE_ROWS, Animated, pose_at, shimmer, sprite_lines
from rook.core.events import (
    AgentFinished,
    AgentProgress,
    AgentStarted,
    EngineFinished,
    EngineProgress,
    EngineStarted,
    Event,
)

GOOD = "#62D69B"
BAD = "#FF7A70"
INK = "#ECECEA"
DIM = "#8A8F93"
PULSE_DIM = "#5E6B72"
MIN_SPRITE_WIDTH = 80  # below this, sprites are hidden and rows stay (04 §2.5)
BAR_WIDTH = 12
HEADER_LINE = 2  # which sprite line the name/verb sits on; the detail goes on the next one

WORKER_NAMES = {
    "runner": "Runner", "judge": "Judge", "shrinker": "Shrinker", "replayer": "Replayer",
    "testrunner": "Test runner", "verifier": "Verifier",
}

State = Literal["working", "done"]
Clock = Callable[[], float]


def _mark(ok: bool) -> Text:
    return Text("✓", Style(color=GOOD)) if ok else Text("✗", Style(color=BAD))


class AgentRow(Animated):
    """One Bob agent call, keyed by its `call_id`."""

    DEFAULT_CSS = """
    AgentRow { height: auto; }
    """

    def __init__(
        self, started: Event, *, reduced_motion: bool | None = None, seed: int | None = None,
        truecolor: bool | None = None, compact: bool | None = None, clock: Clock = time.monotonic,
    ) -> None:
        super().__init__(reduced_motion=reduced_motion, seed=seed, truecolor=truecolor)
        data = started.typed_data()
        if not isinstance(data, AgentStarted):
            raise TypeError(f"an AgentRow starts from agent.started, not {started.type}")
        self.call_id = data.call_id
        self.char: Character = character(data.agent)
        self.detail = clean(data.detail)
        self.state: State = "working"
        self.ok: bool | None = None
        self.summary = ""
        self.recorded = False
        self._compact = compact
        self._clock = clock
        self._t0 = clock()

    def wants_animation(self) -> bool:
        return self.state == "working"

    def apply(self, event: Event) -> bool:
        """Apply agent.progress / agent.finished for this call; returns whether the event was ours."""
        if event.type not in ("agent.progress", "agent.finished") or event.data.get("call_id") != self.call_id:
            return False
        if self.state == "done":
            return True  # late progress after the collapse changes nothing
        data = event.typed_data()
        if isinstance(data, AgentProgress):
            self.detail = clean(data.detail)
        elif isinstance(data, AgentFinished):
            self.state = "done"
            self.ok = data.ok and not data.summary.lower().startswith("reject")
            self.summary = clean(data.summary)
            self.recorded = data.recorded
            self.stop_animation()
        self.refresh(layout=True)
        return True

    @property
    def compact(self) -> bool:
        if self._compact is not None:
            return self._compact
        return not self.truecolor or self.app.size.width < MIN_SPRITE_WIDTH

    def render(self) -> Text:
        return self.render_text(self.frame, self.compact, self.truecolor)

    def render_text(self, frame: int, compact: bool, truecolor: bool = True) -> Text:
        name = Text(self.char.name, Style(color=self.char.color, bold=True))
        if self.state == "done":
            line = Text.assemble(Text("● ", Style(color=self.char.color)), name, " ", _mark(bool(self.ok)),
                                 " ", self.summary)
            if self.recorded:
                line.append("  recorded", Style(color=DIM, italic=True))
            return line
        elapsed = self._clock() - self._t0
        header = Text.assemble(name, "  ", shimmer(f"{self.char.verb}…", self.char.color, frame, self.reduced_motion),
                               Text(f" ({elapsed:.1f}s)", Style(color=DIM)))
        detail = Text.assemble(Text("⎿ ", Style(color=DIM)), Text(self.detail, Style(color=DIM)))
        if compact:
            return Text("\n").join([Text.assemble(Text("● ", Style(color=self.char.color)), header),
                                    Text.assemble("  ", detail)])
        sprite = sprite_lines(self.char, pose_at(frame, self.seed, self.reduced_motion), truecolor)
        text_col = [Text() for _ in range(SPRITE_ROWS)]
        text_col[HEADER_LINE] = header
        text_col[HEADER_LINE + 1] = detail
        return Text("\n").join([Text.assemble(s, "  ", t) for s, t in zip(sprite, text_col, strict=True)])


def _progress_label(label: str, count: int | None) -> str:
    """Group the leading count in thousands ("1700 sequences" -> "1,700 sequences")."""
    if count is None:
        return label
    return re.sub(rf"^{count}\b", f"{count:,}", label)


class EngineRow(Animated):
    """One deterministic engine worker, keyed by its `worker`."""

    DEFAULT_CSS = """
    EngineRow { height: auto; }
    """

    def __init__(
        self, started: Event, *, reduced_motion: bool | None = None, seed: int | None = None,
    ) -> None:
        super().__init__(reduced_motion=reduced_motion, seed=seed, truecolor=True)
        data = started.typed_data()
        if not isinstance(data, EngineStarted):
            raise TypeError(f"an EngineRow starts from engine.started, not {started.type}")
        self.worker = data.worker
        self.name_shown = WORKER_NAMES.get(data.worker, clean(data.worker.title()))
        self.label = clean(data.label)
        self.pct = 0.0
        self.state: State = "working"
        self.ok: bool | None = None
        self.summary = ""

    def wants_animation(self) -> bool:
        return self.state == "working"

    def apply(self, event: Event) -> bool:
        if event.type not in ("engine.progress", "engine.finished") or event.data.get("worker") != self.worker:
            return False
        if self.state == "done":
            return True
        data = event.typed_data()
        if isinstance(data, EngineProgress):
            self.pct = max(0.0, min(100.0, data.pct))
            self.label = clean(_progress_label(data.label, data.count))
        elif isinstance(data, EngineFinished):
            self.state = "done"
            self.ok = data.ok
            self.summary = clean(data.summary)
            self.stop_animation()
        self.refresh(layout=True)
        return True

    def render(self) -> Text:
        return self.render_text(self.frame)

    def render_text(self, frame: int) -> Text:
        name = Text(self.name_shown, Style(color=INK, bold=True))
        if self.state == "done":
            return Text.assemble(Text("■ ", Style(color=INK)), name, " ", _mark(bool(self.ok)), " ", self.summary)
        pulse = INK if self.reduced_motion or frame % 8 < 4 else PULSE_DIM
        filled = round(self.pct / 100 * BAR_WIDTH)
        bar = Text.assemble(Text("█" * filled, Style(color=INK)), Text("░" * (BAR_WIDTH - filled), Style(color=DIM)))
        return Text.assemble(Text("■ ", Style(color=pulse)), name, "  ", bar, " ", self.label)


Row = AgentRow | EngineRow


class LiveRows:
    """Routes agent.* / engine.* events to rows. `handle` returns a new row for the caller to mount."""

    def __init__(
        self, *, reduced_motion: bool | None = None, truecolor: bool | None = None, clock: Clock = time.monotonic,
    ) -> None:
        self.reduced_motion = reduced_motion
        self.truecolor = truecolor
        self._clock = clock
        self._agents: dict[str, AgentRow] = {}
        self._engines: dict[str, EngineRow] = {}

    @property
    def active(self) -> list[Row]:
        return [*self._agents.values(), *self._engines.values()]

    def handle(self, event: Event) -> Row | None:
        match event.type:
            case "agent.started":
                row = AgentRow(event, reduced_motion=self.reduced_motion, truecolor=self.truecolor, clock=self._clock)
                self._agents[row.call_id] = row
                return row
            case "engine.started":
                engine = EngineRow(event, reduced_motion=self.reduced_motion)
                self._engines[engine.worker] = engine
                return engine
            case "agent.progress" | "agent.finished":
                agent = self._agents.get(str(event.data.get("call_id")))
                if agent is not None:
                    agent.apply(event)
                    if agent.state == "done":
                        del self._agents[agent.call_id]
            case "engine.progress" | "engine.finished":
                worker = self._engines.get(str(event.data.get("worker")))
                if worker is not None:
                    worker.apply(event)
                    if worker.state == "done":
                        del self._engines[worker.worker]
        return None
