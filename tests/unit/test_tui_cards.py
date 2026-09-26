"""Pilot tests for the result cards (ROOK-027): each card renders from real-schema sample events."""

from __future__ import annotations

from typing import Any

from textual.widget import Widget
from tui_question_samples import CX, DIFF, RULES, SIZE, VERDICTS, Events, booted, make_app

from rook.cli.tui.app import RookApp
from rook.cli.tui.widgets.cards import (
    Card,
    CounterexampleCard,
    DiagnosisCard,
    FixCard,
    PrLine,
    RulesCard,
    ShrinkLine,
    VerifyBlock,
    card_views,
    compact,
    cx_title,
    diff_text,
    observed_text,
    step_text,
)


def fits(app: RookApp) -> bool:
    return app.transcript.max_scroll_x == 0 and all(
        w.region.right <= SIZE[0] for w in app.transcript.walk_children(Widget) if w.display
    )


async def shown(pilot: Any, app: RookApp, events: Events, *items: tuple[str, dict[str, Any]]) -> None:
    for event_type, data in items:
        app.show_event(events(event_type, data))
    await pilot.pause()


async def test_rules_card_shows_sources_then_verdicts() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        await shown(pilot, app, events, ("rules.proposed", {"rules": RULES}))
        card = app.transcript.query_one(RulesCard)
        assert card.plain.splitlines() == [
            "◆ These rules should always be true:",
            "   1  Refunds never exceed the amount paid",
            "       src/refunds.js:40 · README",
            "   2  An order total is never negative",
            "       src/orders.js:12",
            "   3  Stock never goes below zero",
            "       src/stock.js:8",
        ]
        await shown(pilot, app, events, ("rules.reviewed", {"verdicts": VERDICTS}))
        assert card.plain.splitlines() == [
            "◆ These rules should always be true:",
            "   1  Refunds never exceed the amount paid",
            "       src/refunds.js:40 · README",
            "   2  An order total is never negative",
            "       src/orders.js:12",
            "       ? possibly already broken · needs your explicit OK",
            "       critic: a response contract",
            " ✗ 3  Stock never goes below zero",
            "       src/stock.js:8",
            "       engine: stock is not exposed by any action",
        ]
        strikes = [span for line in card.lines() for span in line.spans if "strike" in str(span.style)]
        assert len(strikes) == 1
        assert fits(app)


async def test_rules_card_revision_replaces_the_text() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        revised = {**RULES[0], "text": "Refunds never exceed the paid amount of the order"}
        await shown(pilot, app, events, ("rules.proposed", {"rules": RULES}),
                    ("rules.reviewed", {"verdicts": [{"rule_id": "refund_le_paid", "verdict": "revise",
                                                      "reason": "clearer", "by": "critic", "revised": revised}]}))
        card = app.transcript.query_one(RulesCard)
        assert "Refunds never exceed the paid amount of the order" in card.plain
        assert card.rows[0].status == "accepted"


async def test_shrink_line_grows_with_each_step() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        await shown(pilot, app, events, ("violation.found", {"violation_id": "v1", "rule_id": "refund_le_paid",
                                                             "steps_count": 12, "observed": {"refunded": 110}}))
        line = app.transcript.query_one(ShrinkLine)
        assert line.plain == "✗ Rule refund_le_paid broken in 12 steps"
        for count in (8, 5, 5, 3):
            await shown(pilot, app, events, ("shrink.step", {"violation_id": "v1", "steps_count": count}))
        assert line.plain.splitlines()[1] == "  Shrinking  12 → 8 → 5 → 3 steps"
        assert len(app.transcript.query(ShrinkLine)) == 1


async def test_counterexample_card_has_the_title_steps_values_and_replay() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        await shown(pilot, app, events, ("counterexample.saved", CX))
        card = app.transcript.query_one(CounterexampleCard)
        assert card.border_title == "COUNTEREXAMPLE #001"
        assert card.plain.splitlines() == [
            "Refunds never exceed the amount paid",
            "1. alice: create_order(amount=100)",
            "2. alice: refund(amount=60)",
            "3. at the same time: alice: refund(amount=50) | bob: refund(amount=10)",
            "Observed   paid 100 · refunded 110",
            "Must hold  order.refunded <= order.paid  ✗ rule broken",
            "Replayed 10/10 on the real app ✓ real bug",
        ]
        assert card.styles.border_top[0] == "round"
        # published again once the regression test exists: the same card is updated
        await shown(pilot, app, events, ("counterexample.saved", {**CX, "test_path": "tests/rook/cx_001.test.js"}))
        assert len(app.transcript.query(CounterexampleCard)) == 1
        assert card.plain.splitlines()[-1] == "Regression test  tests/rook/cx_001.test.js"
        assert fits(app)


async def test_flaky_counterexample_is_not_called_a_real_bug() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await shown(pilot, app, Events(), ("counterexample.saved", {**CX, "reproduced": "6/10", "flaky": True}))
        card = app.transcript.query_one(CounterexampleCard)
        assert "Replayed 6/10 on the real app ? flaky" in card.plain
        assert "real bug" not in card.plain


async def test_diagnosis_and_fix_cards() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        await shown(pilot, app, events,
                    ("diagnosis.ready", {"cx_id": "cx_001", "file": "src/refunds.js", "line": 42,
                                         "explanation": "Each refund is checked alone.\nTwo refunds add up.",
                                         "reviewed": True}),
                    ("fix.ready", {"cx_id": "cx_001", "files": ["src/refunds.js"], "diff": DIFF, "reviewed": False}))
        diagnosis = app.transcript.query_one(DiagnosisCard)
        assert diagnosis.plain.splitlines() == [
            "Root cause src/refunds.js : 42",
            "  Each refund is checked alone.",
            "  Two refunds add up.",
            "  reviewed by the Diagnosis Reviewer",
        ]
        fix = app.transcript.query_one(FixCard)
        lines = fix.plain.splitlines()
        assert lines[0] == "◆ Fix ready · src/refunds.js"
        assert lines[-1] == "not reviewed"
        diff = fix.lines()[1]
        assert diff.no_wrap and diff.overflow == "ellipsis"
        red = [s for s in diff.spans if str(s.style) == "#FF7A70"]
        green = [s for s in diff.spans if str(s.style) == "#62D69B"]
        assert len(red) == 1 and len(green) == 1
        assert diff.plain[red[0].start:red[0].end].startswith("-  if (amount > order.paid)")
        assert diff.plain[green[0].start:green[0].end].startswith("+  if (order.refunded + amount")
        assert fits(app)


async def test_diagnosis_without_a_line() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await shown(pilot, app, Events(), ("diagnosis.ready", {"cx_id": "cx_001", "file": "src/refunds.js",
                                                               "line": None, "explanation": "x", "reviewed": False}))
        assert app.transcript.query_one(DiagnosisCard).plain.startswith("Root cause src/refunds.js\n")


async def test_verify_block_updates_each_check_then_verifies() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()

        def step(check: str, status: str, detail: str) -> tuple[str, dict[str, Any]]:
            return "verify.step", {"cx_id": "cx_001", "check": check, "status": status, "detail": detail}

        await shown(pilot, app, events, step("replay", "running", "replaying"))
        block = app.transcript.query_one(VerifyBlock)
        assert block.plain == "  ◐ Replay: replaying"
        await shown(pilot, app, events,
                    step("replay", "passed", "second refund now rejected · refunded ₹60"),
                    step("project_tests", "passed", "12 passed"),
                    step("regression_test", "passed", "1 passed"),
                    step("fresh_search", "passed", "2,000 sequences, no violation"),
                    ("verify.done", {"cx_id": "cx_001", "verified": True, "summary": "all checks passed"}))
        assert block.plain.splitlines() == [
            "  ✓ Replay: second refund now rejected · refunded ₹60",
            "  ✓ Project tests: 12 passed",
            "  ✓ Regression test: 1 passed",
            "  ✓ Fresh search: 2,000 sequences, no violation",
            "✓ FIX VERIFIED",
        ]
        assert "bold" in str(block.lines()[-1].style)
        # a second verification round (after a new fix) starts a new block
        await shown(pilot, app, events, step("replay", "failed", "still refunds ₹110"),
                    ("verify.done", {"cx_id": "cx_001", "verified": False, "summary": "the replay still breaks"}))
        blocks = app.transcript.query(VerifyBlock)
        assert len(blocks) == 2
        assert blocks.last().plain.splitlines() == [
            "  ✗ Replay: still refunds ₹110",
            "✗ Fix not verified · the replay still breaks",
        ]


async def test_pr_and_commit_lines() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await shown(pilot, app, Events(),
                    ("fix.committed", {"cx_id": "cx_001", "branch": "rook/fix-cx_001", "commit": "1a2b3c4d5e6f",
                                       "files": ["src/refunds.js", "tests/rook/cx_001.test.js"]}),
                    ("pr.opened", {"url": "https://github.com/acme/shop/pull/88", "number": 88,
                                   "branch": "rook/fix-cx_001"}))
        committed, pr = app.transcript.query(PrLine)
        assert committed.plain == "✓ Fix committed to rook/fix-cx_001 · 1a2b3c4 · 2 files"
        assert pr.plain == "✓ PR #88 opened · https://github.com/acme/shop/pull/88"


async def test_cards_clean_terminal_controls_and_fit_80_columns() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        evil = "\x1b]0;pwned\x07\x1b[2J"
        long = "x" * 300
        await shown(pilot, app, Events(),
                    ("rules.proposed", {"rules": [{"id": "r1", "text": f"rule {evil} {long}", "kind": "state",
                                                   "check": "1 == 1", "evidence": [evil + long]}]}),
                    ("counterexample.saved", {**CX, "cx_id": f"cx_{evil}", "rule_text": evil + long,
                                              "steps": [{"action": evil, "actor": "a", "params": {"p": long}}],
                                              "observed": {"nested": {"deep": [long]}}}),
                    ("diagnosis.ready", {"cx_id": "cx_001", "file": evil, "line": 1,
                                         "explanation": f"line one {evil}\r\nline two", "reviewed": True}),
                    ("fix.ready", {"cx_id": "cx_001", "files": [evil], "diff": f"+{long}\n-{evil}\n",
                                   "reviewed": True}),
                    ("verify.step", {"cx_id": "cx_001", "check": "replay", "status": "passed", "detail": evil}),
                    ("pr.opened", {"url": f"https://x/{evil}", "number": 1, "branch": "b"}))
        cards: list[type[Card]] = [RulesCard, CounterexampleCard, DiagnosisCard, FixCard, VerifyBlock, PrLine]
        for kind in cards:
            plain = app.transcript.query_one(kind).plain
            assert "\x1b" not in plain and "\x07" not in plain and "\r" not in plain, kind
        assert "line one ]0;pwned[2J\n  line two" in app.transcript.query_one(DiagnosisCard).plain
        assert "\x1b" not in str(app.transcript.query_one(CounterexampleCard).border_title)
        assert fits(app)


def test_formatting_helpers() -> None:
    assert step_text({"action": "buy", "params": {}}) == "buy()"
    assert step_text("raw step") == "raw step"
    assert observed_text({"status": 500, "json": {"error": "x"}}) == '{"status": 500, "json": {"error": "x"}}'
    assert cx_title("cx_007") == "COUNTEREXAMPLE #007"
    assert cx_title("abc") == "COUNTEREXAMPLE abc"
    assert compact("y" * 500, 10) == "y" * 9 + "…"
    many = "\n".join(f"+{i}" for i in range(50))
    assert diff_text(many, limit=5).plain.splitlines()[-1] == "… 45 more lines"
    assert set(card_views()) == {
        "rules.proposed", "rules.reviewed", "violation.found", "shrink.step", "counterexample.saved",
        "diagnosis.ready", "fix.ready", "verify.step", "verify.done", "fix.committed", "pr.opened",
    }
