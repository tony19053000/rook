"""Agent characters: shape masks, eyes and colours (docs/04_FRONTEND_SPEC.md §1.3, the sprite contract).

A sprite is a 12 x 10 pixel grid. `pixels()` returns it as rows of hex colours (None = transparent);
drawing it into the terminal is `sprite.py`'s job.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from rook.agents import registry
from rook.agents.registry import Shape
from rook.cli.tui.safe_text import clean

WIDTH = 12
HEIGHT = 10

EYE_WHITE = "#FFFFFF"
GUIDE_TERM_COLOR = "#E9ECEF"  # the web Guide is grey; in the terminal it is near-white with dark eyes
GUIDE_TERM_EYES = "#1B1F24"
MASCOT_COLOR = "#E0563F"

Grid = list[list[str | None]]


def _rot(dx: float, dy: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def _circle(x: int, y: int) -> bool:
    return (x - 5.5) ** 2 + (y - 4.8) ** 2 <= 4.9**2


def _small(x: int, y: int) -> bool:
    return (x - 5.5) ** 2 + (y - 6) ** 2 <= 3.6**2


def _roundsq(x: int, y: int) -> bool:
    dx, dy = abs(x - 5.5), abs(y - 4.8)
    return dx <= 5 and dy <= 4.6 and dx + dy <= 8.2


def _tilted(x: int, y: int) -> bool:
    px, py = _rot(x - 5.5, y - 4.8, -14)
    dx, dy = abs(px), abs(py)
    return dx <= 4.4 and dy <= 4.1 and dx + dy <= 7.4


def _triangle(x: int, y: int) -> bool:
    dx = abs(x - 5.5)
    return y >= 0 and dx <= (y + 0.6) * 0.62 and not (y >= 9 and dx > 4.6)


_CLOUD = ((3.4, 5.6, 3.1), (7.6, 5.6, 3.1), (5.5, 3.4, 3.1), (5.5, 6.4, 3.2))


def _cloud(x: int, y: int) -> bool:
    return any((x - cx) ** 2 + (y - cy) ** 2 <= r * r for cx, cy, r in _CLOUD)


def _blob(x: int, y: int) -> bool:
    return ((x - 5.5) / 5.6) ** 2 + ((y - 5.2) / 4.3) ** 2 <= 1


SHAPES: dict[Shape, Callable[[int, int], bool]] = {
    "circle": _circle, "small": _small, "roundsq": _roundsq, "tilted": _tilted,
    "triangle": _triangle, "cloud": _cloud, "blob": _blob,
}
EYE_ROW: dict[Shape, int] = {"circle": 3, "small": 5, "roundsq": 3, "tilted": 3, "triangle": 6, "cloud": 4, "blob": 4}


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    shape: Shape
    color: str
    eye: str
    verb: str


def _from_registry(agent_id: str) -> Character:
    spec = registry.get(agent_id)
    if agent_id == "guide":
        return Character(agent_id, spec.name, spec.character_shape, GUIDE_TERM_COLOR, GUIDE_TERM_EYES, spec.verb)
    return Character(agent_id, spec.name, spec.character_shape, spec.color, EYE_WHITE, spec.verb)


CHARACTERS: dict[str, Character] = {agent_id: _from_registry(agent_id) for agent_id in registry.AGENTS}
MASCOT = Character("mascot", "Rook", "cloud", MASCOT_COLOR, EYE_WHITE, "")


def character(agent_id: str) -> Character:
    """The character for an event's `agent`; unknown ids get a neutral circle so a row still renders."""
    found = CHARACTERS.get(agent_id)
    if found is not None:
        return found
    return Character(agent_id, clean(agent_id).replace("_", " ").title(), "circle", "#8E99A6", EYE_WHITE, "Working")


def pixels(char: Character, look: int = 0, blink: bool = False) -> Grid:
    """The 12 x 10 grid. Eyes are 2 px tall at x = 4+look and 7+look; blinking keeps only the bottom pixel."""
    inside = SHAPES[char.shape]
    eye_row = EYE_ROW[char.shape]
    eye_cols = (4 + look, 7 + look)
    eye_rows = (eye_row + 1,) if blink else (eye_row, eye_row + 1)
    grid: Grid = []
    for y in range(HEIGHT):
        row: list[str | None] = []
        for x in range(WIDTH):
            if not inside(x, y):
                row.append(None)
            elif x in eye_cols and y in eye_rows:
                row.append(char.eye)
            else:
                row.append(char.color)
        grid.append(row)
    return grid
