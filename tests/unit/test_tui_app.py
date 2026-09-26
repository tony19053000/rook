"""Textual pilot tests for the TUI shell (ROOK-025)."""

from __future__ import annotations

from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Static
from tui_samples import SAMPLES

from rook.cli.logo import WORD
from rook.cli.tui.app import PLACEHOLDER, RookApp
from rook.cli.tui.auth import AuthState, StubAuth
from rook.cli.tui.backend import make_event
from rook.cli.tui.render import clean_data
from rook.cli.tui.safe_text import clean, clean_multiline
from rook.cli.tui.widgets.shell import HomeBox, Logo
from rook.core.events import EVENT_TYPES

SIZE = (80, 24)


class FakeBackend:
    def __init__(self, running: bool = False) -> None:
        self.running = running
        self.calls: list[tuple[str, ...]] = []

    def bind(self, app: RookApp) -> None:
        self.app = app

    def submit(self, text: str) -> None:
        self.calls.append(("submit", text))

    def command(self, name: str, arg: str) -> None:
        self.calls.append(("command", name, arg))

    def answer(self, question_id: str, answer: str) -> None:
        self.calls.append(("answer", question_id, answer))

    def interrupt(self) -> None:
        self.calls.append(("interrupt",))


class SigningAuth(StubAuth):
    async def sign_in(self) -> str | None:
        return "aayush"

    async def connect_github(self) -> int | None:
        return 3


def lines(app: RookApp) -> list[str]:
    return [str(w.render()) for w in app.transcript.children if isinstance(w, Static)]


def text(app: RookApp) -> str:
    return "\n".join(lines(app))


async def booted(pilot: Pilot[Any], app: RookApp) -> None:
    for _ in range(200):
        if app.ready:
            await pilot.pause()
            return
        await pilot.pause(0.02)
    raise AssertionError("the app never finished booting")


async def type_text(pilot: Pilot[Any], value: str) -> None:
    await pilot.press(*[{" ": "space", "?": "question_mark", "/": "slash"}.get(ch, ch) for ch in value])


def event(event_type: str, seq: int = 1, **overrides: Any) -> Any:
    return make_event(seq, event_type, {**SAMPLES[event_type], **overrides}, run_id="r1")


# --- launch --------------------------------------------------------------------------------------------


async def test_launch_first_run_shows_logo_steps_home_and_footer() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        assert app.query_one(Logo).complete
        body = text(app)
        assert "v0.1.0 · find the smallest sequence that breaks your software" in body
        assert "1/2 Sign in with Google" in body and "2/2 Connect GitHub" in body
        assert "✻ Rook · not signed in · GitHub not connected" in str(app.query_one(HomeBox).render())
        assert app.prompt.placeholder == PLACEHOLDER
        assert app.focused is app.prompt
        assert app.footer_bar.text == "? for shortcuts · none · 0.00 coins"
        assert not app.status_bar.display


async def test_logo_is_drawn_letter_by_letter_with_motion() -> None:
    app = RookApp(motion=True, letter_delay=0.05)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.01)
        logo = app.query_one(Logo)
        assert logo.letters < len(WORD)
        await booted(pilot, app)
        assert logo.complete


async def test_first_run_signs_in_through_the_auth_provider() -> None:
    app = RookApp(auth=SigningAuth(), motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        body = text(app)
        assert "✓ Signed in as aayush (Google)" in body
        assert "✓ GitHub connected · 3 repos shared" in body
        assert "signed in as aayush · GitHub connected" in str(app.query_one(HomeBox).render())


async def test_first_run_is_skipped_with_credentials() -> None:
    app = RookApp(auth=StubAuth(AuthState(user="aayush", github_repos=2)), motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        assert "Sign in with Google" not in text(app)
        assert "signed in as aayush" in str(app.query_one(HomeBox).render())


# --- slash completion ------------------------------------------------------------------------------------


async def test_tab_completes_a_unique_slash_command() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "/he")
        await pilot.press("tab")
        await pilot.pause()
        assert app.prompt.value == "/help "
        assert app.focused is app.prompt
        assert not app.suggestions.display


async def test_tab_with_several_matches_lists_them() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "/re")
        await pilot.press("tab")
        await pilot.pause()
        assert app.prompt.value == "/rep"
        assert app.suggestions.display
        assert str(app.suggestions.render()) == "/repo  /replay"
        await pilot.press("l")
        await pilot.pause()
        assert not app.suggestions.display
        await pilot.press("tab")
        await pilot.pause()
        assert app.prompt.value == "/replay "


async def test_tab_on_plain_text_keeps_focus() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "hi")
        await pilot.press("tab")
        await pilot.pause()
        assert app.prompt.value == "hi" and app.focused is app.prompt


# --- help and commands -----------------------------------------------------------------------------------


async def test_help_lists_every_command_and_shortcut() -> None:
    backend = FakeBackend()
    app = RookApp(backend=backend, motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "/help")
        await pilot.press("enter")
        await pilot.pause()
        body = text(app)
        for command in ("/run [repo]", "/repo", "/rules", "/replay <cx>", "/explain <cx>", "/verify <cx>",
                        "/dashboard", "/login", "/github", "/logout", "/auto on|off", "/help"):
            assert command in body
        assert "Ctrl+C twice" in body and "Tab" in body
        assert backend.calls == []
        assert app.prompt.value == ""


async def test_question_mark_in_empty_input_shows_shortcuts() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await pilot.press("question_mark")
        await pilot.pause()
        assert app.prompt.value == ""
        assert "Shortcuts" in lines(app)
        await type_text(pilot, "why?")
        assert app.prompt.value == "why?"


async def test_commands_are_validated_then_sent_to_the_backend() -> None:
    backend = FakeBackend()
    app = RookApp(backend=backend, motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        for value in ("/nope", "/replay", "/run shop-app", "/auto on"):
            await type_text(pilot, value)
            await pilot.press("enter")
        await pilot.pause()
        body = text(app)
        assert "Unknown command /nope. Type /help to see the commands." in body
        assert "Usage: /replay <cx>" in body
        assert "✓ Auto-approve on" in body and app.auto
        assert backend.calls == [("command", "run", "shop-app"), ("command", "auto", "on")]


async def test_plain_text_goes_to_the_backend_and_offline_backend_explains() -> None:
    backend = FakeBackend()
    app = RookApp(backend=backend, motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "find bugs in my app")
        await pilot.press("enter")
        await pilot.pause()
        assert backend.calls == [("submit", "find bugs in my app")]
        assert "> find bugs in my app" in lines(app)

    offline = RookApp(motion=False)
    async with offline.run_test(size=SIZE) as pilot:
        await booted(pilot, offline)
        await type_text(pilot, "hello")
        await pilot.press("enter")
        await pilot.pause()
        assert "Runs aren't connected in this build yet." in lines(offline)


async def test_history_up_and_down() -> None:
    app = RookApp(backend=FakeBackend(), motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        for value in ("first", "second"):
            await type_text(pilot, value)
            await pilot.press("enter")
        await type_text(pilot, "dr")
        await pilot.press("up")
        assert app.prompt.value == "second"
        await pilot.press("up")
        assert app.prompt.value == "first"
        await pilot.press("down", "down")
        assert app.prompt.value == "dr"


# --- keys ------------------------------------------------------------------------------------------------


async def test_ctrl_c_twice_quits() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running
        assert app.footer_bar.hint == "Press Ctrl+C again to quit"
        await pilot.press("ctrl+c")
        await pilot.pause()
    assert app.return_code == 0


async def test_single_ctrl_c_notice_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rook.cli.tui.app.CONFIRM_WINDOW", 0.05)
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await pilot.press("ctrl+c")
        await pilot.pause(0.2)
        assert app.footer_bar.hint == "? for shortcuts"
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running


async def test_escape_interrupts_a_run_after_confirmation() -> None:
    backend = FakeBackend(running=True)
    app = RookApp(backend=backend, motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        assert backend.calls == []
        assert app.footer_bar.hint == "Press Esc again to interrupt the run"
        await pilot.press("escape")
        await pilot.pause()
        assert backend.calls == [("interrupt",)]


async def test_question_is_answered_with_enter_or_cancelled_with_escape() -> None:
    backend = FakeBackend()
    app = RookApp(backend=backend, motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(event("question.asked"))
        await type_text(pilot, "y")
        await pilot.press("enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q1", "y")]
        assert app.active_question is None

        app.show_event(event("question.asked", seq=2, question_id="q2"))
        await pilot.press("escape")
        await pilot.pause()
        assert app.active_question is None
        assert "  · Question cancelled" in lines(app)


# --- events, status bar, footer --------------------------------------------------------------------------


async def test_events_drive_status_bar_and_footer() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(event("run.created", 1))
        app.show_event(event("search.progress", 2))
        app.show_event(event("cost.update", 3))
        await pilot.pause()
        assert app.status_bar.display
        assert app.status_bar.message == "Searching 2,140 sequences · 1,140/s"
        assert app.footer_bar.text == "? for shortcuts · shop-app · 0.46 coins"
        app.show_event(event("run.finished", 4))
        await pilot.pause()
        assert not app.status_bar.display
        assert app.footer_bar.text == "? for shortcuts · shop-app · 1 fix verified · 0.46 coins"


async def test_every_event_type_renders_without_markup_injection() -> None:
    assert set(SAMPLES) <= set(EVENT_TYPES)
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        for seq, event_type in enumerate(SAMPLES, 1):
            app.show_event(event(event_type, seq))
        await pilot.pause()
        body = text(app)
        for expected in ("◆ Scout  reading repo", "a small shop [with refunds]", "COUNTEREXAMPLE cx_001",
                         "Root cause src/refunds.js : 42", "✓ FIX VERIFIED", "✓ PR #88 opened",
                         "◆ Guide 2,140 sequences so far.", "Found 2 actions: buy  refund"):
            assert expected in body


async def test_custom_views_replace_the_default() -> None:
    app = RookApp(motion=False)
    seen: list[str] = []
    app.views["agent.started"] = lambda ev, transcript: seen.append(ev.data["agent"])
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(event("agent.started"))
        assert seen == ["scout"]
        assert "◆ Scout  reading repo" not in text(app)


# --- 80 columns ------------------------------------------------------------------------------------------


async def test_renders_at_80_columns() -> None:
    app = RookApp(auth=SigningAuth(), motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_text(pilot, "/help")
        await pilot.press("enter")
        for seq, event_type in enumerate(SAMPLES, 1):
            app.show_event(event(event_type, seq))
        app.show_event(event("search.progress", 99))
        await type_text(pilot, "/r")
        await pilot.press("tab")
        await pilot.pause()
        assert app.size.width == 80
        for widget in app.screen.walk_children():
            if widget.display:
                assert widget.region.right <= 80, widget
        assert app.transcript.max_scroll_x == 0
        assert app.query_one(HomeBox).region.width <= 80
        screenshot = app.export_screenshot()
        assert "Rook" in screenshot


# --- terminal control characters -------------------------------------------------------------------------

INJECT = "\x1b[31m\x1b]0;pwn\x07\x9b"
CONTROLS = ("\x1b", "\x07", "\x9b")


def _paths(value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Paths to every string value, plus ("key", ...) paths for every dict key."""
    if isinstance(value, str):
        return [path]
    if isinstance(value, dict):
        out = [(*path, ("key", k)) for k in value]
        for k, v in value.items():
            out += _paths(v, (*path, k))
        return out
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _paths(v, (*path, i))]
    return []


def _inject(value: Any, path: tuple[Any, ...]) -> Any:
    if not path:
        return value + INJECT
    head, rest = path[0], path[1:]
    if isinstance(head, tuple):  # rename a dict key
        return {(k + INJECT if k == head[1] else k): v for k, v in value.items()}
    if isinstance(value, dict):
        return {k: (_inject(v, rest) if k == head else v) for k, v in value.items()}
    return [(_inject(v, rest) if i == head else v) for i, v in enumerate(value)]


def poisoned(event_type: str) -> dict[str, Any]:
    """The sample with the control sequences appended to every string the contract lets through."""
    data = SAMPLES[event_type]
    for path in _paths(data):
        candidate = _inject(data, path)
        try:
            make_event(1, event_type, candidate)
        except ValueError:  # a Literal or patterned field: the contract already rejects controls there
            continue
        data = candidate
    return data


async def test_control_characters_never_reach_the_terminal() -> None:
    injected = 0
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        for seq, event_type in enumerate(SAMPLES, 1):
            data = poisoned(event_type)
            injected += str(data).count("\\x1b")
            app.show_event(make_event(seq, event_type, data, run_id="r1"))
        app.show_event(make_event(99, "search.progress", poisoned("search.progress"), run_id="r1"))
        app.prompt.value = "typed" + INJECT
        await pilot.press("enter")
        await pilot.pause()
        surfaces = [text(app), app.status_bar.message, app.footer_bar.text, app.export_screenshot()]
        for surface in surfaces:
            for control in CONTROLS:
                assert control not in surface
        assert "shop-app[31m]0;pwn" in app.footer_bar.text  # the text stays, the controls go
        assert "typed[31m]0;pwn" in text(app)
        assert app.status_bar.display
    assert injected > 30  # most free-text fields were really poisoned


async def test_stale_or_duplicate_answers_do_not_clear_the_open_question() -> None:
    app = RookApp(motion=False)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(event("question.asked", 1, question_id="q2"))
        app.show_event(event("question.answered", 2, question_id="q1"))
        assert app.active_question == "q2"
        app.show_event(event("question.answered", 3, question_id="q2"))
        assert app.active_question is None
        app.show_event(event("question.asked", 4, question_id="q3"))
        app.show_event(event("question.answered", 5, question_id="q2"))
        assert app.active_question == "q3"


# --- multi-line fields ------------------------------------------------------------------------------------


def test_clean_multiline_keeps_line_breaks_only() -> None:
    assert clean_multiline("-a\r\n+b\r c\td\ve\ff") == "-a\n+b\n c d e f"
    assert clean_multiline("x" + INJECT + "\ny") == "x[31m]0;pwn\ny"
    assert clean_multiline("a\x00b\x07c\x1bd\x7fe\x80f\x9fg") == "abcdefg"  # NUL, BEL, ESC, DEL, C1
    assert clean_multiline("\r\r\n\n") == "\n\n\n"  # lone \r, then \r\n, then \n
    assert clean_multiline("ü → ✓") == "ü → ✓"  # printable non-ASCII survives
    assert clean("a\nb") == "a b"  # unchanged single-line behaviour


def test_clean_data_keeps_multiline_values_and_flattens_keys() -> None:
    assert clean_data({"diff": "-a\r\n+b\n c"})["diff"] == "-a\n+b\n c"
    assert clean_data({"k\ney": ["x\x1b\ny"]}) == {"k ey": ["x\ny"]}
    assert clean_data({"diff": "-a\n+b"}, multiline=False) == {"diff": "-a +b"}
    nested = clean_data({"files": ["a\r\nb" + INJECT], "n": 3, "ok": None})
    assert nested == {"files": ["a\nb[31m]0;pwn"], "n": 3, "ok": None}


async def test_views_get_multiline_values_but_default_rows_stay_one_line() -> None:
    app = RookApp(motion=False)
    seen: list[str] = []
    app.views["fix.ready"] = lambda ev, transcript: seen.append(ev.data["diff"])
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(event("fix.ready", 1, diff="--- a\r\n+++ b\n-x\x1b\n+y\n"))
        app.show_event(event("diagnosis.ready", 2, explanation="first line\nsecond line"))
        app.show_event(event("log", 3, text="one\r\ntwo"))
        app.show_event(event("run.finished", 4, summary="done\nreally"))
        await pilot.pause()
        assert seen == ["--- a\n+++ b\n-x\n+y\n"]
        body = lines(app)
        assert "  first line second line" in body
        assert "one two" in body
        assert all("\n" not in line for line in body[-4:])
        assert "\n" not in app.footer_bar.text and "done really" in app.footer_bar.text
