"""Safe expression evaluator for rule checks (02_ARCHITECTURE.md, section 6.1).

Rules come from Bob, so they are untrusted. An expression is parsed into an AST,
checked against a node whitelist, and then walked by a small interpreter in this
module. Python's own code execution is never used.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

MAX_SOURCE_LENGTH = 500
MAX_DEPTH = 50
MAX_ITERATIONS = 10_000  # elements in one comprehension or one repeated sequence
# Total work units per evaluation, across all nesting levels: one per comprehension
# item, plus the length of every sequence handed to a function, compared, searched
# with `in`, concatenated or built by `*`. Stops nested loops from multiplying.
MAX_TOTAL_WORK = 100_000


class ExprError(Exception):
    """Raised when an expression is rejected or fails to evaluate."""


_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "sum": sum,
    "len": len,
    "min": min,
    "max": max,
    "abs": abs,
    "all": all,
    "any": any,
    "round": round,
}

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Tuple,
    ast.List,
    ast.Attribute,
    ast.Subscript,
    ast.Call,
    ast.GeneratorExp,
    ast.ListComp,
    ast.comprehension,
    # operator / context marker nodes
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Load,
    ast.Store,
    *_BIN_OPS,
    *_CMP_OPS,
)

# Friendly names for common forbidden constructs.
_FORBIDDEN_NAMES: dict[type[ast.AST], str] = {
    ast.Lambda: "lambda",
    ast.NamedExpr: "assignment expression (:=)",
    ast.Starred: "starred argument",
    ast.JoinedStr: "f-string",
    ast.FormattedValue: "f-string",
    ast.Dict: "dict display",
    ast.Set: "set display",
    ast.DictComp: "dict comprehension",
    ast.SetComp: "set comprehension",
    ast.IfExp: "conditional expression",
    ast.Await: "await",
    ast.Yield: "yield",
    ast.YieldFrom: "yield",
    ast.Slice: "slice",
    ast.Pow: "operator **",
}


def _is_private(name: str) -> bool:
    return name.startswith("_")


class _Validator(ast.NodeVisitor):
    def generic_visit(self, node: ast.AST) -> None:
        if not isinstance(node, _ALLOWED_NODES):
            label = _FORBIDDEN_NAMES.get(type(node), type(node).__name__)
            raise ExprError(f"{label} is not allowed in rule expressions")
        super().generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if node.value is not None and not isinstance(node.value, (bool, int, float, str)):
            raise ExprError(f"constant of type {type(node.value).__name__} is not allowed")

    def visit_Name(self, node: ast.Name) -> None:
        if _is_private(node.id):
            raise ExprError(f"name {node.id!r} is not allowed (names may not start with '_')")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_private(node.attr):
            raise ExprError(f"attribute {node.attr!r} is not allowed (no '_'-prefixed or dunder names)")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, right in zip(node.ops, node.comparators, strict=True):
            if isinstance(op, (ast.Is, ast.IsNot)) and not (
                isinstance(right, ast.Constant) and right.value is None
            ):
                raise ExprError("'is' / 'is not' may only compare against None")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            self.visit(node.func)  # reports lambdas, dunders etc. by name first
            raise ExprError("only direct calls to allowed functions are permitted (no method calls)")
        if node.func.id not in _FUNCTIONS:
            allowed = ", ".join(sorted(_FUNCTIONS))
            raise ExprError(f"call to {node.func.id!r} is not allowed (allowed: {allowed})")
        if node.keywords:
            raise ExprError("keyword arguments are not allowed")
        for arg in node.args:
            self.visit(arg)

    def _visit_comprehension(self, node: ast.GeneratorExp | ast.ListComp) -> None:
        if len(node.generators) != 1:
            raise ExprError("comprehensions may have exactly one 'for'")
        gen = node.generators[0]
        if gen.is_async:
            raise ExprError("async comprehensions are not allowed")
        if not isinstance(gen.target, ast.Name):
            raise ExprError("comprehension target must be a single name")
        if len(gen.ifs) > 1:
            raise ExprError("comprehensions may have at most one 'if'")
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)


def _depth(node: ast.AST, level: int = 1) -> int:
    if level > MAX_DEPTH:
        raise ExprError(f"expression nesting is deeper than {MAX_DEPTH}")
    children = list(ast.iter_child_nodes(node))
    return max((_depth(child, level + 1) for child in children), default=level)


@dataclass(frozen=True)
class CompiledExpr:
    """A parsed and validated expression, ready for repeated evaluation."""

    source: str
    tree: ast.Expression

    def evaluate(self, context: Mapping[str, Any]) -> Any:
        return _Interpreter(context).run(self.tree.body)


def compile_expr(src: str) -> CompiledExpr:
    """Parse and validate `src`. Raises ExprError if it is not a safe expression."""
    if not isinstance(src, str):
        raise ExprError("expression must be a string")
    if len(src) > MAX_SOURCE_LENGTH:
        raise ExprError(f"expression is longer than {MAX_SOURCE_LENGTH} characters")
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ExprError(f"invalid expression syntax: {exc}") from None
    _depth(tree)
    _Validator().visit(tree)
    return CompiledExpr(source=src, tree=tree)


def evaluate(src_or_compiled: str | CompiledExpr, context: Mapping[str, Any]) -> Any:
    """Evaluate a rule expression against `context` (entity dicts, `response`, `global`)."""
    compiled = src_or_compiled if isinstance(src_or_compiled, CompiledExpr) else compile_expr(src_or_compiled)
    return compiled.evaluate(context)


class _Interpreter:
    def __init__(self, context: Mapping[str, Any]) -> None:
        self._context = context
        self._scopes: list[dict[str, Any]] = []
        self._work = 0

    def _spend(self, units: int) -> None:
        self._work += units
        if self._work > MAX_TOTAL_WORK:
            raise ExprError(f"expression exceeds the work budget of {MAX_TOTAL_WORK} steps")

    def run(self, node: ast.expr) -> Any:
        try:
            result = self._eval(node)
            # Never hand a lazy generator back to the caller.
            return list(result) if isinstance(result, Iterator) else result
        except ExprError:
            raise
        except (TypeError, ValueError, OverflowError, ArithmeticError, RecursionError) as exc:
            raise ExprError(f"evaluation failed: {exc}") from None

    def _eval(self, node: ast.expr) -> Any:
        method = getattr(self, f"_eval_{type(node).__name__}", None)
        if method is None:  # unreachable after validation, kept as a hard stop
            raise ExprError(f"{type(node).__name__} is not allowed")
        return method(node)

    def _eval_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def _eval_Name(self, node: ast.Name) -> Any:
        for scope in reversed(self._scopes):
            if node.id in scope:
                return scope[node.id]
        if node.id in self._context:
            return self._context[node.id]
        raise ExprError(f"unknown name {node.id!r}")

    def _eval_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self._eval(elt) for elt in node.elts)

    def _eval_List(self, node: ast.List) -> list[Any]:
        return [self._eval(elt) for elt in node.elts]

    def _eval_BoolOp(self, node: ast.BoolOp) -> Any:
        is_and = isinstance(node.op, ast.And)
        result: Any = None
        for value in node.values:
            result = self._eval(value)
            if is_and and not result:
                return result
            if not is_and and result:
                return result
        return result

    def _eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self._eval(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        return +operand

    def _eval_BinOp(self, node: ast.BinOp) -> Any:
        left = self._eval(node.left)
        right = self._eval(node.right)
        op_type = type(node.op)
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and isinstance(right, (int, float)) and right == 0:
            raise ExprError("division by zero")
        if op_type is ast.Mult:
            self._spend(_check_repeat_size(left, right))
        elif op_type is ast.Add:
            self._spend(_seq_len(left) + _seq_len(right))
        return _BIN_OPS[op_type](left, right)

    def _eval_Compare(self, node: ast.Compare) -> bool:
        left = self._eval(node.left)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = self._eval(comparator)
            self._spend(_seq_len(left) + _seq_len(right))
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True

    def _eval_Attribute(self, node: ast.Attribute) -> Any:
        value = self._eval(node.value)
        if not isinstance(value, Mapping):
            raise ExprError(f"attribute {node.attr!r} can only be read from an object (dict)")
        if node.attr not in value:
            raise ExprError(f"missing key {node.attr!r}")
        return value[node.attr]

    def _eval_Subscript(self, node: ast.Subscript) -> Any:
        value = self._eval(node.value)
        key = self._eval(node.slice)
        if isinstance(value, Mapping):
            if not isinstance(key, str) or _is_private(key):
                raise ExprError("object keys must be strings not starting with '_'")
            if key not in value:
                raise ExprError(f"missing key {key!r}")
            return value[key]
        if isinstance(value, (list, tuple, str)):
            if isinstance(key, bool) or not isinstance(key, int):
                raise ExprError("list index must be an integer")
            if not -len(value) <= key < len(value):
                raise ExprError(f"index {key} out of range")
            return value[key]
        raise ExprError(f"cannot index a value of type {type(value).__name__}")

    def _eval_Call(self, node: ast.Call) -> Any:
        assert isinstance(node.func, ast.Name)  # guaranteed by the validator
        func = _FUNCTIONS[node.func.id]
        args = [self._eval(arg) for arg in node.args]
        self._spend(sum(_seq_len(arg) for arg in args))
        return func(*args)

    def _eval_GeneratorExp(self, node: ast.GeneratorExp) -> Iterator[Any]:
        return self._comprehend(node.generators[0], node.elt)

    def _eval_ListComp(self, node: ast.ListComp) -> list[Any]:
        return list(self._comprehend(node.generators[0], node.elt))

    def _comprehend(self, gen: ast.comprehension, elt: ast.expr) -> Iterator[Any]:
        iterable = self._eval(gen.iter)
        if not isinstance(iterable, (list, tuple)):
            raise ExprError(f"can only iterate over a list, not {type(iterable).__name__}")
        if len(iterable) > MAX_ITERATIONS:
            raise ExprError(f"iteration over more than {MAX_ITERATIONS} elements")
        assert isinstance(gen.target, ast.Name)  # guaranteed by the validator
        name = gen.target.id
        cond = gen.ifs[0] if gen.ifs else None
        enclosing = list(self._scopes)

        # Lazy so all()/any() short-circuit; each item runs in its own scope on top of
        # the scopes that were active when the comprehension was created.
        def items() -> Iterator[Any]:
            for item in iterable:
                self._spend(1)
                saved = self._scopes
                self._scopes = [*enclosing, {name: item}]
                try:
                    keep = cond is None or self._eval(cond)
                    value = self._eval(elt) if keep else None
                finally:
                    self._scopes = saved
                if keep:
                    yield value

        return items()


def _seq_len(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple, str, Mapping)) else 0


def _check_repeat_size(left: Any, right: Any) -> int:
    """Block `[0] * 10**9`-style memory blow-ups; returns the result size."""
    for seq, count in ((left, right), (right, left)):
        if isinstance(seq, (list, tuple, str)) and isinstance(count, int):
            size = len(seq) * max(count, 0)
            if size > MAX_ITERATIONS:
                raise ExprError(f"repeated sequence would exceed {MAX_ITERATIONS} elements")
            return size
    return 0
