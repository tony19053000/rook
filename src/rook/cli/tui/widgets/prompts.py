"""Inline question prompts (04_FRONTEND_SPEC.md §2.2) for `question.asked` / `question.answered`.

- MenuPrompt (menu, repo, and any question with options): `❯` on the selection, ↑/↓ (or 1-9) and Enter.
- ConfirmPrompt (fix, pr): `? Fix cx_001 in src/refunds.js:42? (Y/n)`.
- ValuePrompt (setup_value, or a question with no options): a text input, masked unless the payload says
  `secret: false`. The value goes only to the backend; it is never drawn, echoed or kept in the widget.
- RulesPrompt (approve_rules): drives the RulesCard above it. Accepted rules are pre-selected except one
  flagged `already_broken`, which needs an explicit toggle (admin rule B); space or 1-9 toggles, Y/Enter
  approves the selection, n rejects all.

A prompt takes the focus while open, answers through `app.backend.answer` (the 025 seam), then collapses to
`✓ <choice>` and gives the focus back to the input. Esc cancels it. A `question.answered` event (an auto
answer, or an answer from the web) collapses it too, marked `(auto)` when `by` is auto.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Protocol, cast

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import Input, Static

from rook.cli.tui.render import EventView
from rook.cli.tui.safe_text import clean, clean_multiline
from rook.cli.tui.widgets import cards
from rook.cli.tui.widgets.cards import ACCENT, DIM, GOOD, WARN, RulesCard, compact, latest
from rook.cli.tui.widgets.shell import Transcript
from rook.core.events import Event, QuestionOption

State = Literal["open", "answered", "cancelled"]


class _Answering(Protocol):
    # The Session accepts "all" | "none" | [rule ids] for approve_rules (core/session.valid_answer); the
    # 025 `Backend.answer` is annotated `answer: str`, so ROOK-024 must widen it to `Any` for lists.
    def answer(self, question_id: str, answer: Any) -> None: ...


class Host(Protocol):
    """What a prompt needs from RookApp."""

    backend: _Answering
    active_question: str | None

    @property
    def prompt(self) -> Input: ...


def question_text(data: dict[str, Any]) -> str:
    return clean(clean_multiline(str(data.get("text", ""))).strip())


def parse_options(data: dict[str, Any]) -> list[QuestionOption]:
    raw = data.get("options")
    options = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and "id" in item:
            options.append(QuestionOption(id=clean(str(item["id"])), label=clean(str(item.get("label") or item["id"]))))
    return options


def describe_answer(answer: Any, options: list[QuestionOption]) -> str:
    """How an answer reads once collapsed: the option label, `Approve r1, r2`, `NAME provided`…"""
    labels = {o.id: o.label for o in options}
    if isinstance(answer, bool):
        return "Yes" if answer else "No"
    if isinstance(answer, str):
        return clean(labels.get(answer, answer))
    if isinstance(answer, list):
        return f"Approve {', '.join(clean(str(i)) for i in answer)}" if answer else "Reject all"
    if isinstance(answer, dict) and "name" in answer:
        name = clean(str(answer["name"]))
        return f"{name} provided" if answer.get("provided") else f"{name} not provided"
    return compact(answer)


class QuestionPrompt(Widget, can_focus=True):
    """The shared lifecycle: open (focused) → answered or cancelled (one collapsed line)."""

    DEFAULT_CSS = """
    QuestionPrompt { height: auto; width: 100%; }
    QuestionPrompt:focus { background: $boost; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", show=False)]

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.question_id = clean(str(data.get("question_id", "")))
        self.kind = clean(str(data.get("kind", "")))
        self.text = question_text(data)
        self.options = parse_options(data)
        self.state: State = "open"
        self.result = ""
        self.by = "user"

    @property
    def host(self) -> Host:
        return cast(Host, self.app)

    def on_mount(self) -> None:
        self.focus_prompt()

    def focus_prompt(self) -> None:
        self.focus()

    def submit(self, answer: Any, shown: str | None = None) -> None:
        """Send the user's answer and collapse. Only an open prompt can answer (never twice)."""
        if self.state != "open":
            return
        host = self.host
        if host.active_question == self.question_id:
            host.active_question = None
        host.backend.answer(self.question_id, answer)
        self._close("answered", shown if shown is not None else describe_answer(answer, self.options), "user")

    def resolve(self, answer: Any, by: str) -> None:
        """question.answered from the run: collapse if this prompt is still open."""
        if self.state == "open":
            self._close("answered", describe_answer(answer, self.options), by)

    def action_cancel(self) -> None:
        if self.state != "open":
            return
        host = self.host
        if host.active_question == self.question_id:
            host.active_question = None
        self._close("cancelled", "", "user")

    def _close(self, state: State, result: str, by: str) -> None:
        had_focus = self.has_focus_within
        self.state, self.result, self.by = state, result, by
        self.on_closed()
        self.refresh(layout=True)
        if had_focus:
            self.host.prompt.focus()

    def on_closed(self) -> None:
        """Hook for prompts with children to tidy up."""

    def question_line(self, hint: str = "") -> Text:
        line = Text.assemble(Text("? ", style=f"bold {WARN}"), Text(self.text, style="bold"))
        if hint:
            line.append(f" {hint}", style=DIM)
        return line

    def closed_line(self) -> Text:
        if self.state == "cancelled":
            return Text("  · Question cancelled", style=DIM)
        line = Text.assemble("  ", Text("✓ ", style=GOOD), Text(self.result, style=GOOD))
        if self.by == "auto":
            line.append(" (auto)", style=DIM)
        return line

    def open_lines(self) -> list[Text]:
        return [self.question_line()]

    def lines(self) -> list[Text]:
        if self.state == "open":
            return self.open_lines()
        return [self.question_line(), self.closed_line()]

    def render(self) -> RenderableType:
        return Text("\n").join(self.lines())

    @property
    def plain(self) -> str:
        return "\n".join(line.plain for line in self.lines())


class MenuPrompt(QuestionPrompt):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("enter", "choose", show=False),
        *[Binding(str(n), f"pick({n})", show=False) for n in range(1, 10)],
    ]

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        self.cursor = 0

    def action_move(self, delta: int) -> None:
        if self.options and self.state == "open":
            self.cursor = (self.cursor + delta) % len(self.options)
            self.refresh()

    def action_pick(self, number: int) -> None:
        if 1 <= number <= len(self.options):
            self.cursor = number - 1
            self.action_choose()

    def action_choose(self) -> None:
        if self.options:
            self.submit(self.options[self.cursor].id)

    def open_lines(self) -> list[Text]:
        out = [self.question_line("(↑/↓ and Enter)")]
        for i, option in enumerate(self.options):
            if i == self.cursor:
                out.append(Text.assemble("  ", Text(f"❯ {option.label}", style=f"bold {ACCENT}")))
            else:
                out.append(Text(f"    {option.label}"))
        return out


class ConfirmPrompt(QuestionPrompt):
    """Y/Enter answers the first option (yes), n the second (no)."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y,Y,enter", "confirm(True)", show=False),
        Binding("n,N", "confirm(False)", show=False),
    ]

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        yes = self.options[0] if self.options else QuestionOption(id="yes", label="Yes")
        no = self.options[1] if len(self.options) > 1 else QuestionOption(id="no", label="No")
        self.choices = (yes, no)
        self.options = list(self.choices)

    def action_confirm(self, yes: bool) -> None:
        self.submit(self.choices[0].id if yes else self.choices[1].id)

    def open_lines(self) -> list[Text]:
        yes, no = self.choices
        return [self.question_line(f"(Y = {yes.label} / n = {no.label})")]


class ValuePrompt(QuestionPrompt):
    """A typed value; masked when the payload marks it secret (the default for setup values)."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(data)
        payload = data.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        self.name_asked = clean(str(payload.get("name", "")))
        self.secret = payload.get("secret") is not False

    DEFAULT_CSS = """
    ValuePrompt { height: auto; }
    ValuePrompt > .question { height: auto; }
    ValuePrompt > Input { margin: 0 2; }
    """

    def compose(self) -> ComposeResult:
        yield Static(self.question_line("(Enter to send, Esc to cancel)"), classes="question")
        yield Input(password=self.secret, placeholder="hidden value" if self.secret else "value")

    def focus_prompt(self) -> None:
        self.query_one(Input).focus()

    def render(self) -> RenderableType:
        return Text()  # the children draw the prompt

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()  # keep the value away from RookApp's own input handlers

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()  # otherwise RookApp would echo it to the transcript or send it a second time
        value = event.value
        event.input.value = ""
        if not value.strip():
            self.app.bell()
            return
        shown = f"{self.name_asked or 'Value'} provided" if self.secret else clean(value)
        self.submit(value, shown)

    def on_closed(self) -> None:
        for box in self.query(Input):
            box.value = ""
            box.remove()
        self.query_one(".question", Static).update(Text("\n").join(self.lines()))


class RulesPrompt(QuestionPrompt):
    """`? Approve these 3 rules? (Y / n · space toggles)` under the RulesCard it drives."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("space", "tick", show=False),
        Binding("y,Y,enter", "approve", show=False),
        Binding("n,N", "reject", show=False),
        *[Binding(str(n), f"tick({n})", show=False) for n in range(1, 10)],
    ]

    def __init__(self, data: dict[str, Any], card: RulesCard) -> None:
        super().__init__(data)
        self.card = card

    def action_move(self, delta: int) -> None:
        if self.state == "open":
            self.card.move(delta)

    def action_tick(self, number: int | None = None) -> None:
        if self.state == "open":
            self.card.toggle(number)
            self.refresh(layout=True)

    def action_approve(self) -> None:
        ids = self.card.selected_ids
        # Always the explicit list: "all" would also approve a flagged rule the user left unticked.
        self.submit(ids if ids else "none", f"Approved {len(ids)} rules" if ids else "Rejected all rules")

    def action_reject(self) -> None:
        self.submit("none", "Rejected all rules")

    def submit(self, answer: Any, shown: str | None = None) -> None:
        if self.state == "open":
            self.card.decide(answer)
        super().submit(answer, shown)

    def resolve(self, answer: Any, by: str) -> None:
        if self.state == "open":
            self.card.decide(answer)
        super().resolve(answer, by)

    def action_cancel(self) -> None:
        if self.state == "open":
            self.card.asking = False
            self.card.redraw()
        super().action_cancel()

    def open_lines(self) -> list[Text]:
        count = len(self.card.selected_ids)
        ask = f"Approve these {count} rules?" if count else "Approve no rules (reject all)?"
        line = Text.assemble(Text("? ", style=f"bold {WARN}"), Text(ask, style="bold"),
                             Text(" (Y / n · ↑/↓ and space to choose)", style=DIM))
        return [line]

    def lines(self) -> list[Text]:
        if self.state == "open":
            return self.open_lines()
        return [self.closed_line()]


# --- views ---------------------------------------------------------------------------------------------------


def make_prompt(data: dict[str, Any], transcript: Transcript) -> QuestionPrompt:
    kind = data.get("kind")
    payload = data.get("payload")
    rules = payload.get("rules") if isinstance(payload, dict) else None
    if kind == "approve_rules" and isinstance(rules, list) and rules:
        card = latest(transcript, RulesCard, lambda c: not c.asking and all(r.approved is None for r in c.rows))
        if card is None:
            card = RulesCard()
            transcript.mount_item(card)
        card.ask(rules)
        return RulesPrompt(data, card)
    options = parse_options(data)
    if kind in ("fix", "pr", "approve_rules") and options and len(options) <= 2:
        return ConfirmPrompt(data)
    if options:
        return MenuPrompt(data)
    return ValuePrompt(data)


def show_question(event: Event, transcript: Transcript) -> None:
    transcript.mount_item(make_prompt(event.data, transcript))


def show_answer(event: Event, transcript: Transcript) -> None:
    question_id = clean(str(event.data.get("question_id", "")))
    by = clean(str(event.data.get("by", "user")))
    prompt = latest(transcript, QuestionPrompt, lambda p: p.question_id == question_id)
    if prompt is not None:
        prompt.resolve(event.data.get("answer"), by)
        return
    line = Text.assemble("  ", Text("✓ ", style=GOOD), Text(describe_answer(event.data.get("answer"), []),
                                                            style=GOOD))
    if by == "auto":
        line.append(" (auto)", style=DIM)
    transcript.write(line)


def prompt_views() -> dict[str, EventView]:
    return {"question.asked": show_question, "question.answered": show_answer}


def register(app: cards.HasViews) -> None:
    """Install the cards and the prompts into RookApp.views (the 025 seam). Call once, before events flow."""
    cards.register(app)
    app.views.update(prompt_views())
