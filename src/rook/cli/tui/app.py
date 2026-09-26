"""The interactive `rook` shell (04_FRONTEND_SPEC.md §2): logo, first-run auth, home box, prompt, transcript.

Seams for later tickets:
- ROOK-026/027: replace entries in `RookApp.views` (event type → view) or mount widgets with
  `app.transcript.mount_item(...)`.
- ROOK-024/028: pass a real `Backend`; from a worker thread call `app.call_from_thread(app.show_event, ev)`.
- ROOK-030: pass a real `AuthProvider`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable
from typing import ClassVar, TypeVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Input

from rook import __version__
from rook.cli.logo import TAGLINE, WORD
from rook.cli.tui import commands
from rook.cli.tui.auth import AuthProvider, AuthState, StubAuth
from rook.cli.tui.backend import Backend, OfflineBackend
from rook.cli.tui.history import InputHistory
from rook.cli.tui.render import BAD, DIM, GOOD, EventView, clean_data, default_views
from rook.cli.tui.safe_text import clean
from rook.cli.tui.widgets.shell import (
    SPINNER,
    FooterBar,
    HomeBox,
    Logo,
    PromptInput,
    StatusBar,
    Suggestions,
    Transcript,
)
from rook.core.events import Event

T = TypeVar("T")
PLACEHOLDER = 'Try "find bugs in my app" or /help'
CONFIRM_WINDOW = 2.0  # seconds for the second Ctrl+C / Esc


def motion_enabled() -> bool:
    return os.environ.get("NO_MOTION", "").lower() not in ("1", "true", "yes")


class RookApp(App[None]):
    TITLE = "Rook"
    CSS = "Screen { layout: vertical; }"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+c", "ctrl_c", show=False, priority=True),
        Binding("escape", "escape", show=False),
    ]

    def __init__(
        self,
        backend: Backend | None = None,
        auth: AuthProvider | None = None,
        motion: bool | None = None,
        letter_delay: float = 0.12,
    ) -> None:
        super().__init__()
        self.backend: Backend = backend or OfflineBackend()
        self.auth: AuthProvider = auth or StubAuth()
        self.motion = motion_enabled() if motion is None else motion
        self.letter_delay = letter_delay
        self.history = InputHistory()
        self.views: dict[str, EventView] = default_views()
        self.auto = False
        self.active_question: str | None = None
        self.auth_state = AuthState()
        self.ready = False
        self._armed: str | None = None  # "quit" or "interrupt" while waiting for the confirming key
        self._completion_value: str | None = None

    # -- layout ---------------------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Transcript(id="transcript")
        yield StatusBar(motion=self.motion)
        yield Suggestions(id="suggestions")
        yield PromptInput(placeholder=PLACEHOLDER, id="prompt")
        yield FooterBar()

    @property
    def transcript(self) -> Transcript:
        return self.query_one(Transcript)

    @property
    def prompt(self) -> PromptInput:
        return self.query_one(PromptInput)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    @property
    def footer_bar(self) -> FooterBar:
        return self.query_one(FooterBar)

    @property
    def suggestions(self) -> Suggestions:
        return self.query_one(Suggestions)

    def on_mount(self) -> None:
        self.backend.bind(self)
        self.prompt.focus()
        self.run_worker(self._boot(), exclusive=True, group="boot")

    # -- launch and first run ------------------------------------------------------------------------

    async def _boot(self) -> None:
        logo = Logo(0 if self.motion else len(WORD))
        self.transcript.mount_item(logo)
        if self.motion:
            for letters in range(1, len(WORD) + 1):
                await asyncio.sleep(self.letter_delay)
                logo.show_letters(letters)
        self.transcript.write(Text(f"v{__version__} · {TAGLINE}", style=DIM))
        state = self.auth.state()
        if not state.signed_in:
            state = await self._first_run()
        self.auth_state = state
        self.transcript.mount_item(HomeBox(state))
        self.ready = True

    async def _first_run(self) -> AuthState:
        self.transcript.write("Welcome. Two quick steps and you're ready.")
        self.transcript.write(Text("1/2 Sign in with Google", style="bold"))
        signed_in_as = await self._step("Opening your browser to sign in with Google…", self.auth.sign_in())
        user = clean(signed_in_as) if signed_in_as else None
        self.transcript.write(
            Text(f"  ✓ Signed in as {user} (Google)", style=GOOD)
            if user
            else Text("  · Sign-in isn't available yet. Continuing offline.", style=DIM)
        )
        self.transcript.write(Text("2/2 Connect GitHub", style="bold"))
        repos = None
        if user:
            repos = await self._step("Opening GitHub in your browser. Pick the repos to share…",
                                     self.auth.connect_github())
        self.transcript.write(
            Text(f"  ✓ GitHub connected · {repos} repos shared", style=GOOD)
            if repos is not None
            else Text("  · Skipped. Use /github after signing in.", style=DIM)
        )
        return AuthState(user=user, github_repos=repos)

    async def _step(self, text: str, work: Awaitable[T]) -> T:
        """Await `work` while a spinner line shows `text`; the line is removed afterwards."""
        line = self.transcript.write(f"  {SPINNER[0]} {text}")
        task = asyncio.ensure_future(work)
        frame = 0
        while not task.done():
            await asyncio.wait({task}, timeout=0.11)
            frame += 1
            line.update(Text(f"  {SPINNER[frame % len(SPINNER)]} {text}"))
        await line.remove()
        return task.result()

    # -- events ---------------------------------------------------------------------------------------

    def show_event(self, event: Event) -> None:
        """Apply one event: update the chrome, then let its view draw it in the transcript.

        The payload is cleaned here, once, so no view or chrome ever sees terminal control characters. Values
        keep their line breaks (for multi-line cards); one-line chrome and default rows flatten them.
        """
        data = clean_data(event.data)
        event = event.model_copy(update={"data": data})
        footer = self.footer_bar
        match event.type:
            case "run.created":
                footer.repo, footer.summary = data["repo"]["name"], ""
            case "search.progress":
                self.status_bar.show_search(data["sequences"], data["per_sec"])
            case "engine.finished" if data["worker"] == "runner":
                self.status_bar.hide()
            case "cost.update":
                footer.coins = data["coins_total"]
            case "question.asked":
                self.active_question = data["question_id"]
            case "question.answered" if data["question_id"] == self.active_question:
                self.active_question = None
            case "run.finished":
                self.status_bar.hide()
                self.active_question = None
                footer.summary = data["summary"]
        footer.refresh_text()
        view = self.views.get(event.type)
        if view is not None:
            view(event, self.transcript)

    # -- input ----------------------------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = clean(event.value).strip()
        self.prompt.value = ""
        self.suggestions.hide()
        if not text:
            return
        self.history.add(text)
        parsed = commands.parse(text)
        if parsed is not None:
            self.transcript.write(Text(f"> {text}", style=DIM))
            self._run_command(parsed)
        elif self.active_question is not None:
            question_id, self.active_question = self.active_question, None
            self.backend.answer(question_id, text)
        else:
            self.transcript.write(Text(f"> {text}", style="bold"))
            self.backend.submit(text)

    def _run_command(self, parsed: commands.Parsed) -> None:
        error = commands.validate(parsed)
        if error:
            self.transcript.write(Text(error, style=BAD))
        elif parsed.name == "help":
            self.show_help()
        else:
            if parsed.name == "auto":
                self.auto = parsed.arg == "on"
                self.transcript.write(Text(f"  ✓ Auto-approve {parsed.arg}", style=GOOD))
            self.backend.command(parsed.name, parsed.arg)

    def show_help(self) -> None:
        self.transcript.write(Text("Commands", style="bold"))
        for line in commands.help_lines():
            self.transcript.write(f"  {line}")
        self.transcript.write(Text("Plain text goes to Bob, e.g. \"find bugs in my refund flow\".", style=DIM))
        self.show_shortcuts()

    def show_shortcuts(self) -> None:
        self.transcript.write(Text("Shortcuts", style="bold"))
        for line in commands.shortcut_lines():
            self.transcript.write(f"  {line}")

    def on_prompt_input_shortcuts_requested(self, _: PromptInput.ShortcutsRequested) -> None:
        self.show_shortcuts()

    def on_prompt_input_history_move(self, message: PromptInput.HistoryMove) -> None:
        prompt = self.prompt
        value = self.history.previous(prompt.value) if message.older else self.history.next()
        if value is not None:
            prompt.value = value
            prompt.cursor_position = len(value)

    def on_prompt_input_complete_requested(self, _: PromptInput.CompleteRequested) -> None:
        prompt = self.prompt
        completion = commands.complete(prompt.value)
        self._completion_value = completion.value
        prompt.value = completion.value
        prompt.cursor_position = len(completion.value)
        if len(completion.candidates) > 1:
            self.suggestions.show(completion.candidates)
        else:
            self.suggestions.hide()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.value != self._completion_value:
            self.suggestions.hide()

    # -- keys -----------------------------------------------------------------------------------------

    def _arm(self, kind: str, notice: str) -> None:
        self._armed = kind
        self.footer_bar.notice = notice
        self.footer_bar.refresh_text()
        self.set_timer(CONFIRM_WINDOW, lambda: self._disarm(kind))

    def _disarm(self, kind: str | None = None) -> None:
        if kind is None or self._armed == kind:
            self._armed = None
            self.footer_bar.notice = ""
            self.footer_bar.refresh_text()

    def action_ctrl_c(self) -> None:
        if self._armed == "quit":
            self.exit()
        else:
            self._arm("quit", "Press Ctrl+C again to quit")

    def action_escape(self) -> None:
        if self.suggestions.display:
            self.suggestions.hide()
        elif self.active_question is not None:
            self.active_question = None
            self.transcript.write(Text("  · Question cancelled", style=DIM))
        elif self.backend.running:
            if self._armed == "interrupt":
                self._disarm()
                self.transcript.write(Text("Interrupting the run…", style=DIM))
                self.backend.interrupt()
            else:
                self._arm("interrupt", "Press Esc again to interrupt the run")
        else:
            self.prompt.value = ""


def run_tui(backend: Backend | None = None, auth: AuthProvider | None = None, motion: bool | None = None) -> None:
    """Entry point for the interactive shell (wired to bare `rook` by ROOK-024)."""
    RookApp(backend=backend, auth=auth, motion=motion).run()
