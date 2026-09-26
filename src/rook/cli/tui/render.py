"""Default event → transcript views (04_FRONTEND_SPEC.md §4), one plain line (or a few) per event.

These are placeholders with the right copy. ROOK-026 replaces the `agent.*` / `engine.*` views with live
rows, ROOK-027 replaces questions and cards, by assigning into `RookApp.views`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rich.text import Text

from rook.agents.registry import AGENTS
from rook.cli.tui.safe_text import clean, clean_multiline
from rook.cli.tui.widgets.shell import Transcript
from rook.core.events import EVENT_TYPES, Event

EventView = Callable[[Event, Transcript], None]

GOOD, BAD, WARN, DIM = "#62D69B", "#FF7A70", "#E9C46A", "dim"


def clean_data(value: Any, multiline: bool = True) -> Any:
    """Every string in an event payload with terminal control characters removed.

    Values keep their line breaks when `multiline` (a diff or an explanation stays multi-line for the cards);
    dict keys are always flattened to one line.
    """
    if isinstance(value, str):
        return clean_multiline(value) if multiline else clean(value)
    if isinstance(value, dict):
        return {clean(k) if isinstance(k, str) else k: clean_data(v, multiline) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean_data(v, multiline) for v in value]
    return value


def agent_name(agent: str) -> str:
    spec = AGENTS.get(agent)
    return spec.name if spec else agent.replace("_", " ").title()


def _mark(ok: bool) -> Text:
    return Text("✓", style=GOOD) if ok else Text("✗", style=BAD)


def _line(*parts: str | Text) -> Text:
    return Text.assemble(*parts)


def _text_of(item: Any, key: str = "text") -> str:
    if isinstance(item, dict):
        return str(item.get(key) or item.get("id") or item)
    return str(item)


def _lines(event: Event) -> list[Text]:
    d = event.data
    match event.type:
        case "run.created":
            return [Text(f"Run started · {d['repo']['name']}", style=DIM)]
        case "agent.started":
            return [_line(Text("◆ ", style=WARN), Text(agent_name(d["agent"]), style="bold"), f"  {d['detail']}")]
        case "agent.progress":
            return [Text(f"  ⎿ {d['detail']}", style=DIM)]
        case "agent.finished":
            return [_line("● ", Text(agent_name(d["agent"]), style="bold"), " ", _mark(d["ok"]), f" {d['summary']}")]
        case "engine.started":
            return [Text(f"■ {d['worker'].title()}  {d['label']}")]
        case "engine.finished":
            return [_line(f"■ {d['worker'].title()} ", _mark(d["ok"]), f" {d['summary']}")]
        case "question.asked":
            options = [Text(f"    {i}. {o['label']}") for i, o in enumerate(d["options"], 1)]
            return [_line(Text("? ", style=WARN), d["text"]), *options]
        case "question.answered":
            return [_line("  ", _mark(True), Text(f" {d['answer']}", style=GOOD))]
        case "repo.summary":
            return [Text(f"◆ {d['language']} · {d['framework']} · {d['business_summary']}")]
        case "sandbox.ready":
            return [_line("  ", _mark(True), f" App running ({d['mode']})")]
        case "model.actions":
            names = "  ".join(_text_of(action, "name") for action in d["actions"])
            return [Text(f"◆ Found {len(d['actions'])} actions: {names}")]
        case "rules.proposed":
            return [Text("◆ These rules should always be true:")] + [
                Text(f"  {i}  {_text_of(rule)}") for i, rule in enumerate(d["rules"], 1)
            ]
        case "rules.approved":
            return [_line("  ", _mark(True), f" {len(d['rule_ids'])} rules approved")]
        case "violation.found":
            return [_line(_mark(False), f" Rule {d['rule_id']} broken in {d['steps_count']} steps")]
        case "shrink.step":
            return [Text(f"  Shrinking → {d['steps_count']} steps", style=DIM)]
        case "counterexample.saved":
            steps = [Text(f"  {i}. {_text_of(step)}") for i, step in enumerate(d["steps"], 1)]
            return [
                Text(f"COUNTEREXAMPLE {d['cx_id']}", style=f"bold {BAD}"),
                Text(f"  {d['rule_text']}"),
                *steps,
                _line(f"  Replayed {d['reproduced']} on the real app ", _mark(not d["flaky"])),
            ]
        case "diagnosis.ready":
            where = f"{d['file']} : {d['line']}" if d["line"] is not None else d["file"]
            return [Text(f"Root cause {where}", style="bold"), Text(f"  {d['explanation']}")]
        case "fix.ready":
            return [Text(f"◆ Fix ready · {', '.join(d['files'])}")]
        case "verify.step":
            mark = {"running": Text("◐"), "passed": _mark(True), "failed": _mark(False)}[d["status"]]
            return [_line("  ", mark, f" {d['check'].replace('_', ' ').capitalize()}: {d['detail']}")]
        case "verify.done":
            if d["verified"]:
                return [Text("✓ FIX VERIFIED", style=f"bold {GOOD}")]
            return [_line(_mark(False), f" Fix not verified · {d['summary']}")]
        case "pr.opened":
            return [_line(_mark(True), f" PR #{d['number']} opened · {d['url']}")]
        case "chat.message" if d["role"] == "guide":
            return [_line(Text("◆ Guide ", style="bold"), d["text"])]
        case "log":
            style = {"info": DIM, "warn": WARN, "error": BAD}[d["level"]]
            return [Text(d["text"], style=style)]
        case "run.finished":
            return [_line(_mark(d["status"] == "done"), f" Run {d['status']} · {d['summary']}")]
    # run.phase, engine.progress, search.progress and cost.update drive the status bar and footer instead;
    # the user's own chat.message is echoed by the prompt.
    return []


def default_view(event: Event, transcript: Transcript) -> None:
    # Each default row is one line, so every field is flattened here (this also keeps the view safe when it
    # is called outside `show_event`).
    for line in _lines(event.model_copy(update={"data": clean_data(event.data, multiline=False)})):
        transcript.write(line)


def default_views() -> dict[str, EventView]:
    return {event_type: default_view for event_type in EVENT_TYPES}
