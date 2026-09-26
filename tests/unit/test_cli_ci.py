"""ROOK-024: `rook run --ci` on minishop with the real Session and engine and a scripted Bob (0 coins, no Docker).

AC: exit 1 on buggy minishop, 0 on fixed; rules flagged `already_broken` are never approved automatically;
the reports are written; questions are never left waiting.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from cli_helpers import CI_FLAGS, RULES, ScriptedSessions, script
from session_helpers import minishop_source
from typer.testing import CliRunner

from rook.cli import ci
from rook.cli.main import app
from rook.core.events import Event, clear_secrets, now_ts

runner = CliRunner()


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def run_ci(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sessions: ScriptedSessions, *extra: str) -> Any:
    monkeypatch.setattr("rook.cli.runs.build_session", sessions)
    src = minishop_source(tmp_path)
    reports = tmp_path / "reports"
    result = runner.invoke(app, ["run", str(src), *CI_FLAGS, "--report-dir", str(reports), *extra])
    return result, reports


def read_report(reports: Path) -> tuple[dict[str, Any], str]:
    data = json.loads((reports / ci.REPORT_JSON).read_text())
    return data, (reports / ci.REPORT_MD).read_text()


def test_ci_exits_1_on_buggy_minishop_and_writes_the_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = ScriptedSessions(tmp_path, script())
    result, reports = run_ci(tmp_path, monkeypatch, sessions)
    assert result.exit_code == 1, result.output
    out = result.output
    assert "Rule refund_le_paid broken" in out and "COUNTEREXAMPLE cx_001" in out
    assert "exit 1: an approved rule is broken" in out  # the summary table
    assert "\x1b[" not in out  # plain output, no colors or animation
    data, md = read_report(reports)
    assert data["exit_code"] == 1 and data["broken_rules"] == ["refund_le_paid"]
    assert data["approved"] == ["refund_le_paid"] and data["status"] == "done"
    assert list(data["counterexamples"]) == ["cx_001"]
    assert md.startswith("## Rook: ✗ A business rule is broken")
    assert "### Counterexample `cx_001`" in md and "Minimal steps:" in md
    # Without --auto, CI mode never changes code: the fix question is answered "no".
    fix = [a for a in sessions.events("question.answered") if a["by"] == "user"]
    assert [a["answer"] for a in fix] == [["refund_le_paid"], "no"]
    assert "surgeon" not in [a["agent"] for a in sessions.events("agent.started")]


def test_ci_exits_0_on_fixed_minishop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = ScriptedSessions(tmp_path, script(), fixed=True)
    result, reports = run_ci(tmp_path, monkeypatch, sessions)
    assert result.exit_code == 0, result.output
    assert "exit 0: every approved rule held" in result.output
    data, md = read_report(reports)
    assert data["exit_code"] == 0 and data["broken_rules"] == [] and data["counterexamples"] == {}
    assert md.startswith("## Rook: ✓ Every approved rule held")
    assert "| `refund_le_paid` | ✓ held |" in md


def test_ci_never_approves_a_flagged_rule_without_auto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The critic approves all four rules; the buggy app breaks the admin rule on the first request, so the
    # engine flags it. CI mode answers for the user and must leave it out.
    sessions = ScriptedSessions(tmp_path, script(tuple(RULES)))
    result, reports = run_ci(tmp_path, monkeypatch, sessions)
    (asked, *_) = sessions.events("question.asked")
    assert [r["id"] for r in asked["payload"]["rules"] if r["already_broken"]] == ["admin_export_forbidden"]
    (answer, *_) = sessions.events("question.answered")
    assert answer["by"] == "user" and "admin_export_forbidden" not in answer["answer"]
    assert "admin_export_forbidden" not in sessions.events("rules.approved")[0]["rule_ids"]
    data, md = read_report(reports)
    assert data["flagged"] == ["admin_export_forbidden"]
    assert "admin_export_forbidden" not in data["approved"]
    assert "| `admin_export_forbidden` | ! not approved: may already be broken, a human decides |" in md
    assert result.exit_code == 1  # another approved rule is broken


def test_ci_auto_never_approves_a_flagged_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # --auto: the Session answers itself. An unreviewed diagnosis keeps the run from fixing (rails).
    reject = {"verdict": "reject", "reason": "the line does not explain it"}
    sessions = ScriptedSessions(tmp_path, script(tuple(RULES), diag_reviewer=[reject]))
    result, _ = run_ci(tmp_path, monkeypatch, sessions, "--auto")
    (answer, *_) = sessions.events("question.answered")
    assert answer["by"] == "auto" and "admin_export_forbidden" not in answer["answer"]
    assert set(answer["answer"]) == set(RULES) - {"admin_export_forbidden"}
    assert all(a["by"] == "auto" for a in sessions.events("question.answered"))
    assert result.exit_code == 1, result.output


def test_ci_stops_on_a_setup_value_it_was_not_given(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {"mode": "command", "build": "", "start": "uvicorn app:app", "port": 8000, "health_path": "/health",
            "env_required": ["PAYMENT_API_KEY"], "env_defaults": {}}
    sessions = ScriptedSessions(tmp_path, script(mechanic=[plan]))
    result, reports = run_ci(tmp_path, monkeypatch, sessions)
    assert result.exit_code == 2, result.output
    assert "cannot answer a setup_value question (pass it with --setup PAYMENT_API_KEY)" in result.output
    data, _ = read_report(reports)
    assert data["status"] == "cancelled" and data["exit_code"] == 2


def test_ci_setup_values_come_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {"mode": "command", "build": "", "start": "uvicorn app:app", "port": 8000, "health_path": "/health",
            "env_required": ["PAYMENT_API_KEY"], "env_defaults": {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}}
    monkeypatch.setenv("PAYMENT_API_KEY", "not-a-real-key-123")
    sessions = ScriptedSessions(tmp_path, script(mechanic=[plan]), fixed=True)
    result, _ = run_ci(tmp_path, monkeypatch, sessions, "--setup", "PAYMENT_API_KEY")
    assert result.exit_code == 0, result.output
    assert sessions.session.options.setup_values == {"PAYMENT_API_KEY": "not-a-real-key-123"}
    assert "not-a-real-key-123" not in result.output


def test_ci_setup_flag_needs_the_variable(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", str(minishop_source(tmp_path)), "--ci", "--setup", "NOPE_NOT_SET_X"])
    assert result.exit_code == 2
    assert "NOPE_NOT_SET_X is not set" in result.output


# --- the answer policy and the report, unit level ----------------------------------------------------------


def rules_question(*rules: dict[str, Any]) -> dict[str, Any]:
    return {"question_id": "q1", "kind": "approve_rules", "text": "Approve?", "options": [],
            "payload": {"rules": list(rules)}}


def rule(rule_id: str, **fields: Any) -> dict[str, Any]:
    return {"id": rule_id, "accepted": True, "critic": "approve", "already_broken": False} | fields


def test_ci_answer_policy() -> None:
    q = rules_question(rule("ok"), rule("revised", critic="revise"), rule("flagged", already_broken=True),
                       rule("rejected", critic="reject"), rule("engine_no", accepted=False), rule("nocritic", critic=None))
    assert ci.ci_answer(q) == ["ok", "revised"]
    assert ci.ci_answer(rules_question(rule("flagged", already_broken=True))) == "none"
    assert ci.ci_answer(rules_question()) == "none"
    assert ci.ci_answer({"kind": "approve_rules", "payload": "junk"}) == "none"
    assert ci.ci_answer({"kind": "fix"}) == "no" and ci.ci_answer({"kind": "pr"}) == "no"
    menu = {"kind": "menu", "options": [{"id": "retry"}, {"id": "stop"}, {"id": "report"}]}
    assert ci.ci_answer(menu) == "report"
    assert ci.ci_answer({"kind": "menu", "options": [{"id": "retry"}]}) is None
    assert ci.ci_answer({"kind": "setup_value", "payload": {"name": "X"}}) is None
    assert ci.ci_answer({"kind": "repo", "options": []}) is None


def ev(seq: int, event_type: str, data: dict[str, Any]) -> Event:
    return Event.model_validate({"seq": seq, "ts": now_ts(), "run_id": "r1", "type": event_type, "data": data})


def test_exit_codes() -> None:
    report = ci.CiReport()
    assert report.exit_code == 2  # never finished
    report.observe(ev(1, "run.finished", {"status": "done", "summary": "held"}))
    assert report.exit_code == 0
    report.observe(ev(2, "violation.found", {"violation_id": "v1", "rule_id": "r", "steps_count": 3, "observed": {}}))
    assert report.exit_code == 1
    failed = ci.CiReport()
    failed.observe(ev(1, "run.finished", {"status": "failed", "summary": "boom"}))
    assert failed.exit_code == 2
    failed.observe(ev(2, "violation.found", {"violation_id": "v1", "rule_id": "r", "steps_count": 3, "observed": {}}))
    assert failed.exit_code == 1  # the rule is broken even if a later phase failed


def test_markdown_puts_untrusted_text_in_code_spans(tmp_path: Path) -> None:
    report = ci.CiReport(repo="shop", run_id="r1", status="done", approved=["r|1"])
    hostile = "@team `rm -rf` [x](http://evil) | ~~~\n<img src=x>\x1b[31m"
    report.observe(ev(1, "violation.found", {"violation_id": "v", "rule_id": "r|1", "steps_count": 1, "observed": {}}))
    report.observe(ev(2, "counterexample.saved", {
        "cx_id": "cx_001", "rule_id": "r|1", "rule_text": hostile, "expected": hostile, "reproduced": "10/10",
        "flaky": False, "test_path": None, "observed": {"note": hostile},
        "steps": [{"action": hostile, "actor": "customer", "params": {"x": hostile}}]}))
    ci.write_reports(report, tmp_path)
    md = (tmp_path / ci.REPORT_MD).read_text()
    assert "\x1b" not in md
    lines = md.splitlines()
    fences = [i for i, line in enumerate(lines) if line.startswith("~~~")]
    assert len(fences) == 2  # the observed block cannot be closed early
    for i, line in enumerate(lines):
        if "@team" in line and not fences[0] < i < fences[1]:
            # one inline code span holds all of it: no mention, link, HTML or table cell break
            assert line.count("`") == 2 and line.index("`") < line.index("@team") < line.rindex("`"), line
            assert "|" not in line.replace("| `r¦1` |", "")
    data = json.loads((tmp_path / ci.REPORT_JSON).read_text())
    assert data["exit_code"] == 1 and data["broken_rules"] == ["r|1"]
