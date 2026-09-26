"""ROOK-018: the engine's rule sanity checks (static + holds on a fresh app), in-process on minishop."""

from typing import Any

import pytest
from test_runner import BASE, ENV, MODEL, minishop

from rook.engine.inprocess import InProcessTransport
from rook.engine.sanity import SanityResult, producers, sanity_check, static_check
from rook.model.schema import Rule

RULES = {r.id: r for r in MODEL.rules}


def rule(check: str, *, kind: str = "state", scope: str = "order", **extra: Any) -> Rule:
    return Rule.model_validate({"id": "r_test", "text": "a test rule", "kind": kind, "scope": scope,
                                "check": check, "evidence": ["app.py"]} | extra)


def response_rule(check: str, action: str = "admin_export", actor: str | None = "customer") -> Rule:
    when: dict[str, Any] = {"action": action} if actor is None else {"action": action, "actor": actor}
    return rule(check, kind="response", scope="global", when=when)


async def check(rules: list[Rule], *, fixed: bool, env: dict[str, str] = ENV) -> list[SanityResult]:
    transport = InProcessTransport(minishop.create_app(fixed=fixed))
    return await sanity_check(MODEL.model_copy(update={"rules": []}), rules, BASE, env=env, transport=transport)


# --- static ---


def test_static_check_accepts_the_minishop_rules() -> None:
    for r in MODEL.rules:
        assert static_check(MODEL, r) is None, r.id


@pytest.mark.parametrize(("bad", "message"), [
    (rule("order.refunded <= "), "does not parse"),
    (rule("__import__('os')"), "does not parse"),
    (rule("order.refunded <= product.stock"), "unknown name 'product'"),
    (rule("order.refund_total <= order.paid"), "'order' has no field 'refund_total'"),
    (rule('order["nope"] == 1'), "'order' has no field 'nope'"),
    (rule("product.stock >= 0", scope="global"), "in a global rule 'product' is the list"),
    (rule("all(p.stok >= 0 for p in product)", scope="global"), "'product' has no field 'stok'"),
    (rule("order.paid >= 0", scope="orders"), "scope 'orders' is not a state reader"),
    (response_rule("response.body == 1"), "'response' has no field 'body'"),
    (response_rule("response.status == 403", action="export"), "unknown action 'export'"),
    (response_rule("response.status == 403", actor="guest"), "unknown actor 'guest'"),
    (response_rule("order.paid == 1"), "unknown name 'order'"),
])
def test_static_check_rejects_unknown_names_fields_and_bad_syntax(bad: Rule, message: str) -> None:
    problem = static_check(MODEL, bad)
    assert problem is not None and message in problem


def test_static_check_allows_comprehensions_and_response_json() -> None:
    assert static_check(MODEL, rule("all(p.stock >= 0 for p in product)", scope="global")) is None
    assert static_check(MODEL, rule("sum(o.refunded for o in order) <= sum(o.paid for o in order)",
                                    scope="global")) is None
    assert static_check(MODEL, response_rule('response.status != 200 or response.json["x"] == 1')) is None


def test_producers_are_the_creating_actions_in_dependency_order() -> None:
    assert [a.name for a in producers(MODEL, ["order_id"])] == ["create_product", "buy"]
    assert [a.name for a in producers(MODEL, ["product_id"])] == ["create_product"]


# --- fresh app ---


async def test_minishop_rules_hold_on_a_fresh_fixed_app() -> None:
    results = await check(list(MODEL.rules), fixed=True)
    assert [r.rule_id for r in results] == [r.id for r in MODEL.rules]
    assert all(r.ok and r.stage == "fresh" for r in results), results


async def test_an_expected_4xx_response_rule_is_not_rejected_for_its_status() -> None:
    [result] = await check([RULES["admin_export_forbidden"]], fixed=True)
    assert result.ok and not result.already_broken
    assert "admin_export as customer -> HTTP 403" in result.reason


async def test_a_rule_false_on_a_fresh_app_is_rejected_with_a_reason() -> None:
    [result] = await check([rule("order.refunded > 0")], fixed=True)
    assert not result.ok and result.stage == "fresh" and not result.already_broken
    assert result.reason.startswith("it is already false on a fresh app: a new order gives {")
    assert '"refunded": 0' in result.reason and "fails `order.refunded > 0`" in result.reason


async def test_a_response_rule_is_judged_by_its_check() -> None:
    # `when` without an actor uses the action's own actor. A response rule false on its first request is
    # kept but flagged: the engine cannot tell a wrong rule from a one-step bug.
    [wrong] = await check([response_rule("response.status == 201", action="buy", actor=None)], fixed=True)
    assert wrong.ok and wrong.already_broken and "buy as customer -> HTTP " in wrong.reason
    [right] = await check([response_rule("response.status < 500", action="buy", actor=None)], fixed=True)
    assert right.ok and not right.already_broken and "buy as customer -> HTTP " in right.reason


async def test_a_one_step_bug_flags_its_response_rule_as_possibly_already_broken() -> None:
    # Buggy minishop lets a customer read the admin export; a single request breaks the rule.
    results = await check(list(MODEL.rules), fixed=False)
    by_id = {r.rule_id: r for r in results}
    for i in ("refund_le_paid", "stock_non_negative", "cancelled_never_ships"):
        assert by_id[i].ok and not by_id[i].already_broken
    admin = by_id["admin_export_forbidden"]
    assert admin.ok and admin.already_broken and admin.stage == "fresh"
    assert admin.reason.startswith("it may already be broken on the first request: on a fresh app "
                                   "admin_export as customer -> HTTP 200")
    assert "fails `response.status in (401, 403)`" in admin.reason and "a human decides" in admin.reason


async def test_a_response_check_that_cannot_evaluate_is_still_rejected() -> None:
    # Only a check that evaluates to False is flagged; one that errors is rejected, never flagged.
    [result] = await check([response_rule('response.json["nope"] == 1')], fixed=False)
    assert not result.ok and not result.already_broken
    assert "fails to evaluate on a fresh app" in result.reason


async def test_global_rules_see_every_new_entity() -> None:
    ok, bad = await check([rule("all(p.stock >= 0 for p in product)", scope="global"),
                           rule("len(order) == 0", scope="global", id="no_orders")], fixed=True)
    assert ok.ok and not bad.ok and "the new entities" in bad.reason


async def test_a_check_that_cannot_evaluate_is_rejected() -> None:
    [result] = await check([rule("order.status > 5")], fixed=True)
    assert not result.ok and "fails to evaluate on a fresh app" in result.reason


async def test_a_rule_that_cannot_be_exercised_is_rejected() -> None:
    [result] = await check([rule("order.paid >= 0")], fixed=True, env={"MINISHOP_ADMIN_PASSWORD": "wrong"})
    assert not result.ok
    assert result.reason.startswith("it could not be exercised on a fresh app: create_product did not succeed")


async def test_static_failures_skip_the_app() -> None:
    results = await check([rule("order.nope == 1"), RULES["refund_le_paid"]], fixed=True)
    assert [(r.ok, r.stage) for r in results] == [(False, "static"), (True, "fresh")]


async def test_results_are_deterministic() -> None:
    rules = [*MODEL.rules, rule("order.refunded > 0")]
    assert await check(rules, fixed=True) == await check(rules, fixed=True)
