"""Connects the widgets of ROOK-026/027 to RookApp (the `views` seam) and maps typed text to an open prompt.

- `register_views(app)`: live AgentRow/EngineRow rows for agent.* / engine.* (04 §4), then the cards and the
  question prompts. Called once by `build_app`, before any event flows.
- `answer_from_input(prompt, text)`: when a question prompt is open and the user types in the main input
  instead, the text is mapped to one of the prompt's own choices (never sent raw). A setup value is never
  taken from the main input, which is not masked.
"""

from __future__ import annotations

from typing import Protocol

from rook.cli.tui.render import EventView
from rook.cli.tui.widgets import prompts
from rook.cli.tui.widgets.prompts import ConfirmPrompt, MenuPrompt, QuestionPrompt, RulesPrompt
from rook.cli.tui.widgets.rows import LiveRows
from rook.cli.tui.widgets.shell import Transcript
from rook.core.events import Event

YES = frozenset({"y", "yes", "ok", "approve", "all"})
NO = frozenset({"n", "no", "none", "reject"})
ROW_EVENTS = ("agent.started", "agent.progress", "agent.finished",
              "engine.started", "engine.progress", "engine.finished")


class HasViews(Protocol):
    views: dict[str, EventView]
    motion: bool


def rows_view(live: LiveRows) -> EventView:
    def view(event: Event, transcript: Transcript) -> None:
        row = live.handle(event)
        if row is not None:
            transcript.mount_item(row)

    return view


def register_views(app: HasViews) -> LiveRows:
    live = LiveRows(reduced_motion=not app.motion)
    view = rows_view(live)
    app.views.update({event_type: view for event_type in ROW_EVENTS})
    prompts.register(app)
    return live


def answer_from_input(prompt: QuestionPrompt, text: str) -> bool:
    """Answer `prompt` from text typed in the main input; False if the text is not one of its choices."""
    word = text.strip().lower()
    if isinstance(prompt, RulesPrompt):
        if word in YES:
            prompt.action_approve()
        elif word in NO:
            prompt.action_reject()
        else:
            return False
        return True
    if isinstance(prompt, ConfirmPrompt):
        yes, no = prompt.choices
        if word in YES or word in (yes.id.lower(), yes.label.lower()):
            prompt.action_confirm(True)
        elif word in NO or word in (no.id.lower(), no.label.lower()):
            prompt.action_confirm(False)
        else:
            return False
        return True
    if isinstance(prompt, MenuPrompt):
        for i, option in enumerate(prompt.options):
            if word in (str(i + 1), option.id.lower(), option.label.lower()):
                prompt.cursor = i
                prompt.action_choose()
                return True
    return False  # a ValuePrompt, or text that is none of the choices


def hint(prompt: QuestionPrompt) -> str:
    if isinstance(prompt, RulesPrompt):
        return "Answer the rules question above: y to approve the ticked rules, n to reject all."
    if isinstance(prompt, ConfirmPrompt):
        return "Answer the question above: y or n."
    if isinstance(prompt, MenuPrompt):
        return f"Pick 1-{len(prompt.options)} in the question above (↑/↓ and Enter)."
    return "Type the value in the question's own (hidden) box above."
