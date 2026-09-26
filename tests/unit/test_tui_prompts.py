"""Pilot tests for the question prompts (ROOK-027): each question kind answered through the keyboard."""

from __future__ import annotations

from typing import Any

import pytest
from textual.widget import Widget
from textual.widgets import Input, Static
from tui_question_samples import (
    RULES,
    SIZE,
    VERDICTS,
    Events,
    FakeBackend,
    approve_rules_question,
    booted,
    fix_question,
    make_app,
    menu_question,
    pr_question,
    setup_question,
)

from rook.cli.tui.app import RookApp
from rook.cli.tui.render import default_view
from rook.cli.tui.widgets.cards import RulesCard
from rook.cli.tui.widgets.prompts import (
    ConfirmPrompt,
    MenuPrompt,
    QuestionPrompt,
    RulesPrompt,
    ValuePrompt,
    describe_answer,
    prompt_views,
)
from rook.core.events import QuestionOption


def texts(app: RookApp) -> str:
    """Everything drawn in the transcript (cards and prompts by their plain text, lines by their content)."""
    out: list[str] = []
    for widget in app.transcript.children:
        plain = getattr(widget, "plain", None)
        if isinstance(plain, str):
            out.append(plain)
        elif isinstance(widget, Static):
            out.append(str(widget.render()))
    out += [box.value for box in app.transcript.query(Input)]
    return "\n".join(out)


def fits(app: RookApp) -> bool:
    return app.transcript.max_scroll_x == 0 and all(
        w.region.right <= SIZE[0] for w in app.transcript.walk_children(Widget) if w.display
    )


async def ask(pilot: Any, app: RookApp, data: dict[str, Any], events: Events | None = None) -> QuestionPrompt:
    app.show_event((events or Events())("question.asked", data))
    await pilot.pause()
    return app.transcript.query(QuestionPrompt).last()


# --- menu ------------------------------------------------------------------------------------------------------


async def test_menu_moves_with_arrows_and_answers_with_enter() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, menu_question())
        assert isinstance(prompt, MenuPrompt)
        assert app.focused is prompt and app.active_question == "q_menu"
        assert "❯ Search longer" in prompt.plain
        await pilot.press("down")
        assert "❯ Write the report" in prompt.plain
        await pilot.press("up", "up")
        assert "❯ Stop" in prompt.plain  # wraps around
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q_menu", "report")]
        assert prompt.state == "answered"
        assert prompt.plain.splitlines()[-1] == "  ✓ Write the report"
        assert "❯" not in prompt.plain
        assert app.active_question is None
        assert app.focused is app.prompt
        assert fits(app)


async def test_menu_number_key_picks_an_option() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        await ask(pilot, app, menu_question())
        await pilot.press("3")
        await pilot.pause()
        assert backend.calls == [("answer", "q_menu", "stop")]


async def test_repo_question_is_a_menu() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, {"question_id": "q_repo", "kind": "repo", "text": "Which repo?",
                                        "options": [{"id": "acme/shop", "label": "acme/shop · private"},
                                                    {"id": "demo/minishop", "label": "demo/minishop · demo"}]})
        assert isinstance(prompt, MenuPrompt)
        await pilot.press("down", "enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q_repo", "demo/minishop")]
        assert "✓ demo/minishop · demo" in prompt.plain


# --- confirm ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("keys", "answer", "shown"), [
    (("y",), "yes", "✓ Fix it"),
    (("enter",), "yes", "✓ Fix it"),
    (("n",), "no", "✓ Not now"),
])
async def test_fix_confirm_sends_the_option_id(keys: tuple[str, ...], answer: str, shown: str) -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, fix_question())
        assert isinstance(prompt, ConfirmPrompt)
        assert prompt.plain == "? Fix cx_001 in src/refunds.js:42? (Y = Fix it / n = Not now)"
        await pilot.press(*keys)
        await pilot.pause()
        assert backend.calls == [("answer", "q_fix", answer)]
        assert prompt.plain.endswith(shown)
        assert app.focused is app.prompt


async def test_pr_confirm_and_a_second_key_does_not_answer_twice() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, pr_question())
        prompt.focus()
        await pilot.press("y")
        prompt.focus()  # even if it got the focus back somehow, a closed prompt stays closed
        await pilot.press("n")
        await pilot.pause()
        assert backend.calls == [("answer", "q_pr", "yes")]
        assert prompt.plain.endswith("✓ Ship it")
        assert fits(app)


# --- setup value -----------------------------------------------------------------------------------------------


async def test_setup_value_is_masked_sent_once_and_never_drawn() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    secret = "fakekey123"
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, setup_question())
        assert isinstance(prompt, ValuePrompt)
        box = prompt.query_one(Input)
        assert box.password is True
        assert app.focused is box
        await pilot.press("enter")  # an empty value is not an answer
        await pilot.pause()
        assert backend.calls == []
        await pilot.press(*secret)
        assert secret not in str(box.render())
        await pilot.press("enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q_setup", secret)]
        assert prompt.state == "answered"
        assert not prompt.query(Input)
        body = texts(app)
        assert secret not in body
        assert "✓ PAYMENT_API_KEY provided" in body
        assert app.prompt.value == ""
        assert app.focused is app.prompt
        assert app.history.previous("") is None  # not stored in the input history either
        # the run then publishes a redacted answer; the prompt stays as it is
        app.show_event(Events()("question.answered", {"question_id": "q_setup",
                                                      "answer": {"name": "PAYMENT_API_KEY", "provided": True},
                                                      "by": "user"}))
        await pilot.pause()
        assert texts(app).count("PAYMENT_API_KEY provided") == 1
        assert fits(app)


async def test_setup_value_not_marked_secret_is_shown() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, setup_question(secret=False))
        box = prompt.query_one(Input)
        assert box.password is False
        await pilot.press(*"3000")
        await pilot.press("enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q_setup", "3000")]
        assert "✓ 3000" in prompt.plain


# --- approve rules ---------------------------------------------------------------------------------------------


async def rules_prompt(pilot: Any, app: RookApp) -> tuple[RulesPrompt, RulesCard]:
    events = Events()
    app.show_event(events("rules.proposed", {"rules": RULES}))
    app.show_event(events("rules.reviewed", {"verdicts": VERDICTS}))
    prompt = await ask(pilot, app, approve_rules_question(), events)
    assert isinstance(prompt, RulesPrompt)
    return prompt, prompt.card


async def test_already_broken_rule_is_not_preselected_and_yes_sends_the_explicit_list() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt, card = await rules_prompt(pilot, app)
        assert len(app.transcript.query(RulesCard)) == 1  # the question drives the existing card
        assert card.selected_ids == ["refund_le_paid"]
        assert prompt.has_focus
        lines = card.plain.splitlines()
        assert lines[1] == " ❯[x] 1  Refunds never exceed the amount paid"
        assert lines[3] == "  [ ] 2  An order total is never negative"
        assert "? possibly already broken · needs your explicit OK" in card.plain
        assert prompt.plain.startswith("? Approve these 1 rules?")
        await pilot.press("y")
        await pilot.pause()
        assert backend.calls == [("answer", "q_rules", ["refund_le_paid"])]
        assert prompt.plain == "  ✓ Approved 1 rules"
        assert card.plain.splitlines()[1] == " ✓ 1  Refunds never exceed the amount paid"
        assert card.plain.splitlines()[3] == " · 2  An order total is never negative"
        assert app.focused is app.prompt
        assert fits(app)


async def test_flagged_rule_needs_an_explicit_toggle() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt, card = await rules_prompt(pilot, app)
        await pilot.press("down", "space")  # the cursor moves to the flagged rule and ticks it
        assert card.selected_ids == ["refund_le_paid", "total_positive"]
        assert prompt.plain.startswith("? Approve these 2 rules?")
        await pilot.press("3")  # the engine-rejected rule can't be ticked
        assert card.selected_ids == ["refund_le_paid", "total_positive"]
        await pilot.press("1")
        assert card.selected_ids == ["total_positive"]
        await pilot.press("enter")
        await pilot.pause()
        assert backend.calls == [("answer", "q_rules", ["total_positive"])]


async def test_rules_n_rejects_all_and_an_empty_selection_is_none() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt, _ = await rules_prompt(pilot, app)
        await pilot.press("n")
        await pilot.pause()
        assert backend.calls == [("answer", "q_rules", "none")]
        assert prompt.plain == "  ✓ Rejected all rules"

    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt, card = await rules_prompt(pilot, app)
        await pilot.press("space")
        assert card.selected_ids == []
        assert prompt.plain.startswith("? Approve no rules (reject all)?")
        await pilot.press("y")
        await pilot.pause()
        assert backend.calls == [("answer", "q_rules", "none")]


async def test_rules_question_without_an_earlier_card_builds_one_from_the_payload() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, approve_rules_question())
        assert isinstance(prompt, RulesPrompt)
        assert [r.id for r in prompt.card.rows] == ["refund_le_paid", "total_positive", "stock_nonneg"]
        assert prompt.card.selected_ids == ["refund_le_paid"]


async def test_auto_answer_collapses_rules_and_never_selects_the_flagged_rule() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        prompt, card = await rules_prompt(pilot, app)
        app.show_event(events("question.answered", {"question_id": "q_rules", "answer": ["refund_le_paid"],
                                                    "by": "auto"}))
        await pilot.pause()
        assert prompt.state == "answered" and prompt.by == "auto"
        assert prompt.plain == "  ✓ Approve refund_le_paid (auto)"
        assert [r.approved for r in card.rows] == [True, False, False]
        await pilot.press("y")
        await pilot.pause()
        assert backend.calls == []


# --- lifecycle -------------------------------------------------------------------------------------------------


async def test_escape_cancels_the_question_without_answering() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        prompt = await ask(pilot, app, fix_question())
        await pilot.press("escape")
        await pilot.pause()
        assert prompt.state == "cancelled"
        assert prompt.plain.endswith("· Question cancelled")
        assert app.active_question is None
        assert backend.calls == []
        assert app.focused is app.prompt

        value = await ask(pilot, app, setup_question("q2"))
        await pilot.press(*"abc", "escape")
        await pilot.pause()
        assert value.state == "cancelled" and not value.query(Input)
        assert backend.calls == []


async def test_auto_answer_collapses_a_confirm_prompt() -> None:
    backend = FakeBackend()
    app = make_app(backend)
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        events = Events()
        prompt = await ask(pilot, app, fix_question(), events)
        app.show_event(events("question.answered", {"question_id": "q_fix", "answer": "yes", "by": "auto"}))
        await pilot.pause()
        assert prompt.plain.endswith("✓ Fix it (auto)")
        assert app.active_question is None
        assert app.focused is app.prompt


async def test_an_answer_without_its_prompt_is_a_plain_line() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        app.show_event(Events()("question.answered", {"question_id": "q_old", "answer": True, "by": "user"}))
        await pilot.pause()
        assert "  ✓ Yes" in texts(app)


async def test_question_text_is_cleaned_of_terminal_controls() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        data = {**menu_question(), "text": "Pick\x1b]0;pwned\x07 one\nnow",
                "options": [{"id": "a", "label": "A\x1b[31m red"}, {"id": "b", "label": "B"}]}
        prompt = await ask(pilot, app, data)
        assert "\x1b" not in prompt.plain and "\x07" not in prompt.plain
        assert prompt.plain.splitlines()[0].startswith("? Pick]0;pwned one now")
        assert "❯ A[31m red" in prompt.plain


async def test_long_question_and_options_fit_in_80_columns() -> None:
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await booted(pilot, app)
        long = "word " * 60
        await ask(pilot, app, {**menu_question(), "text": long,
                               "options": [{"id": "x", "label": long}, {"id": "y", "label": "y"}]})
        await ask(pilot, app, {**fix_question("q2"), "text": long})
        assert fits(app)


def test_views_and_answer_descriptions() -> None:
    assert set(prompt_views()) == {"question.asked", "question.answered"}
    options = [QuestionOption(id="yes", label="Fix it")]
    assert describe_answer("yes", options) == "Fix it"
    assert describe_answer(False, []) == "No"
    assert describe_answer(["r1", "r2"], []) == "Approve r1, r2"
    assert describe_answer([], []) == "Reject all"
    assert describe_answer({"name": "KEY", "provided": False}, []) == "KEY not provided"
    assert describe_answer({"x": 1}, []) == '{"x": 1}'


def test_register_replaces_only_the_question_and_card_views() -> None:
    app = make_app()
    assert app.views["question.asked"] is not default_view
    assert app.views["rules.proposed"] is not default_view
    assert app.views["agent.started"] is default_view
    assert app.views["log"] is default_view
