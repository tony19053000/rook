"""`rook run --ci`: the non-interactive run (04_FRONTEND_SPEC.md §2.6).

- Plain event lines (no animation, no prompts), then a summary table.
- Questions: with `--auto` the Session answers them itself (the rails' auto answers). Without it, CI mode
  answers like auto mode for the rules (critic-approved only, never a rule flagged `already_broken`: only
  a human may approve that one), says "no" to fixing and shipping (CI never changes code unless `--auto`),
  picks "report"/"stop" in a menu, and stops the run on a setup value it was not given (`--setup NAME`).
- Exit codes: 0 every approved rule held; 1 an approved rule is broken (the engine found a violation);
  2 the run failed or was stopped before it could say (and bad arguments).
- Writes `rook-report.json` and `rook-report.md` (for the GitHub Action comment). Event data is already
  redacted by the bus; app and Bob text in the Markdown is put in code spans so it cannot ping or inject.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from rook.cli.tui.render import BAD, GOOD, WARN, event_lines
from rook.cli.tui.safe_text import clean
from rook.core.events import Event, redact_text
from rook.core.session import RunResult, Session

EXIT_HELD, EXIT_BROKEN, EXIT_ERROR = 0, 1, 2
REPORT_JSON = "rook-report.json"
REPORT_MD = "rook-report.md"
CRITIC_OK = ("approve", "revise")
MENU_CHOICES = ("report", "stop")
_CELL_MAX = 300
_BLOCK_MAX = 4_000


def safe_rule_ids(payload: Any) -> list[str]:
    """The rules CI mode may approve by itself: accepted, approved by the critic and not flagged
    `already_broken` (admin rule B: only a human may approve a flagged rule)."""
    rules = payload.get("rules") if isinstance(payload, dict) else None
    ids = []
    for rule in rules if isinstance(rules, list) else []:
        if (isinstance(rule, dict) and rule.get("accepted") is True and rule.get("critic") in CRITIC_OK
                and rule.get("already_broken") is not True and isinstance(rule.get("id"), str)):
            ids.append(rule["id"])
    return ids


def ci_answer(data: dict[str, Any]) -> Any | None:
    """CI mode's answer to a `question.asked` (without `--auto`), or None when it cannot answer."""
    kind = data.get("kind")
    if kind == "approve_rules":
        return safe_rule_ids(data.get("payload")) or "none"
    if kind in ("fix", "pr"):
        return "no"
    if kind == "menu":
        ids = [o.get("id") for o in data.get("options") or [] if isinstance(o, dict)]
        return next((c for c in MENU_CHOICES if c in ids), None)
    return None  # a setup value or a repo choice needs a person


@dataclass
class CiReport:
    run_id: str = ""
    repo: str = ""
    status: str = "failed"
    summary: str = ""
    auto: bool = False
    approved: list[str] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)  # already_broken rules left for a human
    violations: list[dict[str, Any]] = field(default_factory=list)
    counterexamples: dict[str, dict[str, Any]] = field(default_factory=dict)
    verified: list[str] = field(default_factory=list)
    committed: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    coins: float = 0.0
    notes: list[str] = field(default_factory=list)

    def observe(self, event: Event) -> None:
        d = event.data
        match event.type:
            case "run.created":
                self.run_id, self.repo = event.run_id, str(d["repo"]["name"])
            case "question.asked" if d["kind"] == "approve_rules":
                rules = d["payload"].get("rules", []) if isinstance(d["payload"], dict) else []
                self.flagged = [r["id"] for r in rules if isinstance(r, dict) and r.get("already_broken") is True]
            case "rules.approved":
                self.approved = list(d["rule_ids"])
            case "violation.found":
                self.violations.append({"rule_id": d["rule_id"], "steps_count": d["steps_count"]})
            case "counterexample.saved":
                self.counterexamples[d["cx_id"]] = {k: d[k] for k in (
                    "cx_id", "rule_id", "rule_text", "steps", "observed", "expected", "reproduced", "flaky",
                    "test_path")}
            case "verify.done" if d["verified"]:
                self.verified.append(d["cx_id"])
            case "fix.committed":
                self.committed.append({"cx_id": d["cx_id"], "branch": d["branch"], "commit": d["commit"]})
            case "pr.opened":
                self.prs.append({"url": d["url"], "number": d["number"]})
            case "cost.update":
                self.coins = float(d["coins_total"])
            case "run.finished":
                self.status, self.summary = d["status"], d["summary"]

    @property
    def broken_rules(self) -> list[str]:
        return list(dict.fromkeys(v["rule_id"] for v in self.violations))

    @property
    def exit_code(self) -> int:
        if self.violations:
            return EXIT_BROKEN
        return EXIT_HELD if self.status == "done" else EXIT_ERROR

    def to_json(self) -> dict[str, Any]:
        return {"version": 1, "exit_code": self.exit_code, "broken_rules": self.broken_rules, **asdict(self)}


# --- the run --------------------------------------------------------------------------------------------


def plain_console(file: Any = None) -> Console:
    """No colors unless the output is a terminal, no markup or emoji parsing, no wrapping of long lines."""
    return Console(file=file, highlight=False, emoji=False, markup=False, soft_wrap=True)


async def run_ci(session: Session, console: Console, report_dir: Path) -> CiReport:
    report = CiReport(auto=session.options.auto)

    def say(text: str, style: str = WARN) -> None:
        report.notes.append(text)
        console.print(Text(text, style=style))

    def handle(event: Event) -> None:
        report.observe(event)
        for line in event_lines(event):
            console.print(line)
        if event.type != "question.asked" or session.options.auto:
            return
        payload = event.data.get("payload")
        name = payload.get("name") if isinstance(payload, dict) else None
        if event.data["kind"] == "setup_value" and name in session.options.setup_values:
            return  # given with --setup: the Session answers it itself
        answer = ci_answer(event.data)
        if answer is None:
            hint = f" (pass it with --setup {clean(str(name))})" if event.data["kind"] == "setup_value" and name else ""
            say(f"CI mode cannot answer a {event.data['kind']} question{hint}; stopping the run.", BAD)
            session.cancel()
        elif not session.answer(event.data["question_id"], answer):
            say("CI mode's answer was refused; stopping the run.", BAD)
            session.cancel()

    async def follow() -> None:
        try:
            async for event in session.events():
                handle(event)
        except Exception as exc:  # noqa: BLE001 - never leave the run waiting for an answer
            say(redact_text(f"CI mode stopped the run: {type(exc).__name__}: {exc}"), BAD)
            session.cancel()

    follower = asyncio.create_task(follow())
    try:
        result = await session.run()
    finally:
        await asyncio.wait([follower], timeout=5.0)
        follower.cancel()
    finish(report, result)
    write_reports(report, report_dir)
    console.print(summary_table(report))
    return report


def finish(report: CiReport, result: RunResult) -> None:
    report.run_id = report.run_id or result.run_id
    report.status, report.summary = result.status, result.summary


def summary_table(report: CiReport) -> Table:
    table = Table(title=f"Rook · {clean(report.repo) or 'run'} · {report.status}", show_lines=False)
    table.add_column("Rule")
    table.add_column("Result")
    broken = {v["rule_id"] for v in report.violations}
    for rule_id in report.approved:
        cx = next((c for c in report.counterexamples.values() if c["rule_id"] == rule_id), None)
        if rule_id in broken:
            where = f" · {cx['cx_id']}, {len(cx['steps'])} steps" if cx else ""
            fixed = " · fix verified" if cx and cx["cx_id"] in report.verified else ""
            table.add_row(clean(rule_id), Text(f"✗ broken{where}{fixed}", style=BAD))
        else:
            table.add_row(clean(rule_id), Text("✓ held", style=GOOD))
    for rule_id in report.flagged:
        if rule_id not in report.approved:
            table.add_row(clean(rule_id), Text("! not approved: may already be broken (a human decides)", style=WARN))
    verdict = {EXIT_HELD: "every approved rule held", EXIT_BROKEN: "an approved rule is broken",
               EXIT_ERROR: "the run did not finish"}[report.exit_code]
    table.caption = f"exit {report.exit_code}: {verdict} · {report.coins:.2f} coins"
    return table


# --- reports ----------------------------------------------------------------------------------------------


def write_reports(report: CiReport, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path, md_path = report_dir / REPORT_JSON, report_dir / REPORT_MD
    json_path.write_text(json.dumps(report.to_json(), indent=2, sort_keys=True, default=str) + "\n",
                         encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return json_path, md_path


def md_code(value: Any, limit: int = _CELL_MAX) -> str:
    """Untrusted text as one inline code span: no Markdown, links, mentions or table breaks."""
    text = clean(value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str))
    text = text.replace("`", "'").replace("|", "¦")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return f"`{text}`" if text else "` `"


def md_block(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, indent=2, sort_keys=True, default=str)
    text = text.replace("~~~", "～～～")[:_BLOCK_MAX]
    return f"~~~\n{text}\n~~~"


def step_text(step: Any) -> str:
    if isinstance(step, dict) and isinstance(step.get("parallel"), list):
        return "at the same time: " + " + ".join(step_text(s) for s in step["parallel"])
    if isinstance(step, dict):
        params = json.dumps(step.get("params") or {}, sort_keys=True, default=str)
        return f"{step.get('actor', '?')}: {step.get('action', '?')} {params}"
    return str(step)


def markdown(report: CiReport) -> str:
    code = report.exit_code
    head = {EXIT_HELD: "✓ Every approved rule held", EXIT_BROKEN: "✗ A business rule is broken",
            EXIT_ERROR: "! The run did not finish"}[code]
    out = [f"## Rook: {head}", "",
           (f"Repo {md_code(report.repo)} · run {md_code(report.run_id)} · status **{report.status}** · "
            f"{report.coins:.2f} coins · exit {code}"), ""]
    broken = set(report.broken_rules)
    if report.approved or report.flagged:
        out += ["| Rule | Result |", "|---|---|"]
        out += [f"| {md_code(r)} | {'✗ broken' if r in broken else '✓ held'} |" for r in report.approved]
        out += [f"| {md_code(r)} | ! not approved: may already be broken, a human decides |"
                for r in report.flagged if r not in report.approved]
        out.append("")
    for cx in report.counterexamples.values():
        out += [f"### Counterexample {md_code(cx['cx_id'])}: rule {md_code(cx['rule_id'])}", "",
                f"Rule: {md_code(cx['rule_text'])}", "", "Minimal steps:", ""]
        out += [f"{i}. {md_code(step_text(s))}" for i, s in enumerate(cx["steps"], 1)]
        out += ["", f"Replayed {md_code(cx['reproduced'])} on the real app"
                    + (" (flaky)" if cx["flaky"] else "") + ".", "",
                "Observed:", "", md_block(cx["observed"]), "", f"Expected: {md_code(cx['expected'])}", ""]
        if cx["cx_id"] in report.verified:
            out.append("✓ A fix was verified by the engine.")
        for c in report.committed:
            if c["cx_id"] == cx["cx_id"]:
                out.append(f"Fix committed to branch {md_code(c['branch'])} ({md_code(c['commit'][:12])}).")
        out.append("")
    for pr in report.prs:
        out += [f"PR #{int(pr['number'])}: {md_code(pr['url'])}", ""]
    if report.summary:
        out += [f"Summary: {md_code(report.summary, 1_000)}", ""]
    for note in report.notes:
        out += [f"Note: {md_code(note)}", ""]
    return "\n".join(out)
