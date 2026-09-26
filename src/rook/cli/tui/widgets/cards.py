"""Inline result cards for the transcript (04_FRONTEND_SPEC.md §2.2 and §4).

- RulesCard: the proposed rules with their sources, then the engine/critic verdicts (rejected rules struck
  through with the reason; `already_broken` rules marked "possibly already broken"). While the approve_rules
  question is open it also holds the selection (prompts.RulesPrompt drives it).
- ShrinkLine: `✗ Rule r1 broken in 12 steps` / `Shrinking  12 → 8 → 5 → 3 steps`.
- CounterexampleCard: red border, `COUNTEREXAMPLE #001`, the minimal steps, observed vs the rule, replay result.
- DiagnosisCard, FixCard (the coloured diff), VerifyBlock and PrLine.

Every payload string is cleaned here (`clean` for one line, `clean_multiline` for explanations and diffs),
so the views stay safe even when called outside `RookApp.show_event`. Cards wrap to the terminal width;
diff lines are cropped with an ellipsis instead, so nothing ever needs horizontal scrolling at 80 columns.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from rich.console import Group, RenderableType
from rich.text import Text
from textual.widget import Widget

from rook.cli.tui.render import EventView
from rook.cli.tui.safe_text import clean, clean_multiline
from rook.cli.tui.widgets.shell import Transcript
from rook.core.events import Event

GOOD, BAD, WARN, DIM, ACCENT = "#62D69B", "#FF7A70", "#E9C46A", "dim", "#E0563F"
MAX_DIFF_LINES = 40
MAX_VALUE_CHARS = 200
MAX_SOURCE_CHARS = 60
MAX_STEPS = 30

CHECK_NAMES = {
    "replay": "Replay", "project_tests": "Project tests", "regression_test": "Regression test",
    "fresh_search": "Fresh search",
}


def short(text: str, limit: int) -> str:
    """One cleaned line, cut to `limit` characters with an ellipsis."""
    line = clean(text)
    return line if len(line) <= limit else line[: max(limit - 1, 0)] + "…"


def compact(value: Any, limit: int = MAX_VALUE_CHARS) -> str:
    """A value as one short line: strings as-is, everything else as compact JSON."""
    if isinstance(value, str):
        return short(value, limit)
    try:
        dumped = json.dumps(value, ensure_ascii=False, separators=(", ", ": "), default=str)
    except (TypeError, ValueError):
        dumped = repr(value)
    return short(dumped, limit)


def mark(ok: bool) -> Text:
    return Text("✓", style=GOOD) if ok else Text("✗", style=BAD)


class Card(Widget):
    """A transcript card drawn from `lines()`. `plain` is the same content without styles (for tests)."""

    DEFAULT_CSS = """
    Card { height: auto; width: 100%; margin: 0 0 1 0; }
    """

    def lines(self) -> list[Text]:
        raise NotImplementedError

    def render(self) -> RenderableType:
        return Group(*self.lines())

    def redraw(self) -> None:
        self.refresh(layout=True)

    @property
    def plain(self) -> str:
        return "\n".join(line.plain for line in self.lines())


# --- rules ---------------------------------------------------------------------------------------------------

RuleStatus = Literal["proposed", "accepted", "rejected"]


@dataclass
class RuleRow:
    id: str
    text: str
    sources: list[str] = field(default_factory=list)
    status: RuleStatus = "proposed"
    reason: str = ""
    already_broken: bool = False
    selected: bool = False
    approved: bool | None = None  # set once the approve_rules question is answered


def _rule_fields(item: Any, index: int) -> tuple[str, str, list[str]]:
    if isinstance(item, dict):
        rule_id = clean(str(item.get("id") or f"rule_{index}"))
        text = clean(str(item.get("text") or item.get("check") or rule_id))
        evidence = item.get("evidence")
        sources = [short(str(s), MAX_SOURCE_CHARS) for s in evidence] if isinstance(evidence, list) else []
        return rule_id, text, sources
    return f"rule_{index}", clean(str(item)), []


class RulesCard(Card):
    """`◆ These rules should always be true:` and the numbered rules (see the module docstring)."""

    def __init__(self, rules: Iterable[Any] = ()) -> None:
        super().__init__()
        self.rows: list[RuleRow] = []
        self.asking = False
        self.cursor = 0
        for index, item in enumerate(rules, 1):
            rule_id, text, sources = _rule_fields(item, index)
            self.rows.append(RuleRow(rule_id, text, sources))

    def row(self, rule_id: str) -> RuleRow | None:
        return next((r for r in self.rows if r.id == rule_id), None)

    def apply_verdicts(self, verdicts: Iterable[Any]) -> None:
        """rules.reviewed: engine and critic verdicts, in order; the last one decides the status."""
        for verdict in verdicts:
            if not isinstance(verdict, dict):
                continue
            row = self.row(clean(str(verdict.get("rule_id", ""))))
            if row is None:
                continue
            kind = verdict.get("verdict")
            by = clean(str(verdict.get("by") or ""))
            reason = clean(str(verdict.get("reason") or ""))
            row.reason = f"{by}: {reason}" if by and reason else reason
            row.status = "rejected" if kind == "reject" else "accepted"
            revised = verdict.get("revised")
            if kind == "revise" and isinstance(revised, dict) and revised.get("text"):
                row.text = clean(str(revised["text"]))
            row.already_broken = row.already_broken or verdict.get("already_broken") is True
        self.redraw()

    def ask(self, rules: Iterable[Any]) -> None:
        """The approve_rules payload is the final word: text, accepted, reason, already_broken.

        Accepted rules are pre-selected, except a rule flagged `already_broken`: the engine can't tell a
        one-step bug from a wrong rule, so only an explicit human choice may approve it.
        """
        for index, item in enumerate(rules, 1):
            if not isinstance(item, dict):
                continue
            rule_id, text, _ = _rule_fields(item, index)
            row = self.row(rule_id)
            if row is None:
                row = RuleRow(rule_id, text)
                self.rows.append(row)
            row.text = text
            row.status = "accepted" if item.get("accepted") is True else "rejected"
            row.reason = clean(str(item.get("reason") or row.reason))
            row.already_broken = item.get("already_broken") is True
        for row in self.rows:
            row.selected = row.status == "accepted" and not row.already_broken
        self.asking = True
        choosable = self.choosable
        self.cursor = self.rows.index(choosable[0]) if choosable else 0
        self.redraw()

    @property
    def choosable(self) -> list[RuleRow]:
        return [r for r in self.rows if r.status == "accepted"]

    @property
    def selected_ids(self) -> list[str]:
        return [r.id for r in self.rows if r.status == "accepted" and r.selected]

    def move(self, delta: int) -> None:
        choosable = self.choosable
        if not choosable:
            return
        current = self.rows[self.cursor]
        at = choosable.index(current) if current in choosable else 0
        self.cursor = self.rows.index(choosable[(at + delta) % len(choosable)])
        self.redraw()

    def toggle(self, number: int | None = None) -> None:
        """Toggle the rule under the cursor, or rule `number` (1-based, as shown)."""
        if number is not None:
            if not 1 <= number <= len(self.rows):
                return
            self.cursor = number - 1
        row = self.rows[self.cursor] if self.rows else None
        if row is not None and row.status == "accepted":
            row.selected = not row.selected
        self.redraw()

    def decide(self, answer: Any) -> None:
        """question.answered: record which rules were approved ("all", "none" or a list of ids)."""
        if answer == "all":
            approved = {r.id for r in self.choosable}
        elif isinstance(answer, list):
            approved = {clean(str(i)) for i in answer}
        else:
            approved = set()
        for row in self.rows:
            row.approved = row.status == "accepted" and row.id in approved
        self.asking = False
        self.redraw()

    def _marker(self, index: int, row: RuleRow) -> Text:
        if row.approved is not None:
            return Text("✓ ", style=GOOD) if row.approved else Text("· ", style=DIM)
        if row.status == "rejected":
            return Text("✗ ", style=BAD)
        if not self.asking:
            return Text("  ")
        pointer = Text("❯", style=f"bold {ACCENT}") if index == self.cursor else Text(" ")
        return Text.assemble(pointer, "[x] " if row.selected else "[ ] ")

    def lines(self) -> list[Text]:
        header = Text.assemble(Text("◆ ", style=WARN), Text("These rules should always be true:", style="bold"))
        out = [header]
        for index, row in enumerate(self.rows):
            text = Text(row.text, style=f"strike {DIM}" if row.status == "rejected" else "")
            out.append(Text.assemble(" ", self._marker(index, row), f"{index + 1}  ", text))
            notes: list[Text] = []
            if row.sources:
                notes.append(Text(" · ".join(row.sources), style=DIM))
            if row.already_broken and row.status != "rejected":
                notes.append(Text("? possibly already broken · needs your explicit OK", style=WARN))
            if row.reason and (row.status == "rejected" or row.already_broken):
                notes.append(Text(row.reason, style=DIM))
            out.extend(Text.assemble("       ", note) for note in notes)
        return out


# --- violation and shrink -------------------------------------------------------------------------------------


class ShrinkLine(Card):
    """`✗ Rule r1 broken in 12 steps`, then `Shrinking  12 → 8 → 5 → 3 steps` as shrink.step events arrive."""

    DEFAULT_CSS = """
    ShrinkLine { margin: 0; }
    """

    def __init__(self, violation_id: str, rule_id: str | None, steps_count: int) -> None:
        super().__init__()
        self.violation_id = violation_id
        self.rule_id = rule_id
        self.counts = [steps_count]

    def step(self, steps_count: int) -> None:
        if steps_count != self.counts[-1]:
            self.counts.append(steps_count)
            self.redraw()

    def lines(self) -> list[Text]:
        out: list[Text] = []
        if self.rule_id is not None:
            out.append(Text.assemble(mark(False), f" Rule {self.rule_id} broken in {self.counts[0]} steps"))
        if len(self.counts) > 1:
            chain = Text("  Shrinking  ", style=DIM)
            for i, count in enumerate(self.counts):
                if i:
                    chain.append(" → ", style=DIM)
                chain.append(str(count), style=f"bold {BAD}" if i == len(self.counts) - 1 else "")
            chain.append(" steps", style=DIM)
            out.append(chain)
        return out


# --- counterexample --------------------------------------------------------------------------------------------


def step_text(step: Any) -> str:
    """`alice: refund(order=1, amount=60)`; parallel steps are joined with ` | `."""
    if isinstance(step, dict):
        parallel = step.get("parallel")
        if isinstance(parallel, list):
            return "at the same time: " + " | ".join(step_text(s) for s in parallel)
        action = clean(str(step.get("action", "?")))
        params = step.get("params")
        args = ", ".join(f"{clean(str(k))}={compact(v, 40)}" for k, v in params.items()) \
            if isinstance(params, dict) else ""
        actor = step.get("actor")
        call = f"{action}({args})"
        return f"{clean(str(actor))}: {call}" if actor else call
    return compact(step)


def observed_text(observed: Any) -> str:
    """A flat dict reads `paid 100 · refunded 110`; anything else is compact JSON."""
    if isinstance(observed, dict) and observed and all(
        isinstance(v, str | int | float | bool) or v is None for v in observed.values()
    ):
        return short(" · ".join(f"{k} {compact(v, 40)}" for k, v in observed.items()), MAX_VALUE_CHARS)
    return compact(observed)


def cx_title(cx_id: str) -> str:
    number = re.fullmatch(r"cx_?(\d+)", cx_id)
    return f"COUNTEREXAMPLE #{number.group(1)}" if number else f"COUNTEREXAMPLE {cx_id}"


class CounterexampleCard(Card):
    DEFAULT_CSS = """
    CounterexampleCard { border: round #FF7A70; border-title-color: #FF7A70; border-title-style: bold;
                         padding: 0 1; }
    """

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.data = data
        self.cx_id = clean(str(data.get("cx_id", "")))
        self.border_title = Text(short(cx_title(self.cx_id), 60))

    def update_data(self, data: dict[str, Any]) -> None:
        """counterexample.saved is published again with its test_path once the regression test is written."""
        self.data = data
        self.redraw()

    def lines(self) -> list[Text]:
        d = self.data
        raw = d.get("steps")
        steps: list[Any] = raw if isinstance(raw, list) else []
        out = [Text(clean(str(d.get("rule_text", ""))), style="bold")]
        out += [Text(f"{i}. {step_text(s)}") for i, s in enumerate(steps[:MAX_STEPS], 1)]
        if len(steps) > MAX_STEPS:
            out.append(Text(f"… {len(steps) - MAX_STEPS} more steps", style=DIM))
        out.append(Text.assemble(Text("Observed   ", style=DIM), observed_text(d.get("observed"))))
        out.append(Text.assemble(Text("Must hold  ", style=DIM), compact(d.get("expected")), "  ",
                                 mark(False), Text(" rule broken", style=BAD)))
        reproduced = clean(str(d.get("reproduced", "")))
        verdict = Text("? flaky", style=WARN) if d.get("flaky") else Text.assemble(mark(True), " real bug")
        out.append(Text.assemble(f"Replayed {reproduced} on the real app ", verdict))
        if d.get("test_path"):
            out.append(Text.assemble(Text("Regression test  ", style=DIM), short(str(d["test_path"]), 70)))
        return out


# --- diagnosis and fix -----------------------------------------------------------------------------------------


def _reviewed(reviewed: bool, who: str) -> Text:
    return Text(f"reviewed by the {who}" if reviewed else "not reviewed", style=f"italic {DIM}")


class DiagnosisCard(Card):
    """`Root cause src/refunds.js : 42` and the explanation."""

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.cx_id = clean(str(data.get("cx_id", "")))
        self.file = clean(str(data.get("file", "")))
        line = data.get("line")
        self.line = line if isinstance(line, int) else None
        self.explanation = clean_multiline(str(data.get("explanation", ""))).strip()
        self.reviewed = data.get("reviewed") is True

    def lines(self) -> list[Text]:
        where = f"{self.file} : {self.line}" if self.line is not None else self.file
        out = [Text.assemble(Text("Root cause ", style="bold"), Text(where, style=f"bold {ACCENT}"))]
        out += [Text(f"  {line}") for line in self.explanation.splitlines()]
        out.append(Text.assemble("  ", _reviewed(self.reviewed, "Diagnosis Reviewer")))
        return out


def diff_text(diff: str, limit: int = MAX_DIFF_LINES) -> Text:
    """A unified diff with red `-` and green `+` lines; each line is cropped, never wrapped."""
    lines = clean_multiline(diff).rstrip("\n").splitlines()
    out = Text(no_wrap=True, overflow="ellipsis")
    for i, line in enumerate(lines[:limit]):
        if i:
            out.append("\n")
        if line.startswith(("+++", "---", "diff ", "index ")):
            style = DIM
        elif line.startswith("+"):
            style = GOOD
        elif line.startswith("-"):
            style = BAD
        elif line.startswith("@@"):
            style = "cyan"
        else:
            style = ""
        out.append(line, style=style)
    if len(lines) > limit:
        out.append(f"\n… {len(lines) - limit} more lines", style=DIM)
    return out


class FixCard(Card):
    """`◆ Fix ready · src/refunds.js` and the diff."""

    DEFAULT_CSS = """
    FixCard { border-left: outer #3A3A3A; padding: 0 1; }
    """

    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__()
        self.cx_id = clean(str(data.get("cx_id", "")))
        files = data.get("files")
        self.files = [clean(str(f)) for f in files] if isinstance(files, list) else []
        self.diff = str(data.get("diff", ""))
        self.reviewed = data.get("reviewed") is True

    def lines(self) -> list[Text]:
        return [
            Text.assemble(Text("◆ ", style=WARN), Text("Fix ready", style="bold"), f" · {', '.join(self.files)}"),
            diff_text(self.diff),
            _reviewed(self.reviewed, "Fix Reviewer"),
        ]


# --- verify and ship -------------------------------------------------------------------------------------------


class VerifyBlock(Card):
    """One line per verification check, then `✓ FIX VERIFIED` or `✗ Fix not verified · <why>`."""

    def __init__(self, cx_id: str) -> None:
        super().__init__()
        self.cx_id = cx_id
        self.checks: dict[str, tuple[str, str]] = {}  # check -> (status, detail), in arrival order
        self.verified: bool | None = None
        self.summary = ""

    @property
    def done(self) -> bool:
        return self.verified is not None

    def step(self, check: str, status: str, detail: str) -> None:
        self.checks[check] = (status, detail)
        self.redraw()

    def finish(self, verified: bool, summary: str) -> None:
        self.verified, self.summary = verified, summary
        self.redraw()

    def lines(self) -> list[Text]:
        out = []
        for check, (status, detail) in self.checks.items():
            symbol = {"passed": mark(True), "failed": mark(False)}.get(status, Text("◐", style=WARN))
            name = CHECK_NAMES.get(check, check.replace("_", " ").capitalize())
            out.append(Text.assemble("  ", symbol, f" {name}: {detail}"))
        if self.verified:
            out.append(Text("✓ FIX VERIFIED", style=f"bold {GOOD}"))
        elif self.verified is False:
            out.append(Text.assemble(mark(False), Text(" Fix not verified", style="bold"), f" · {self.summary}"))
        return out


class PrLine(Card):
    """`✓ PR #88 opened · <url>`, or the local commit when the fix is shipped without a PR."""

    DEFAULT_CSS = """
    PrLine { margin: 0; }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def lines(self) -> list[Text]:
        return [Text.assemble(mark(True), f" {self.text}")]


# --- views ---------------------------------------------------------------------------------------------------

def latest[W: Widget](transcript: Transcript, kind: type[W], match: Callable[[W], bool] | None = None) -> W | None:
    """The most recent `kind` widget in the transcript (optionally the latest whose `match(widget)` is true)."""
    for widget in reversed(list(transcript.query(kind))):
        if match is None or match(widget):
            return widget
    return None


def show_rules_proposed(event: Event, transcript: Transcript) -> None:
    rules = event.data.get("rules")
    transcript.mount_item(RulesCard(rules if isinstance(rules, list) else []))


def show_rules_reviewed(event: Event, transcript: Transcript) -> None:
    card = latest(transcript, RulesCard, lambda c: not c.asking)
    verdicts = event.data.get("verdicts")
    if card is not None and isinstance(verdicts, list):
        card.apply_verdicts(verdicts)


def show_violation(event: Event, transcript: Transcript) -> None:
    d = event.data
    transcript.mount_item(ShrinkLine(clean(str(d["violation_id"])), clean(str(d["rule_id"])), int(d["steps_count"])))


def show_shrink_step(event: Event, transcript: Transcript) -> None:
    violation_id = clean(str(event.data["violation_id"]))
    line = latest(transcript, ShrinkLine, lambda w: w.violation_id == violation_id)
    if line is None:
        transcript.mount_item(ShrinkLine(violation_id, None, int(event.data["steps_count"])))
    else:
        line.step(int(event.data["steps_count"]))


def show_counterexample(event: Event, transcript: Transcript) -> None:
    cx_id = clean(str(event.data["cx_id"]))
    card = latest(transcript, CounterexampleCard, lambda c: c.cx_id == cx_id)
    if card is None:
        transcript.mount_item(CounterexampleCard(event.data))
    else:
        card.update_data(event.data)


def show_diagnosis(event: Event, transcript: Transcript) -> None:
    transcript.mount_item(DiagnosisCard(event.data))


def show_fix(event: Event, transcript: Transcript) -> None:
    transcript.mount_item(FixCard(event.data))


def show_verify_step(event: Event, transcript: Transcript) -> None:
    d = event.data
    cx_id = clean(str(d["cx_id"]))
    block = latest(transcript, VerifyBlock, lambda b: b.cx_id == cx_id and not b.done)
    if block is None:
        block = VerifyBlock(cx_id)
        transcript.mount_item(block)
    block.step(clean(str(d["check"])), clean(str(d["status"])), clean(str(d["detail"])))


def show_verify_done(event: Event, transcript: Transcript) -> None:
    d = event.data
    cx_id = clean(str(d["cx_id"]))
    block = latest(transcript, VerifyBlock, lambda b: b.cx_id == cx_id and not b.done)
    if block is None:
        block = VerifyBlock(cx_id)
        transcript.mount_item(block)
    block.finish(d["verified"] is True, clean(str(d["summary"])))


def show_fix_committed(event: Event, transcript: Transcript) -> None:
    d = event.data
    raw = d.get("files")
    files: list[Any] = raw if isinstance(raw, list) else []
    commit = clean(str(d["commit"]))[:7]
    transcript.mount_item(PrLine(f"Fix committed to {clean(str(d['branch']))} · {commit} · {len(files)} files"))


def show_pr(event: Event, transcript: Transcript) -> None:
    d = event.data
    transcript.mount_item(PrLine(f"PR #{int(d['number'])} opened · {clean(str(d['url']))}"))


def card_views() -> dict[str, EventView]:
    return {
        "rules.proposed": show_rules_proposed,
        "rules.reviewed": show_rules_reviewed,
        "violation.found": show_violation,
        "shrink.step": show_shrink_step,
        "counterexample.saved": show_counterexample,
        "diagnosis.ready": show_diagnosis,
        "fix.ready": show_fix,
        "verify.step": show_verify_step,
        "verify.done": show_verify_done,
        "fix.committed": show_fix_committed,
        "pr.opened": show_pr,
    }


class HasViews(Protocol):
    views: dict[str, EventView]


def register(app: HasViews) -> None:
    """Replace the default one-line views with these cards (RookApp.views is the 025 seam)."""
    app.views.update(card_views())
