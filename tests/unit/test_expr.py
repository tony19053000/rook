import re
import time
from pathlib import Path

import pytest

import rook.model.expr as expr_module
from rook.model.expr import CompiledExpr, ExprError, compile_expr, evaluate

ORDER_OK = {"order": {"paid": 100, "refunded": 60, "refunds": [{"amount": 50}, {"amount": 10}]}}
ORDER_BAD = {"order": {"paid": 100, "refunded": 120, "refunds": [{"amount": 60}, {"amount": 60}]}}


# --- sample rules ---------------------------------------------------------------------------


def test_refund_le_paid() -> None:
    assert evaluate("order.refunded <= order.paid", ORDER_OK) is True
    assert evaluate("order.refunded <= order.paid", ORDER_BAD) is False


@pytest.mark.parametrize(("status", "expected"), [(401, True), (403, True), (200, False), (500, False)])
def test_response_status_in(status: int, expected: bool) -> None:
    assert evaluate("response.status in (401, 403)", {"response": {"status": status}}) is expected


def test_all_stock_non_negative() -> None:
    src = "all(p.stock >= 0 for p in products)"
    assert evaluate(src, {"products": [{"stock": 3}, {"stock": 0}]}) is True
    assert evaluate(src, {"products": [{"stock": 3}, {"stock": -1}]}) is False


def test_sum_refunds_le_paid() -> None:
    src = "sum(r.amount for r in order.refunds) <= order.paid"
    assert evaluate(src, ORDER_OK) is True
    assert evaluate(src, ORDER_BAD) is False


def test_compiled_expression_is_reusable() -> None:
    compiled = compile_expr("order.refunded <= order.paid")
    assert isinstance(compiled, CompiledExpr)
    assert evaluate(compiled, ORDER_OK) is True
    assert compiled.evaluate(ORDER_BAD) is False


# --- other allowed constructs ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("1 + 2 * 3 - 4", 3),
        ("7 / 2", 3.5),
        ("7 // 2", 3),
        ("7 % 4", 3),
        ("-x + +x", 0),
        ("not False", True),
        ("x > 1 and x < 10", True),
        ("x < 1 or x == 5", True),
        ("1 < x <= 5", True),
        ("x not in [1, 2]", True),
        ("missing is None", True),
        ("x is not None", True),
        ("len(items)", 3),
        ("min(items) + max(items)", 4),
        ("abs(-3)", 3),
        ("round(2.567, 1)", 2.6),
        ("any(i > 2 for i in items)", True),
        ("items[0]", 1),
        ("items[-1]", 3),
        ("obj['k']", "v"),
        ("[i * 2 for i in items if i > 1]", [4, 6]),
        ("sum([i for i in items])", 6),
        ("'a' + 'b'", "ab"),
    ],
)
def test_allowed_constructs(src: str, expected: object) -> None:
    ctx = {"x": 5, "missing": None, "items": [1, 2, 3], "obj": {"k": "v"}}
    assert evaluate(src, ctx) == expected


def test_and_or_short_circuit() -> None:
    # The right side would fail (unknown name) if it were evaluated.
    assert evaluate("False and nope", {}) is False
    assert evaluate("True or nope", {}) is True


def test_nested_comprehension_scopes() -> None:
    ctx = {"orders": [{"refunds": [1, 2]}, {"refunds": [3]}]}
    assert evaluate("sum(sum(r for r in o.refunds) for o in orders)", ctx) == 6
    assert evaluate("[[r for r in o.refunds] for o in orders]", ctx) == [[1, 2], [3]]


def test_comprehension_variable_does_not_leak() -> None:
    with pytest.raises(ExprError, match="unknown name 'p'"):
        evaluate("[p for p in items] == [] or p", {"items": [1]})


def test_comprehension_variable_shadows_context() -> None:
    assert evaluate("[x for x in items] + [x]", {"x": 9, "items": [1]}) == [1, 9]


# --- compile-time rejections ----------------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        "__import__('os')",
        "().__class__",
        "order.__dict__",
        "order._private",
        "(lambda: 1)()",
        "(x := 1)",
        "open('f')",
        "eval('1')",
        'f"{x}"',
        "round(x, ndigits=1)",
        "sum(*items)",
        "[*items]",
        "order.keys()",
        "{'a': 1}",
        "{1, 2}",
        "x if x else 1",
        "2 ** 10",
        "items[0:2]",
        "x is 1",
        "[a for a in items for b in items]",
        "[(a, b) for (a, b) in items]",
        "b'bytes'",
        "x = 1",
    ],
)
def test_rejected_at_compile_time(src: str) -> None:
    with pytest.raises(ExprError):
        compile_expr(src)


def test_rejection_messages_are_clear() -> None:
    with pytest.raises(ExprError, match="lambda"):
        compile_expr("(lambda: 1)()")
    with pytest.raises(ExprError, match="keyword"):
        compile_expr("round(1.5, ndigits=1)")
    with pytest.raises(ExprError, match="'open' is not allowed"):
        compile_expr("open('f')")
    with pytest.raises(ExprError, match="f-string"):
        compile_expr('f"{x}"')
    with pytest.raises(ExprError, match="assignment"):
        compile_expr("(x := 1)")


def test_length_cap() -> None:
    ok = "1" + " " * 499
    assert len(ok) == 500
    compile_expr(ok)
    too_long = "1" + " " * 500
    assert len(too_long) == 501
    with pytest.raises(ExprError, match="longer than 500"):
        compile_expr(too_long)


def test_nesting_cap() -> None:
    compile_expr("-" * 20 + "1")
    with pytest.raises(ExprError, match="nesting"):
        compile_expr("-" * 60 + "1")


# --- runtime guards -------------------------------------------------------------------------


def test_unknown_name() -> None:
    with pytest.raises(ExprError, match="unknown name"):
        evaluate("nope > 1", {})


def test_missing_key() -> None:
    with pytest.raises(ExprError, match="missing key 'paid'"):
        evaluate("order.paid", {"order": {}})


def test_attribute_only_on_dicts() -> None:
    with pytest.raises(ExprError, match="dict"):
        evaluate("s.upper", {"s": "abc"})


@pytest.mark.parametrize("src", ["1 / 0", "1 // 0", "1 % 0", "1.0 / zero"])
def test_division_by_zero(src: str) -> None:
    with pytest.raises(ExprError, match="division by zero"):
        evaluate(src, {"zero": 0.0})


def test_iteration_cap() -> None:
    assert evaluate("sum(i for i in items)", {"items": [1] * 10_000}) == 10_000
    with pytest.raises(ExprError, match="10000"):
        evaluate("sum(i for i in items)", {"items": [1] * 10_001})


def test_repeat_size_cap() -> None:
    with pytest.raises(ExprError):
        evaluate("[0] * 100000000", {})


def test_only_lists_are_iterable() -> None:
    with pytest.raises(ExprError, match="iterate"):
        evaluate("all(c for c in s)", {"s": "abc"})


def test_type_errors_become_expr_errors() -> None:
    with pytest.raises(ExprError):
        evaluate("x + 'a'", {"x": 1})
    with pytest.raises(ExprError):
        evaluate("len(x)", {"x": 1})


def test_bad_subscripts() -> None:
    with pytest.raises(ExprError, match="out of range"):
        evaluate("items[5]", {"items": [1]})
    with pytest.raises(ExprError, match="integer"):
        evaluate("items['a']", {"items": [1]})
    with pytest.raises(ExprError):
        evaluate("obj['__class__']", {"obj": {}})


def test_syntax_error() -> None:
    with pytest.raises(ExprError, match="syntax"):
        compile_expr("order.paid <=")


# --- the evaluator never runs Python code ---------------------------------------------------


def test_module_never_uses_eval_or_exec() -> None:
    source = Path(expr_module.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\beval\s*\(", source)
    assert not re.search(r"\bexec\s*\(", source)
    assert not re.search(r"\bcompile\s*\(", source)
    assert "__import__" not in source


# --- cumulative work budget -----------------------------------------------------------------

ITEMS_10K = {"items": list(range(10_000))}


@pytest.mark.parametrize(
    "src",
    [
        "sum(sum(x for x in items) for y in items)",
        "sum(sum(sum(x for x in items) for y in items) for z in items)",
        "[[x for x in items] for y in items]",
        "all(len(items) > 0 for y in items)",
        "any(y in items and False for y in items)",
    ],
)
def test_nested_work_is_bounded(src: str) -> None:
    start = time.perf_counter()
    with pytest.raises(ExprError, match="work budget"):
        evaluate(src, ITEMS_10K)
    assert time.perf_counter() - start < 1.0


def test_work_budget_resets_per_evaluation() -> None:
    compiled = compile_expr("sum(x for x in items) > 0")
    for _ in range(20):
        assert compiled.evaluate(ITEMS_10K) is True


def test_small_nested_comprehension_within_budget() -> None:
    ctx = {"items": list(range(100))}
    assert evaluate("sum(sum(x for x in items) for y in items)", ctx) == 4950 * 100
