"""ROOK-026 review fix: untrusted event text never reaches the terminal with control characters."""

import re

import pytest

from rook.cli.tui.safe_text import clean
from rook.cli.tui.widgets.rows import AgentRow, EngineRow, LiveRows
from rook.core.events import Event, validate_data

CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")  # everything but the \n that joins row lines
EVIL = "safe\x1b[31mRED\x1b]0;pwn\x07\x1b[0m\x9b2J\x85\x00\x7f\r\ttail" + "X" * 300


def ev(seq: int, event_type: str, **data: object) -> Event:
    return Event(seq=seq, ts="2026-09-26T12:00:00.000Z", run_id="r1", type=event_type,
                 data=validate_data(event_type, data))


def test_clean_drops_controls_and_flattens_whitespace() -> None:
    assert clean("a\x1b[31mb\x07c\x9bd\x7fe") == "a[31mbcde"
    assert clean("line1\nline2\tx\r") == "line1 line2 x "
    assert clean("Paid ₹100 · Refunded ₹110 ✓") == "Paid ₹100 · Refunded ₹110 ✓"
    assert not CONTROL.search(clean("".join(chr(c) for c in range(0xA0))))


@pytest.mark.parametrize("compact", [False, True])
def test_agent_row_strips_controls(compact: bool) -> None:
    live = LiveRows(reduced_motion=True, truecolor=True)
    row = live.handle(ev(1, "agent.started", agent="evil\x1b]0;x\x07", call_id="c1", detail=EVIL))
    assert isinstance(row, AgentRow)
    assert not CONTROL.search(row.render_text(0, compact=compact).plain)
    live.handle(ev(2, "agent.progress", agent="scout", call_id="c1", detail=EVIL))
    assert not CONTROL.search(row.render_text(5, compact=compact).plain)
    live.handle(ev(3, "agent.finished", agent="scout", call_id="c1", ok=True, summary=EVIL, cost=0.0,
                   recorded=True))
    out = row.render_text(0, compact=compact).plain
    assert not CONTROL.search(out) and "\n" not in out
    assert "safe[31mRED" in out


def test_engine_row_strips_controls() -> None:
    live = LiveRows(reduced_motion=True)
    row = live.handle(ev(1, "engine.started", worker="runner", label=EVIL))
    assert isinstance(row, EngineRow)
    assert not CONTROL.search(row.render_text(0).plain)
    live.handle(ev(2, "engine.progress", worker="runner", pct=10, label=EVIL, count=3))
    assert not CONTROL.search(row.render_text(0).plain)
    live.handle(ev(3, "engine.finished", worker="runner", ok=False, summary=EVIL))
    out = row.render_text(0).plain
    assert not CONTROL.search(out) and "\n" not in out
