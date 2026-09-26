"""ROOK-008: the Judge (02 section 7.2). Pure unit tests; the minishop search is in test_runner.py."""

import re
from pathlib import Path

from rook.core.events import EventBus
from rook.engine.executor import StepResult
from rook.engine.judge import Judge, Violation
from rook.model.loader import load_model, load_model_str
from rook.model.schema import RookModel

SRC = Path(__file__).parents[2] / "src" / "rook"
MODEL = load_model(Path(__file__).parents[1] / "fixtures" / "minishop" / "rook.yaml")


def _with_rules(*rules: dict) -> RookModel:
    return MODEL.model_copy(update={"rules": [MODEL.rules[0].model_validate(r) for r in rules]})


def _result(action: str, actor: str, status: int | None, json: object = None) -> StepResult:
    return StepResult(action, actor, {}, {}, {}, status=status, response_json=json)


def test_only_approved_rules_are_judged() -> None:
    judge = Judge(MODEL)
    assert {r.id for r in judge.rules} == {r.id for r in MODEL.rules if r.status == "approved"}
    proposed = MODEL.model_copy(
        update={"rules": [r.model_copy(update={"status": "proposed"}) for r in MODEL.rules]}
    )
    assert Judge(proposed).rules == []
    assert Judge(proposed).check_state({"order": {1: {"paid": 1, "refunded": 9}}}) is None


def test_scoped_state_rule_reports_entity_and_observed() -> None:
    judge = Judge(MODEL)
    state = {
        "order": {
            7: {"paid": 100, "refunded": 60, "status": "paid", "shipped": False},
            8: {"paid": 100, "refunded": 110, "status": "paid", "shipped": False},
        }
    }
    v = judge.check_state(state, step_index=3)
    assert isinstance(v, Violation)
    assert (v.rule_id, v.step_index, v.entity) == ("refund_le_paid", 3, 8)
    assert v.observed == state["order"][8] and v.expected_expr == "order.refunded <= order.paid"
    assert v.violation_id.startswith("v_")


def test_touched_limits_which_entities_are_judged() -> None:
    judge = Judge(MODEL)
    state = {
        "order": {
            7: {"paid": 100, "refunded": 0, "status": "paid", "shipped": False},
            8: {"paid": 100, "refunded": 110, "status": "paid", "shipped": False},
        }
    }
    assert judge.check_state(state, touched={"order": [7]}) is None
    assert judge.check_state(state, touched={"order": [8]}).entity == 8  # type: ignore[union-attr]
    assert judge.check_state(state, touched={"order": [99]}) is None  # not read: nothing to judge
    assert judge.check_state(state, touched={}) is None


def test_other_scopes_and_holding_rules() -> None:
    judge = Judge(MODEL)
    assert judge.check_state({"product": {1: {"stock": 0}}}) is None
    v = judge.check_state({"product": {1: {"stock": -1}}})
    assert v is not None and v.rule_id == "stock_non_negative" and v.observed == {"stock": -1}
    v = judge.check_state({"order": {2: {"paid": 5, "refunded": 0, "status": "cancelled", "shipped": True}}})
    assert v is not None and v.rule_id == "cancelled_never_ships"


def test_response_rule_matches_action_and_actor() -> None:
    judge = Judge(MODEL)
    v = judge.check_response(_result("admin_export", "customer", 200, []), step_index=0)
    assert v is not None and v.rule_id == "admin_export_forbidden"
    assert v.observed == {"status": 200, "json": []} and v.entity is None
    assert judge.check_response(_result("admin_export", "customer", 403)) is None
    assert judge.check_response(_result("admin_export", "admin", 200)) is None  # other actor
    assert judge.check_response(_result("buy", "customer", 200)) is None  # other action
    # No HTTP response (transport error, skipped): nothing to judge.
    assert judge.check_response(_result("admin_export", "customer", None)) is None


def test_response_rule_without_actor_matches_any_actor() -> None:
    model = _with_rules(
        {
            "id": "no_5xx",
            "text": "t",
            "kind": "response",
            "when": {"action": "buy"},
            "check": "response.status < 500",
            "status": "approved",
        }
    )
    judge = Judge(model)
    assert judge.check_response(_result("buy", "admin", 500)) is not None
    assert judge.check_response(_result("buy", "customer", 500)) is not None
    assert judge.check_response(_result("buy", "customer", 409)) is None


def test_global_rules_see_all_entities_as_lists() -> None:
    model = _with_rules(
        {
            "id": "total",
            "text": "t",
            "kind": "state",
            "scope": "global",
            "check": "sum(o.refunded for o in order) <= sum(o.paid for o in order)",
            "status": "approved",
        }
    )
    judge = Judge(model)
    assert judge.needs_full_state and judge.state_scopes == {"order", "product"}
    ok = {"order": {1: {"paid": 10, "refunded": 5}, 2: {"paid": 10, "refunded": 10}}}
    assert judge.check_state(ok) is None
    bad = {"order": {1: {"paid": 10, "refunded": 5}, 2: {"paid": 10, "refunded": 16}}}
    v = judge.check_state(bad, step_index=1)
    assert v is not None and v.rule_id == "total" and v.entity is None
    assert v.observed == {"order": [{"paid": 10, "refunded": 5}, {"paid": 10, "refunded": 16}]}


def test_state_scopes_without_global_rules() -> None:
    judge = Judge(MODEL)
    assert not judge.needs_full_state
    assert judge.state_scopes == {"order", "product"}


def test_rule_errors_are_never_violations() -> None:
    model = _with_rules(
        {
            "id": "syntax",
            "text": "t",
            "kind": "state",
            "scope": "order",
            "check": "order.paid >=",
            "status": "approved",
        },
        {
            "id": "missing",
            "text": "t",
            "kind": "state",
            "scope": "order",
            "check": "order.nope > 0",
            "status": "approved",
        },
        {
            "id": "call",
            "text": "t",
            "kind": "state",
            "scope": "order",
            "check": "__import__('os').system('x')",
            "status": "approved",
        },
    )
    judge = Judge(model)
    assert judge.check_state({"order": {1: {"paid": 1, "refunded": 0}}}) is None
    errors = dict(judge.pop_new_errors())
    assert set(errors) == {"syntax", "missing", "call"}
    assert judge.pop_new_errors() == []  # each rule's first error is handed out once
    judge.check_state({"order": {2: {"paid": 1, "refunded": 0}}})
    assert judge.pop_new_errors() == []
    assert set(judge.rule_errors) == {"syntax", "missing", "call"}


def test_mixed_error_and_real_violation() -> None:
    model = _with_rules(
        {
            "id": "broken_rule",
            "text": "t",
            "kind": "state",
            "scope": "order",
            "check": "order.nope > 0",
            "status": "approved",
        },
        {
            "id": "refund_le_paid",
            "text": "t",
            "kind": "state",
            "scope": "order",
            "check": "order.refunded <= order.paid",
            "status": "approved",
        },
    )
    v = Judge(model).check_state({"order": {1: {"paid": 1, "refunded": 5}}})
    assert v is not None and v.rule_id == "refund_le_paid"


async def test_publish_violation_emits_violation_found() -> None:
    bus = EventBus()
    judge = Judge(MODEL)
    v = judge.check_state({"order": {8: {"paid": 100, "refunded": 110, "status": "paid", "shipped": False}}})
    assert v is not None
    await judge.publish_violation(bus, "r_1", v, steps_count=4)
    await bus.close("r_1")
    events = [e async for e in bus.subscribe("r_1")]
    assert [e.type for e in events] == ["violation.found"]
    assert events[0].data == {
        "violation_id": v.violation_id,
        "rule_id": "refund_le_paid",
        "steps_count": 4,
        "observed": {"paid": 100, "refunded": 110, "status": "paid", "shipped": False},
    }


def test_judge_is_the_only_emitter_of_violation_found() -> None:
    # Building a ViolationFound payload or publishing "violation.found" happens only in the Judge
    # (core/events.py declares the model; other modules may read the event but never publish it).
    emits = re.compile(r"(?<!class )ViolationFound\(|publish\([^)]*[\"']violation\.found[\"']", re.DOTALL)
    emitters = sorted(str(p.relative_to(SRC)) for p in SRC.rglob("*.py") if emits.search(p.read_text()))
    assert emitters == ["engine/judge.py"]


def test_engine_never_uses_eval_or_exec() -> None:
    for name in ("generator.py", "judge.py", "runner.py", "executor.py", "inprocess.py"):
        text = (SRC / "engine" / name).read_text()
        assert not re.search(r"(?<![\w.])(eval|exec)\s*\(", text), name


def test_minimal_model_from_string() -> None:
    model = load_model_str(
        """
version: 1
actors: [{name: u}]
actions:
  - {name: ping, actor: u, request: {method: GET, path: /ping}}
rules:
  - {id: ok, text: t, kind: response, when: {action: ping}, check: "response.status == 200", status: approved}
"""
    )
    judge = Judge(model)
    assert judge.state_scopes == set() and not judge.needs_full_state
    assert judge.check_response(_result("ping", "u", 200)) is None
    assert judge.check_response(_result("ping", "u", 404)) is not None
