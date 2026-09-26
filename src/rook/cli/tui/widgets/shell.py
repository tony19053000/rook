"""The TUI chrome: logo, home box, transcript, status bar, prompt and footer (04_FRONTEND_SPEC.md §2.1)."""

from __future__ import annotations

from typing import ClassVar

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.events import Key
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, Static

from rook.cli.logo import BRAND_COLOR, WORD, logo_lines
from rook.cli.tui.auth import AuthState
from rook.cli.tui.safe_text import clean

SPINNER = "◐◓◑◒"


class Transcript(VerticalScroll):
    """The growing session log. Lines are Statics; 026/027 mount their own rows and cards with `mount_item`."""

    DEFAULT_CSS = """
    Transcript { height: 1fr; padding: 0 1; scrollbar-size-vertical: 1; }
    Transcript > .line { height: auto; }
    """

    def write(self, content: RenderableType) -> Static:
        """Append a line. Plain strings are shown literally (never parsed as markup)."""
        line = Static(Text(clean(content)) if isinstance(content, str) else content, classes="line")
        self.mount_item(line)
        return line

    def mount_item(self, widget: Widget) -> Widget:
        self.mount(widget)
        self.scroll_end(animate=False)
        return widget


class Logo(Static):
    """The ROOK wordmark, revealed letter by letter."""

    DEFAULT_CSS = "Logo { height: 3; color: " + BRAND_COLOR + "; text-style: bold; }"

    def __init__(self, letters: int = 0) -> None:
        super().__init__()
        self.letters = letters
        self._paint()

    def show_letters(self, letters: int) -> None:
        self.letters = min(letters, len(WORD))
        self._paint()

    @property
    def complete(self) -> bool:
        return self.letters >= len(WORD)

    def _paint(self) -> None:
        self.update(Text("\n".join(logo_lines(self.letters))))


def welcome_text(auth: AuthState) -> str:
    who = f"signed in as {clean(auth.user or '')}" if auth.signed_in else "not signed in"
    github = "GitHub connected" if auth.github_connected else "GitHub not connected"
    return f"✻ Rook · {who} · {github}"


class HomeBox(Static):
    DEFAULT_CSS = """
    HomeBox { border: round """ + BRAND_COLOR + """; padding: 0 1; height: auto; width: 100%; margin: 1 0; }
    """

    def __init__(self, auth: AuthState) -> None:
        super().__init__(Text.assemble(welcome_text(auth), "\n", Text("Type /help for commands.", style="dim")))


class StatusBar(Static):
    """`running ◐ Searching 2,140 sequences · 1,140/s`, shown only while the engine searches."""

    DEFAULT_CSS = "StatusBar { height: 1; padding: 0 1; display: none; }"

    def __init__(self, motion: bool = True) -> None:
        super().__init__(id="status")
        self._motion = motion
        self._frame = 0
        self._message = ""
        self._timer: Timer | None = None

    def show_search(self, sequences: int, per_sec: float, detail: str = "") -> None:
        tail = f" · {detail}" if detail else ""
        self._message = clean(f"Searching {sequences:,} sequences · {per_sec:,.0f}/s{tail}")
        self.display = True
        if self._motion and self._timer is None:
            self._timer = self.set_interval(0.25, self._tick)
        self._paint()

    def hide(self) -> None:
        self.display = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @property
    def message(self) -> str:
        return self._message if self.display else ""

    def _tick(self) -> None:
        self._frame += 1
        self._paint()

    def _paint(self) -> None:
        spin = SPINNER[self._frame % len(SPINNER)]
        self.update(Text.assemble(Text("running ", style=BRAND_COLOR), f"{spin} {self._message}"))


class Suggestions(Static):
    """Slash command candidates after a Tab with several matches."""

    DEFAULT_CSS = "Suggestions { height: auto; padding: 0 2; color: $text-muted; display: none; }"

    def show(self, names: tuple[str, ...]) -> None:
        self.update(Text("  ".join(f"/{n}" for n in names)))
        self.display = bool(names)

    def hide(self) -> None:
        self.display = False


class PromptInput(Input):
    """The `> ` input. Enter sends; ↑/↓ browse history; Tab completes; `?` when empty shows shortcuts."""

    DEFAULT_CSS = "PromptInput { border: round $panel-lighten-2; }"
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "history_previous", show=False),
        Binding("down", "history_next", show=False),
        Binding("tab", "complete", show=False),
    ]

    class HistoryMove(Message):
        def __init__(self, older: bool) -> None:
            super().__init__()
            self.older = older

    class CompleteRequested(Message):
        pass

    class ShortcutsRequested(Message):
        pass

    def action_history_previous(self) -> None:
        self.post_message(self.HistoryMove(older=True))

    def action_history_next(self) -> None:
        self.post_message(self.HistoryMove(older=False))

    def action_complete(self) -> None:
        self.post_message(self.CompleteRequested())

    async def _on_key(self, event: Key) -> None:
        if event.character == "?" and not self.value:
            event.stop()
            event.prevent_default()
            self.post_message(self.ShortcutsRequested())


class FooterBar(Horizontal):
    """`? for shortcuts · <repo or none> · 0.00 coins`, with a transient notice on the left."""

    DEFAULT_CSS = """
    FooterBar { height: 1; padding: 0 2; color: $text-muted; }
    FooterBar > #hint { width: auto; }
    FooterBar > #info { width: 1fr; text-align: right; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.repo: str | None = None
        self.coins = 0.0
        self.summary = ""
        self.notice = ""

    def compose(self) -> ComposeResult:
        yield Static(id="hint")
        yield Static(id="info")

    def on_mount(self) -> None:
        self.refresh_text()

    @property
    def hint(self) -> str:
        return clean(self.notice or "? for shortcuts")

    @property
    def info(self) -> str:
        parts = [self.repo or "none", self.summary, f"{self.coins:.2f} coins"]
        return clean(" · ".join(p for p in parts if p))

    @property
    def text(self) -> str:
        return f"{self.hint} · {self.info}"

    def refresh_text(self) -> None:
        self.query_one("#hint", Static).update(Text(self.hint))
        self.query_one("#info", Static).update(Text(self.info))
