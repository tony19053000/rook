"""ROOK-028: the run in the background, chat to the Guide during it (02_ARCHITECTURE.md §12, 04 §2.3-2.4).

A real Session (scripted Bob, 0 coins; minishop in-process, no Docker) runs in SessionBackend's worker thread.
The search is a fake runner that keeps publishing progress until the test lets it finish, so the checks run
while the engine is busy: a typed question gets the Guide's reply, progress keeps updating, slash commands
still work and Esc twice interrupts the run.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import textual
from session_helpers import LocalLauncher, ScriptedClient, minishop_source
from test_session import FAST, replies
from test_tui_wiring import SIZE, shown, type_in_main_input, until, wired
from textual.pilot import Pilot
from tui_question_samples import booted, fix_question

from rook.cli.tui.app import RookApp
from rook.cli.tui.backend import make_event
from rook.cli.tui.session_backend import SessionBackend
from rook.cli.tui.widgets.prompts import QuestionPrompt, RulesPrompt
from rook.core import session as session_module
from rook.core.events import (
    EngineFinished,
    EngineProgress,
    EngineStarted,
    EventBus,
    SearchProgress,
    clear_secrets,
)
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec
from rook.engine.runner import RunOutcome

GUIDE_REPLY = "Rook is searching the refund flow. Nothing broken yet."
TICK = 0.03


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


class FakeRunner:
    """Stands in for engine.Runner: publishes search/engine progress every TICK until `release` is set
    (then finds nothing) or the run is cancelled."""

    release = threading.Event()
    started = threading.Event()

    def __init__(self, model: Any, executor: Any, bus: EventBus | None, run_id: str, **_: Any) -> None:
        assert bus is not None
        self.bus, self.run_id = bus, run_id
        self.rules = {r.id: "holding" for r in model.rules}

    async def run(self) -> RunOutcome:
        publish = self.bus.publish
        await publish(self.run_id, "engine.started", EngineStarted(worker="runner", label="seed 1"))
        FakeRunner.started.set()
        start, done = time.monotonic(), 0
        try:
            while not FakeRunner.release.is_set():
                await asyncio.sleep(TICK)
                done += 7
                per_sec = round(done / (time.monotonic() - start), 1)
                await publish(self.run_id, "search.progress",
                              SearchProgress(sequences=done, per_sec=per_sec, rules=self.rules))
                await publish(self.run_id, "engine.progress",
                              EngineProgress(worker="runner", pct=50.0, label=f"{done} sequences", count=done))
        except asyncio.CancelledError:
            await publish(self.run_id, "engine.finished",
                          EngineFinished(worker="runner", ok=False, summary="search stopped"))
            raise
        await publish(self.run_id, "engine.finished",
                      EngineFinished(worker="runner", ok=True, summary=f"{done} sequences"))
        return RunOutcome(violation=None, sequences_run=done, elapsed=time.monotonic() - start)


class RealSessions:
    """A SessionFactory building real Sessions with a scripted Bob and in-process minishop."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.launcher = LocalLauncher()
        self.clients: list[ScriptedClient] = []
        self.sessions: list[Session] = []

    def __call__(self, repo: RepoSpec, request: str, options: SessionOptions) -> Session:
        def client(bus: EventBus, run_id: str, ws: Path) -> ScriptedClient:
            self.clients.append(ScriptedClient(bus, run_id, replies(guide=[{"answer": GUIDE_REPLY}])))
            return self.clients[-1]

        session = Session(repo, request, options.model_copy(update=FAST), workspaces_root=self.tmp_path / "ws",
                          client_factory=client, launcher_factory=self.launcher)
        self.sessions.append(session)
        return session


@pytest.fixture
def sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RealSessions:
    FakeRunner.release = threading.Event()
    FakeRunner.started = threading.Event()
    monkeypatch.setattr(session_module, "Runner", FakeRunner)
    return RealSessions(tmp_path)


def searched(app: RookApp) -> int:
    """The sequence count in the status bar (-1 when it is hidden)."""
    match = re.search(r"Searching ([\d,]+) sequences", app.status_bar.message)
    return int(match.group(1).replace(",", "")) if match else -1


async def searching(pilot: Pilot[Any], app: RookApp) -> None:
    await until(pilot, lambda: FakeRunner.started.is_set() and searched(app) > 0, timeout=30.0)


async def test_a_question_during_the_search_gets_a_guide_reply_while_progress_keeps_updating(
        tmp_path: Path, sessions: RealSessions) -> None:
    backend = SessionBackend(repo=str(minishop_source(tmp_path)), factory=sessions,  # type: ignore[arg-type]
                             options=SessionOptions(auto=True))
    app = wired(backend)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await booted(pilot, app)
            await type_in_main_input(pilot, app, "find refund bugs")
            await searching(pilot, app)
            (session,) = sessions.sessions
            assert backend.running and session.request == "find refund bugs"

            before = searched(app)
            await type_in_main_input(pilot, app, "where are we?")
            assert app.prompt.value == "" and app.prompt.has_focus  # the input is free again at once
            await until(pilot, lambda: f"◆ Guide {GUIDE_REPLY}" in shown(app), timeout=10.0)
            at_reply = searched(app)
            assert at_reply > before
            await until(pilot, lambda: searched(app) > at_reply)  # the search did not wait for the Guide
            assert backend.running

            body = shown(app)
            assert body.index("> where are we?") < body.index(f"◆ Guide {GUIDE_REPLY}")
            assert body.count("where are we?") == 1  # the user's chat.message is not echoed twice
            (client,) = sessions.clients
            assert next(p for a, p in client.calls if a == "guide").count("where are we?") == 1
            assert client.total == 0.0 and app.footer_bar.coins == 0.0  # scripted Bob: 0 coins

            FakeRunner.release.set()  # the search ends with nothing found -> the run reports and finishes
            await until(pilot, lambda: not backend.running, timeout=30.0)
            await pilot.pause()
            assert session.result is not None and session.result.status == "done", session.result
            assert "Run done" in shown(app) and app.status_bar.message == ""
    finally:
        FakeRunner.release.set()
        backend.close()


async def test_slash_commands_and_interrupt_during_the_search(tmp_path: Path, sessions: RealSessions) -> None:
    backend = SessionBackend(repo=str(minishop_source(tmp_path)), factory=sessions,  # type: ignore[arg-type]
                             options=SessionOptions(auto=True))
    app = wired(backend)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await booted(pilot, app)
            backend.command("run", "")
            await searching(pilot, app)

            await type_in_main_input(pilot, app, "/help")
            await type_in_main_input(pilot, app, "/run")
            await type_in_main_input(pilot, app, "/auto off")
            body = shown(app)
            assert "Commands" in body and "Shortcuts" in body
            assert "A run is already going. Press Esc twice to interrupt it first." in body
            assert "Auto-approve applies from the next run." in body
            assert len(sessions.sessions) == 1 and not backend.options.auto and not app.auto
            count = searched(app)
            await until(pilot, lambda: searched(app) > count)  # still searching behind the commands

            app.prompt.focus()
            await pilot.press("escape")
            await pilot.pause()
            assert backend.running and "Press Esc again" in app.footer_bar.notice
            await pilot.press("escape")
            await until(pilot, lambda: not backend.running, timeout=30.0)
            await pilot.pause()
            (session,) = sessions.sessions
            assert session.result is not None and session.result.status == "cancelled"
            body = shown(app)
            assert "Interrupting the run…" in body and "Run cancelled" in body
            assert app.status_bar.message == ""
            assert sessions.launcher.apps and all(a.stopped >= 1 for a in sessions.launcher.apps)
            await pilot.press("escape")  # idle again: Esc only clears the input, nothing to interrupt
            assert "Press Esc again" not in app.footer_bar.notice
    finally:
        FakeRunner.release.set()
        backend.close()


@pytest.mark.usefixtures("sessions")
async def test_chat_before_the_guide_is_ready_says_so(tmp_path: Path) -> None:
    gate = threading.Event()

    class Slow(RealSessions):
        def __call__(self, repo: RepoSpec, request: str, options: SessionOptions) -> Session:
            session = super().__call__(repo, request, options)
            original = session._created

            async def created() -> None:  # hold the run in PREPARE until the test has chatted
                await asyncio.to_thread(gate.wait, 10.0)
                await original()

            session._created = created  # type: ignore[method-assign]
            return session

    slow = Slow(tmp_path)
    backend = SessionBackend(repo=str(minishop_source(tmp_path)), factory=slow,  # type: ignore[arg-type]
                             options=SessionOptions(auto=True))
    app = wired(backend)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await booted(pilot, app)
            backend.command("run", "")
            await until(pilot, lambda: backend.running)
            await type_in_main_input(pilot, app, "are you there?")
            assert "The Guide can't answer right now." in shown(app)
            gate.set()
            backend.interrupt()
            await until(pilot, lambda: not backend.running, timeout=30.0)
    finally:
        gate.set()
        backend.close()


# --- regression: events posted from the run thread lacked Textual's active_app (LookupError on render) -------


async def test_events_from_the_run_thread_are_shown_in_the_app_context() -> None:
    backend = SessionBackend()
    app = wired(backend)
    seen: list[Any] = []
    card_view = app.views["question.asked"]

    def view(event: Any, transcript: Any) -> None:
        seen.append(textual.active_app.get(None))
        card_view(event, transcript)

    app.views["question.asked"] = view
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        post = threading.Thread(target=backend._show, args=(make_event(1, "question.asked", fix_question("q1")),))
        post.start()
        post.join()
        await until(pilot, lambda: bool(app.query(QuestionPrompt)))
    assert seen == [app]  # the prompt and card it mounts are Textual widgets of this app


async def test_a_question_arriving_after_quit_is_ignored() -> None:
    backend = SessionBackend()
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
    backend._show(make_event(1, "question.asked", fix_question("q1")))  # the loop is closed or not running
    backend._show_now(make_event(2, "question.asked", fix_question("q2")))
    assert app.active_question is None


@pytest.mark.parametrize("attempt", range(5))  # a timing race: before the fix it failed about 1 time in 8
async def test_quitting_just_after_a_second_run_asked_its_question(tmp_path: Path, sessions: RealSessions,
                                                                   attempt: int) -> None:
    backend = SessionBackend(repo=str(minishop_source(tmp_path)), factory=sessions,  # type: ignore[arg-type]
                             options=SessionOptions(auto=True))
    app = wired(backend)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await booted(pilot, app)
            backend.command("run", "")
            await searching(pilot, app)
            backend.command("auto", "off")
            backend.interrupt()
            await until(pilot, lambda: not backend.running, timeout=30.0)
            await type_in_main_input(pilot, app, "hello?")  # a second run, which stops at approve_rules
            await until(pilot, lambda: bool(app.query(RulesPrompt)), timeout=30.0)
            backend.interrupt()
            await until(pilot, lambda: not backend.running, timeout=30.0)
    finally:
        FakeRunner.release.set()
        backend.close()
    assert [s.result.status for s in sessions.sessions if s.result] == ["cancelled", "cancelled"]
