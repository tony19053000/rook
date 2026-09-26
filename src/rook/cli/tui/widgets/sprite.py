"""Half-block sprite drawing, motion (bounce, blink, glance, shimmer) and the AgentSprite widget (04 §1.3).

Two pixels share one terminal cell: `▀` with fg = top and bg = bottom, `▄` with fg = bottom, or a space.
Everything here is a pure function of (character, frame, seed, reduced motion), so it snapshots cleanly.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass

from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget

from rook.cli.tui.widgets.characters import HEIGHT, WIDTH, Character, Grid, pixels

FPS = 12
BOUNCE_FRAMES = 9  # ~0.75 s at 12 fps
BLINK_PERIOD = 70
BLINK_FRAMES = 4
GLANCE_FRAMES = 22  # frames per step of the glance cycle
GLANCE_CYCLE = (0, 0, 1, 1, 0, 0, -1, -1)

SHIMMER_BASE = "#A3AFB5"
SHIMMER_PEAK = "#FFFFFF"

# One pixel of headroom so the bounce can shift the sprite up by half a cell; 12 px = 6 terminal rows.
CANVAS_HEIGHT = HEIGHT + 2
SPRITE_ROWS = CANVAS_HEIGHT // 2
DOT = "●"


def reduced_motion_from_env() -> bool:
    """`NO_MOTION=1` (any non-empty value except "0") turns every animation off."""
    value = os.environ.get("NO_MOTION", "")
    return value not in ("", "0")


def new_seed() -> int:
    """A random phase so two agents on screen never move in sync."""
    return random.randrange(BLINK_PERIOD * BOUNCE_FRAMES)


@dataclass(frozen=True)
class Pose:
    up: bool = False
    blink: bool = False
    look: int = 0


REST = Pose()


def pose_at(frame: int, seed: int, reduced: bool) -> Pose:
    if reduced:
        return REST
    phase = frame + seed
    return Pose(
        up=(phase // BOUNCE_FRAMES) % 2 == 0,
        blink=phase % BLINK_PERIOD < BLINK_FRAMES,
        look=GLANCE_CYCLE[(phase // GLANCE_FRAMES) % len(GLANCE_CYCLE)],
    )


def canvas(char: Character, pose: Pose = REST) -> Grid:
    """The sprite placed on a 12 x 12 canvas: one empty row on top at rest, none when bounced up."""
    grid = pixels(char, look=pose.look, blink=pose.blink)
    empty: list[str | None] = [None] * WIDTH
    top = 0 if pose.up else 1
    return [list(empty) for _ in range(top)] + grid + [list(empty) for _ in range(CANVAS_HEIGHT - HEIGHT - top)]


def half_blocks(grid: Grid) -> list[Text]:
    """Fold pixel rows in pairs into one line of half-block cells each."""
    lines: list[Text] = []
    for y in range(0, len(grid), 2):
        line = Text()
        for top, bottom in zip(grid[y], grid[y + 1], strict=True):
            if top is None and bottom is None:
                line.append(" ")
            elif bottom is None:
                line.append("▀", Style(color=top))
            elif top is None:
                line.append("▄", Style(color=bottom))
            else:
                line.append("▀", Style(color=top, bgcolor=bottom))
        lines.append(line)
    return lines


def sprite_lines(char: Character, pose: Pose = REST, truecolor: bool = True) -> list[Text]:
    """The sprite as terminal lines; without truecolor it is a single coloured dot (04 §2.5)."""
    if not truecolor:
        return [Text(DOT, Style(color=char.color))]
    return half_blocks(canvas(char, pose))


def shimmer(text: str, color: str, frame: int, reduced: bool) -> Text:
    """A bright highlight wave moving across `text`; static in the agent colour with reduced motion."""
    if reduced:
        return Text(text, Style(color=color))
    out = Text()
    n = len(text)
    pos = (frame * 0.5) % (n + 10) - 5
    for i, ch in enumerate(text):
        distance = abs(i - pos)
        shade = SHIMMER_PEAK if distance < 1.5 else color if distance < 3.2 else SHIMMER_BASE
        out.append(ch, Style(color=shade))
    return out


def is_truecolor(widget: Widget) -> bool:
    return widget.app.console.color_system == "truecolor"


class Animated(Widget):
    """A widget whose `frame` advances at 12 fps unless reduced motion is on."""

    frame: reactive[int] = reactive(0)

    def __init__(
        self, *, reduced_motion: bool | None = None, seed: int | None = None, truecolor: bool | None = None,
        name: str | None = None, id: str | None = None, classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.reduced_motion = reduced_motion_from_env() if reduced_motion is None else reduced_motion
        self.seed = new_seed() if seed is None else seed
        self._truecolor = truecolor
        self._timer: Timer | None = None

    @property
    def truecolor(self) -> bool:
        return is_truecolor(self) if self._truecolor is None else self._truecolor

    @property
    def animating(self) -> bool:
        return self._timer is not None

    def on_mount(self) -> None:
        if not self.reduced_motion and self.wants_animation():
            self._timer = self.set_interval(1 / FPS, self._tick)

    def wants_animation(self) -> bool:
        return True

    def stop_animation(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self.frame += 1


class AgentSprite(Animated):
    """A standalone animated character (e.g. the mascot on the home screen)."""

    DEFAULT_CSS = f"""
    AgentSprite {{ width: {WIDTH}; height: {SPRITE_ROWS}; }}
    """

    def __init__(
        self, char: Character, *, reduced_motion: bool | None = None, seed: int | None = None,
        truecolor: bool | None = None, id: str | None = None,
    ) -> None:
        super().__init__(reduced_motion=reduced_motion, seed=seed, truecolor=truecolor, id=id)
        self.char = char

    def render(self) -> Text:
        return Text("\n").join(sprite_lines(self.char, pose_at(self.frame, self.seed, self.reduced_motion),
                                            self.truecolor))
