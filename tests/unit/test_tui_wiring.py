"""ROOK-024: the TUI wired to a run. `build_app` registers the live rows, cards and prompts; text typed in the
main input while a question is open goes to that question's own choices; `SessionBackend` runs a Session in a
worker thread (events → show_event, answers → Session.answer, chat, cancel)."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from textual.pilot import Pilot
from tui_question_samples import (
    FakeBackend,
    approve_rules_question,
    booted,
    fix_question,
    menu_question,
    setup_question,
)

from rook.cli.tui.app import RookApp, build_app
from rook.cli.tui.auth import AuthState, StubAuth
from rook.cli.tui.backend import make_event
from rook.cli.tui.session_backend import SessionBackend
from rook.cli.tui.widgets.prompts import ConfirmPrompt, MenuPrompt, QuestionPrompt, RulesPrompt, ValuePrompt
from rook.cli.tui.widgets.rows import AgentRow, EngineRow
from rook.core.events import EventBus
from rook.core.session import SessionOptions
from rook.core.workspace import RepoSpec

SIZE = (80, 40)
SIGNED_IN = StubAuth(AuthState(user="aayush", github_repos=1))


def wired(backend: Any = None) -> RookApp:
    return build_app(backend=backend or FakeBackend(), auth=SIGNED_IN, motion=False)


def shown(app: RookApp) -> str:
    out = []
    for widget in app.transcript.children:
        plain = getattr(widget, "plain", None)
        out.append(plain if isinstance(plain, str) else str(widget.render()))
    return "\n".join(out)


async def type_in_main_input(pilot: Pilot[Any], app: RookApp, text: str) -> None:
    app.prompt.focus()
    await pilot.pause()
    app.prompt.value = text
    await pilot.press("enter")
    await pilot.pause()


class Seq:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, event_type: str, data: dict[str, Any]) -> Any:
        self.n += 1
        return make_event(self.n, event_type, data, run_id="r1")


# --- build_app ----------------------------------------------------------------------------------------------


async def test_build_app_registers_rows_cards_and_prompts() -> None:
    app = wired()
    assert app.views["question.asked"].__module__ == "rook.cli.tui.widgets.prompts"
    assert app.views["counterexample.saved"].__module__ == "rook.cli.tui.widgets.cards"
    assert app.views["agent.started"].__module__ == "rook.cli.tui.wiring"
    ev = Seq()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(ev("agent.started", {"agent": "scout", "call_id": "c1", "detail": "reading the repo"}))
        app.show_event(ev("engine.started", {"worker": "runner", "label": "seed 1"}))
        await pilot.pause()
        agent, engine = app.query_one(AgentRow), app.query_one(EngineRow)
        app.show_event(ev("agent.finished", {"agent": "scout", "call_id": "c1", "ok": True, "summary": "python app",
                                             "cost": 0.0, "recorded": True}))
        app.show_event(ev("engine.finished", {"worker": "runner", "ok": False, "summary": "rule broken"}))
        await pilot.pause()
        assert agent.state == "done" and engine.state == "done"
        assert len(app.query(AgentRow)) == 1  # the row collapses in place, no second line


async def test_rules_prompt_sends_a_list_answer() -> None:
    backend = FakeBackend()
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(Seq()("question.asked", approve_rules_question("q1")))
        await pilot.pause()
        assert isinstance(app.focused, RulesPrompt)
        await pilot.press("y")
        await pilot.pause()
        # The flagged rule (total_positive, already_broken) is not ticked unless the user ticks it.
        assert backend.calls == [("answer", "q1", ["refund_le_paid"])]
        assert app.active_question is None and app.focused is app.prompt


# --- typed input while a prompt is open ---------------------------------------------------------------------


async def test_typed_yes_answers_the_open_confirm_prompt() -> None:
    backend = FakeBackend()
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(Seq()("question.asked", fix_question("q1")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "maybe later")
        assert backend.calls == []  # not a choice: never sent raw
        assert "Answer the question above: y or n." in shown(app)
        assert isinstance(app.focused, ConfirmPrompt)  # the focus goes back to the question
        await type_in_main_input(pilot, app, "Yes")
        assert backend.calls == [("answer", "q1", "yes")]
        assert app.query_one(ConfirmPrompt).state == "answered"


async def test_typed_text_picks_a_menu_option_by_number_or_label() -> None:
    backend = FakeBackend()
    app = wired(backend)
    ev = Seq()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(ev("question.asked", menu_question("q1")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "2")
        app.show_event(ev("question.asked", menu_question("q2")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "stop")
        assert backend.calls == [("answer", "q1", "report"), ("answer", "q2", "stop")]
        assert all(p.state == "answered" for p in app.query(MenuPrompt))


async def test_typed_rules_answers_approve_the_selection_or_reject() -> None:
    backend = FakeBackend()
    app = wired(backend)
    ev = Seq()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(ev("question.asked", approve_rules_question("q1")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "all")
        app.show_event(ev("question.asked", approve_rules_question("q2")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "no")
        # "all" approves the ticked rules as an explicit list: never the flagged one.
        assert backend.calls == [("answer", "q1", ["refund_le_paid"]), ("answer", "q2", "none")]


async def test_a_setup_value_is_never_taken_from_the_main_input() -> None:
    backend = FakeBackend()
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(Seq()("question.asked", setup_question("q1")))
        await pilot.pause()
        await type_in_main_input(pilot, app, "sk-typed-in-the-open")
        assert backend.calls == []
        assert "sk-typed-in-the-open" not in shown(app)
        prompt = app.query_one(ValuePrompt)
        assert prompt.state == "open" and app.focused is not app.prompt  # back in the masked box


async def test_escape_in_the_main_input_cancels_the_open_prompt_and_enter_focuses_it() -> None:
    backend = FakeBackend()
    app = wired(backend)
    ev = Seq()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(ev("question.asked", fix_question("q1")))
        await pilot.pause()
        app.prompt.focus()
        await pilot.press("enter")  # empty input: Enter goes to the question
        await pilot.pause()
        assert isinstance(app.focused, ConfirmPrompt)
        app.prompt.focus()
        await pilot.press("escape")
        await pilot.pause()
        assert app.query_one(ConfirmPrompt).state == "cancelled" and app.active_question is None
        assert backend.calls == []


# --- SessionBackend with a fake Session -----------------------------------------------------------------------


class FakeSession:
    """The Session API the backend uses: one approve_rules question, then the run ends."""

    def __init__(self, repo: RepoSpec, request: str, options: SessionOptions, accept: bool = True) -> None:
        self.repo, self.request, self.options = repo, request, options
        self.run_id = "r1"
        self.bus = EventBus()
        self.accept = accept
        self.answers: list[tuple[str, Any]] = []
        self.chats: list[str] = []
        self.cancelled = False
        self.thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._answer: asyncio.Future[Any] | None = None

    def events(self, after: int = 0) -> Any:
        return self.bus.subscribe(self.run_id, after=after)

    def answer(self, question_id: str, answer: Any) -> bool:
        self.answers.append((question_id, answer))
        if not self.accept or self._loop is None or self._answer is None:
            return False
        fut = self._answer
        self._loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(answer))
        return True

    def chat(self, text: str) -> bool:
        self.chats.append(text)
        return True

    def cancel(self) -> None:
        self.cancelled = True
        if self._loop is not None and self._answer is not None:
            fut = self._answer
            self._loop.call_soon_threadsafe(fut.cancel)

    async def run(self) -> None:
        self.thread = threading.current_thread()
        self._loop = asyncio.get_running_loop()
        self._answer = self._loop.create_future()
        publish = self.bus.publish
        await publish(self.run_id, "run.created", {"repo": {"kind": "local", "ref": "/x", "name": "shop"},
                                                   "request": self.request, "options": {"auto": False, "budget": 1.5}})
        await publish(self.run_id, "question.asked", approve_rules_question("q1"))
        try:
            answer = await self._answer
            await publish(self.run_id, "question.answered", {"question_id": "q1", "answer": answer, "by": "user"})
            status = "done"
        except asyncio.CancelledError:
            status = "cancelled"
        await publish(self.run_id, "run.finished", {"status": status, "summary": f"run {status}"})
        await self.bus.close(self.run_id)


class Factory:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.sessions: list[FakeSession] = []

    def __call__(self, repo: RepoSpec, request: str, options: SessionOptions) -> FakeSession:
        self.sessions.append(FakeSession(repo, request, options, self.accept))
        return self.sessions[-1]


async def until(pilot: Pilot[Any], check: Any, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.02)):
        if check():
            return
        await pilot.pause(0.02)
    raise AssertionError("timed out")


async def test_session_backend_runs_in_a_thread_and_takes_a_list_answer(tmp_path: Path) -> None:
    factory = Factory()
    backend = SessionBackend(repo=str(tmp_path), factory=factory)  # type: ignore[arg-type]
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await type_in_main_input(pilot, app, "find refund bugs")
        await until(pilot, lambda: bool(app.query(RulesPrompt)))
        (session,) = factory.sessions
        assert session.request == "find refund bugs" and session.repo.ref == str(tmp_path.resolve())
        assert session.thread is not threading.current_thread() and backend.running
        assert app.footer_bar.repo == "shop"  # run.created reached the app through call_from_thread
        await type_in_main_input(pilot, app, "how is it going?")  # a question is open: not a choice
        assert session.chats == [] and session.answers == []
        app.query_one(RulesPrompt).focus()
        await pilot.press("y")
        await until(pilot, lambda: not backend.running)
        await pilot.pause()
        assert session.answers == [("q1", ["refund_le_paid"])]
        assert "Run done · run done" in shown(app)
    backend.close()


async def test_session_backend_chat_interrupt_and_refused_answers(tmp_path: Path) -> None:
    factory = Factory(accept=False)
    backend = SessionBackend(repo=str(tmp_path), factory=factory)  # type: ignore[arg-type]
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        backend.command("run", "")
        await until(pilot, lambda: bool(app.query(RulesPrompt)))
        (session,) = factory.sessions
        backend.submit("what are you doing?")  # during a run: to the Guide
        assert session.chats == ["what are you doing?"]
        backend.command("run", "")
        backend.command("auto", "on")
        await pilot.pause()
        assert len(factory.sessions) == 1 and backend.options.auto
        assert "A run is already going" in shown(app) and "Auto-approve applies from the next run." in shown(app)
        app.query_one(RulesPrompt).focus()
        await pilot.press("n")
        await pilot.pause()
        assert session.answers == [("q1", "none")]
        assert "That answer wasn't accepted" in shown(app)
        app.prompt.focus()
        await pilot.press("escape")
        await pilot.press("escape")
        await until(pilot, lambda: not backend.running)
        assert session.cancelled
        await pilot.pause()
        assert "Run cancelled" in shown(app)
    backend.close()


async def test_session_backend_starts_the_given_run_once_the_app_is_ready(tmp_path: Path) -> None:
    factory = Factory()
    backend = SessionBackend(repo=str(tmp_path), factory=factory, start_request="check refunds",  # type: ignore[arg-type]
                             options=SessionOptions(auto=True, seed=3))
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await until(pilot, lambda: bool(factory.sessions))
        assert app.ready
        (session,) = factory.sessions
        assert session.request == "check refunds" and session.options.auto and session.options.seed == 3
        await until(pilot, lambda: bool(app.query(QuestionPrompt)))
    backend.close()
    assert session.cancelled and not backend.running  # quitting the shell stops the run


async def test_session_backend_reports_a_bad_repo(tmp_path: Path) -> None:
    factory = Factory()
    backend = SessionBackend(repo=str(tmp_path / "missing"), factory=factory)  # type: ignore[arg-type]
    app = wired(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        backend.submit("find bugs")
        backend.answer("q1", "yes")
        await pilot.pause()
        assert factory.sessions == [] and not backend.running
        body = shown(app)
        assert "is not a folder or a GitHub repo" in body and "There is no run to answer." in body
