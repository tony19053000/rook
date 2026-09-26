"""ROOK-026: AgentRow / EngineRow / LiveRows lifecycles, driven by fake events (04 §1.3)."""

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll

from rook.cli.tui.widgets.rows import BAD, GOOD, AgentRow, EngineRow, LiveRows
from rook.cli.tui.widgets.sprite import SPRITE_ROWS
from rook.core.events import Event, validate_data

_seq = 0


def ev(event_type: str, **data: Any) -> Event:
    global _seq
    _seq += 1
    return Event(seq=_seq, ts="2026-09-26T12:00:00.000Z", run_id="r1", type=event_type,
                 data=validate_data(event_type, data))


def started(agent: str = "scout", call_id: str = "c1", detail: str = "reading README.md") -> Event:
    return ev("agent.started", agent=agent, call_id=call_id, detail=detail)


def progress(call_id: str = "c1", detail: str = "reading src/refunds.js", agent: str = "scout") -> Event:
    return ev("agent.progress", agent=agent, call_id=call_id, detail=detail)


def finished(call_id: str = "c1", ok: bool = True, summary: str = "Node.js · Express · 7 endpoints",
             agent: str = "scout", recorded: bool = False) -> Event:
    return ev("agent.finished", agent=agent, call_id=call_id, ok=ok, summary=summary, cost=0.02,
              recorded=recorded)


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def lines(text: Any) -> list[str]:
    return [line.rstrip() for line in text.plain.split("\n")]


# --- AgentRow ---------------------------------------------------------------------------------------


def test_agent_row_working_layout_with_sprite() -> None:
    clock = FakeClock()
    row = AgentRow(started(), reduced_motion=True, seed=0, clock=clock)
    clock.t += 3.24
    out = lines(row.render_text(0, compact=False))
    assert len(out) == SPRITE_ROWS
    assert out[2].endswith("  Scout  Scouting… (3.2s)")
    assert out[3].endswith("  ⎿ reading README.md")
    assert set(out[2][:12]) <= {" ", "▀", "▄"}  # the sprite column


def test_agent_row_compact_layout() -> None:
    row = AgentRow(started(), reduced_motion=True, clock=FakeClock())
    assert lines(row.render_text(0, compact=True)) == ["● Scout  Scouting… (0.0s)", "  ⎿ reading README.md"]


def test_agent_row_progress_then_collapse() -> None:
    row = AgentRow(started(), reduced_motion=True, clock=FakeClock())
    assert row.apply(progress()) is True
    assert "⎿ reading src/refunds.js" in row.render_text(0, compact=True).plain
    assert row.apply(finished()) is True
    assert row.state == "done" and row.ok is True
    text = row.render_text(0, compact=False)
    assert lines(text) == ["● Scout ✓ Node.js · Express · 7 endpoints"]
    assert any(str(s.style) == GOOD.lower() for s in text.spans)
    # late progress after the collapse changes nothing
    assert row.apply(progress(detail="late")) is True
    assert lines(row.render_text(0, compact=False)) == ["● Scout ✓ Node.js · Express · 7 endpoints"]


def test_agent_row_ignores_other_calls_and_types() -> None:
    row = AgentRow(started(), reduced_motion=True, clock=FakeClock())
    assert row.apply(progress(call_id="c2")) is False
    assert row.apply(ev("engine.started", worker="runner", label="seed 1")) is False
    assert row.detail == "reading README.md"


@pytest.mark.parametrize(("ok", "summary"), [(False, "bob timed out after 120s"),
                                             (True, "rejected \"order is not None\": a code check")])
def test_agent_row_failure_or_rejection_shows_cross(ok: bool, summary: str) -> None:
    row = AgentRow(started(agent="rule_critic"), reduced_motion=True, clock=FakeClock())
    row.apply(finished(agent="rule_critic", ok=ok, summary=summary))
    text = row.render_text(0, compact=False)
    assert text.plain.startswith("● Rule Critic ✗ ")
    assert any(str(s.style) == BAD.lower() for s in text.spans)


def test_agent_row_recorded_tag() -> None:
    row = AgentRow(started(), reduced_motion=True, clock=FakeClock())
    row.apply(finished(recorded=True))
    assert row.render_text(0, compact=False).plain.endswith("  recorded")


def test_agent_row_needs_agent_started() -> None:
    with pytest.raises(TypeError):
        AgentRow(progress())


# --- EngineRow --------------------------------------------------------------------------------------


def test_engine_row_lifecycle() -> None:
    row = EngineRow(ev("engine.started", worker="runner", label="seed 7"), reduced_motion=True)
    assert row.render_text(0).plain == "■ Runner  ░░░░░░░░░░░░ seed 7"
    assert row.apply(ev("engine.progress", worker="runner", pct=50, label="1700 sequences", count=1700))
    assert row.render_text(0).plain == "■ Runner  ██████░░░░░░ 1,700 sequences"
    assert row.apply(ev("engine.progress", worker="judge", pct=90, label="9 checks", count=9)) is False
    assert row.apply(ev("engine.finished", worker="runner", ok=False,
                        summary="Rule broken · refunds ≤ paid · 3,412 sequences"))
    text = row.render_text(0)
    assert text.plain == "■ Runner ✗ Rule broken · refunds ≤ paid · 3,412 sequences"
    assert any(str(s.style) == BAD.lower() for s in text.spans)


def test_engine_row_success_and_names() -> None:
    row = EngineRow(ev("engine.started", worker="testrunner", label="npm test"), reduced_motion=True)
    row.apply(ev("engine.finished", worker="testrunner", ok=True, summary="npm test: 12 passed"))
    assert row.render_text(0).plain == "■ Test runner ✓ npm test: 12 passed"


def test_engine_row_pulse_and_reduced_motion() -> None:
    moving = EngineRow(ev("engine.started", worker="shrinker", label="12 steps"), reduced_motion=False)
    still = EngineRow(ev("engine.started", worker="shrinker", label="12 steps"), reduced_motion=True)
    assert moving.render_text(0).spans[0].style != moving.render_text(4).spans[0].style
    assert still.render_text(0).spans[0].style == still.render_text(4).spans[0].style


# --- LiveRows + a mounted transcript ----------------------------------------------------------------


def test_live_rows_routes_parallel_agents_and_engines() -> None:
    live = LiveRows(reduced_motion=True, clock=FakeClock())
    mapper = live.handle(started(agent="mapper", call_id="m1", detail="reading routes"))
    lawmaker = live.handle(started(agent="lawmaker", call_id="l1", detail="reading models"))
    runner = live.handle(ev("engine.started", worker="runner", label="seed 1"))
    assert isinstance(mapper, AgentRow) and isinstance(lawmaker, AgentRow) and isinstance(runner, EngineRow)
    assert len(live.active) == 3
    assert live.handle(progress(call_id="l1", agent="lawmaker", detail="reading refunds.js")) is None
    assert lawmaker.detail == "reading refunds.js" and mapper.detail == "reading routes"
    live.handle(finished(call_id="m1", agent="mapper", summary="6 actions"))
    assert mapper.state == "done" and lawmaker.state == "working"
    live.handle(ev("engine.finished", worker="runner", ok=True, summary="all rules held"))
    assert live.active == [lawmaker]
    # unknown call ids and unrelated events are ignored
    assert live.handle(progress(call_id="nope")) is None
    assert live.handle(ev("log", level="info", text="hi")) is None


class Transcript(App[None]):
    def __init__(self, events: list[Event], reduced_motion: bool, truecolor: bool | None = True) -> None:
        super().__init__()
        self.live = LiveRows(reduced_motion=reduced_motion, truecolor=truecolor)
        self.events = events

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="log")

    async def feed(self, count: int) -> None:
        log = self.query_one("#log", VerticalScroll)
        for _ in range(count):
            row = self.live.handle(self.events.pop(0))
            if row is not None:
                await log.mount(row)


async def test_mounted_rows_animate_then_collapse() -> None:
    events = [started(), progress(), ev("engine.started", worker="replayer", label="replay 10x"),
              ev("engine.progress", worker="replayer", pct=100, label="10/10 reproduced", count=10),
              finished(), ev("engine.finished", worker="replayer", ok=True, summary="10/10 reproduced")]
    app = Transcript(events, reduced_motion=False)
    async with app.run_test(size=(100, 30)) as pilot:
        await app.feed(3)
        agent, engine = app.query(AgentRow).first(), app.query(EngineRow).first()
        assert agent.animating and engine.animating
        await pilot.pause(0.3)
        assert agent.frame > 0
        assert agent.size.height == SPRITE_ROWS
        await app.feed(3)
        await pilot.pause()
        assert not agent.animating and not engine.animating
        assert agent.size.height == 1 and engine.size.height == 1
        assert str(agent.render()).startswith("● Scout ✓")


async def test_mounted_rows_reduced_motion_and_narrow_terminal() -> None:
    app = Transcript([started(agent="guide", detail="reading live run data")], reduced_motion=True)
    async with app.run_test(size=(60, 20)) as pilot:
        await app.feed(1)
        await pilot.pause(0.2)
        row = app.query(AgentRow).first()
        assert not row.animating and row.frame == 0
        assert row.compact  # below 80 columns the sprite is hidden
        assert row.size.height == 2


async def test_no_truecolor_terminal_uses_the_compact_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLORTERM", raising=False)
    app = Transcript([started()], reduced_motion=True, truecolor=None)
    async with app.run_test(size=(120, 20)) as pilot:
        await app.feed(1)
        await pilot.pause()
        row = app.query(AgentRow).first()
        assert app.console.color_system != "truecolor"
        assert row.compact and row.size.height == 2
        assert str(row.render()).startswith("● Scout  Scouting…")
