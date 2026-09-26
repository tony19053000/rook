"""ROOK-026: sprite rendering (04 §1.3). Every character is snapshotted as text next to this test.

Regenerate after an intended visual change with: ROOK_UPDATE_SNAPSHOTS=1 uv run pytest tests/unit/test_tui_sprite.py
"""

import os
from pathlib import Path

import pytest
from rich.text import Text
from textual.app import App, ComposeResult

from rook.agents import registry
from rook.cli.tui.widgets.characters import (
    CHARACTERS,
    EYE_ROW,
    GUIDE_TERM_COLOR,
    GUIDE_TERM_EYES,
    HEIGHT,
    MASCOT,
    WIDTH,
    Character,
    character,
    pixels,
)
from rook.cli.tui.widgets.sprite import (
    BLINK_PERIOD,
    BOUNCE_FRAMES,
    GLANCE_CYCLE,
    GLANCE_FRAMES,
    REST,
    SHIMMER_BASE,
    SHIMMER_PEAK,
    SPRITE_ROWS,
    AgentSprite,
    Pose,
    canvas,
    pose_at,
    reduced_motion_from_env,
    shimmer,
    sprite_lines,
)

SNAPSHOTS = Path(__file__).parent / "snapshots" / "sprites"
UPDATE = os.environ.get("ROOK_UPDATE_SNAPSHOTS") == "1"

# The 04 §1.3 table, restated so a registry drift shows up here.
SPEC = {
    "coordinator": ("Coordinator", "circle", "#F5B400", "Planning"),
    "scout": ("Scout", "roundsq", "#10B99A", "Scouting"),
    "mechanic": ("Mechanic", "cloud", "#FF8A00", "Building"),
    "mapper": ("Mapper", "blob", "#1FA8E0", "Mapping"),
    "lawmaker": ("Lawmaker", "tilted", "#9B1FE8", "Drafting rules"),
    "rule_critic": ("Rule Critic", "triangle", "#FF1493", "Reviewing rules"),
    "test_designer": ("Test Designer", "blob", "#FF5A1F", "Designing tests"),
    "strategist": ("Strategist", "circle", "#A86B3C", "Strategizing"),
    "detective": ("Detective", "roundsq", "#4F63FF", "Investigating"),
    "diag_reviewer": ("Diagnosis Reviewer", "triangle", "#F05FAA", "Checking evidence"),
    "surgeon": ("Surgeon", "tilted", "#22B868", "Operating"),
    "fix_reviewer": ("Fix Reviewer", "triangle", "#D6247A", "Reviewing fix"),
    "guide": ("Guide", "small", GUIDE_TERM_COLOR, "Answering"),
}
ALL = [*CHARACTERS.values(), MASCOT]


def _pixel_art(char: Character, pose: Pose) -> list[str]:
    symbol = {None: ".", char.color: "#", char.eye: "o"}
    return ["".join(symbol[p] for p in row) for row in canvas(char, pose)]


def _runs(line: Text) -> list[str]:
    """Merge the per-cell spans of one line into `[start:end] glyphs style` runs."""
    runs: list[tuple[int, int, str]] = []
    for span in line.spans:
        style = str(span.style)
        if runs and runs[-1][1] == span.start and runs[-1][2] == style:
            runs[-1] = (runs[-1][0], span.end, style)
        else:
            runs.append((span.start, span.end, style))
    return [f"  [{a}:{b}] {line.plain[a:b]} {style}" for a, b, style in runs]


def snapshot(char: Character) -> str:
    out = [f"{char.id} · {char.name or '(mascot)'} · {char.shape} · body {char.color} · eyes {char.eye}"]
    for title, pose in (("rest", REST), ("bounce up, blink, look +1", Pose(up=True, blink=True, look=1))):
        out.append(f"pixels ({title}):")
        out += ["  " + row for row in _pixel_art(char, pose)]
        out.append(f"half-blocks ({title}):")
        for i, line in enumerate(sprite_lines(char, pose)):
            out.append(f" {i}|{line.plain}|")
            out += _runs(line)
    return "\n".join(out) + "\n"


@pytest.mark.parametrize("char", ALL, ids=[c.id for c in ALL])
def test_character_snapshot(char: Character) -> None:
    path = SNAPSHOTS / f"{char.id}.txt"
    got = snapshot(char)
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(got, encoding="utf-8")
    assert path.exists(), f"missing snapshot {path.name}; run with ROOK_UPDATE_SNAPSHOTS=1"
    assert got == path.read_text(encoding="utf-8")


def test_every_registry_agent_has_its_spec_character() -> None:
    assert set(CHARACTERS) == set(registry.AGENTS) == set(SPEC)
    for agent_id, (name, shape, color, verb) in SPEC.items():
        c = CHARACTERS[agent_id]
        assert (c.name, c.shape, c.color, c.verb) == (name, shape, color, verb)
    assert CHARACTERS["guide"].eye == GUIDE_TERM_EYES
    assert (MASCOT.shape, MASCOT.color) == ("cloud", "#E0563F")


def test_unknown_agent_still_renders() -> None:
    c = character("new_agent")
    assert c.name == "New Agent"
    assert len(sprite_lines(c)) == SPRITE_ROWS


@pytest.mark.parametrize("char", ALL, ids=[c.id for c in ALL])
def test_grid_and_eyes(char: Character) -> None:
    grid = pixels(char)
    assert len(grid) == HEIGHT and all(len(row) == WIDTH for row in grid)
    eye = EYE_ROW[char.shape]
    for x in (4, 7):
        assert grid[eye][x] == char.eye and grid[eye + 1][x] == char.eye
    blink = pixels(char, blink=True)
    for x in (4, 7):
        assert blink[eye][x] == char.color and blink[eye + 1][x] == char.eye
    looked = pixels(char, look=-1)
    assert looked[eye][3] == char.eye and looked[eye][6] == char.eye and looked[eye][4] == char.color


def test_half_block_glyph_rules() -> None:
    lines = sprite_lines(CHARACTERS["scout"])
    assert len(lines) == SPRITE_ROWS and all(len(line.plain) == WIDTH for line in lines)
    assert set("".join(line.plain for line in lines)) <= {" ", "▀", "▄"}


def test_bounce_shifts_up_one_pixel() -> None:
    char = CHARACTERS["coordinator"]
    rest, up = canvas(char, REST), canvas(char, Pose(up=True))
    assert rest[1:11] == up[0:10]
    assert rest[0] == [None] * WIDTH


def test_no_truecolor_falls_back_to_a_dot() -> None:
    lines = sprite_lines(CHARACTERS["surgeon"], truecolor=False)
    assert [line.plain for line in lines] == ["●"]
    assert str(lines[0].style) == CHARACTERS["surgeon"].color.lower()


def test_motion_cycles() -> None:
    frames = range(BLINK_PERIOD * 4)
    poses = [pose_at(f, 0, reduced=False) for f in frames]
    assert pose_at(0, 0, False).up and not pose_at(BOUNCE_FRAMES, 0, False).up
    assert sum(p.blink for p in poses[:BLINK_PERIOD]) == 4
    assert [pose_at(i * GLANCE_FRAMES, 0, False).look for i in range(8)] == list(GLANCE_CYCLE)
    # different seeds give a different phase
    assert [pose_at(f, 0, False) for f in range(40)] != [pose_at(f, 13, False) for f in range(40)]


def test_reduced_motion_is_static() -> None:
    assert {pose_at(f, 7, reduced=True) for f in range(200)} == {REST}
    assert shimmer("Planning…", "#F5B400", 30, reduced=True) == shimmer("Planning…", "#F5B400", 3, reduced=True)


def test_shimmer_moves_a_highlight() -> None:
    def peak(frame: int) -> int:
        text = shimmer("Investigating…", "#4F63FF", frame, reduced=False)
        return next(s.start for s in text.spans if str(s.style) == SHIMMER_PEAK.lower())

    assert peak(10) < peak(14)
    base = shimmer("Investigating…", "#4F63FF", 0, reduced=False)
    assert str(base.spans[-1].style) == SHIMMER_BASE.lower()


@pytest.mark.parametrize(("value", "expected"), [("", False), ("0", False), ("1", True), ("yes", True)])
def test_no_motion_env(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("NO_MOTION", value)
    assert reduced_motion_from_env() is expected


class _SpriteApp(App[None]):
    def __init__(self, sprite: AgentSprite) -> None:
        super().__init__()
        self.sprite = sprite

    def compose(self) -> ComposeResult:
        yield self.sprite


async def test_sprite_widget_animates_and_reduced_motion_does_not() -> None:
    moving = AgentSprite(MASCOT, reduced_motion=False, seed=0, truecolor=True)
    async with _SpriteApp(moving).run_test() as pilot:
        assert moving.animating
        await pilot.pause(0.3)
        assert moving.frame > 0
        assert moving.size.width == WIDTH and moving.size.height == SPRITE_ROWS

    still = AgentSprite(MASCOT, reduced_motion=True, seed=0, truecolor=True)
    async with _SpriteApp(still).run_test() as pilot:
        await pilot.pause(0.3)
        assert not still.animating and still.frame == 0
        assert still.render().plain == "\n".join(line.plain for line in sprite_lines(MASCOT))
