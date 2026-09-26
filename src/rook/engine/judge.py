"""The Judge: decides whether a step broke an approved rule (02_ARCHITECTURE.md section 7.2).

Every approved rule is compiled once with the safe evaluator. State rules are evaluated per entity of
their scope (the context name is the scope, e.g. `order` -> that order's fields); `global` state rules
get every read entity as a list per reader name. Response rules are evaluated when their `when`
matches the step's action and actor, with `response = {status, json}`.

A rule that fails to compile or evaluate (ExprError) is a *rule error*, never a violation.
The Judge is the only component that decides a violation and the only emitter of `violation.found`.
"""

import secrets
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

from rook.core.events import EventBus, ViolationFound
from rook.engine.executor import StepResult
from rook.model.expr import CompiledExpr, ExprError, compile_expr
from rook.model.schema import RookModel, Rule

StateSnapshot = Mapping[str, Mapping[Any, Mapping[str, Any]]]  # {reader: {id: {field: value}}}


@dataclass
class Violation:
    rule_id: str
    step_index: int
    entity: Any  # the entity id (e.g. an order_id) for a scoped state rule, else None
    observed: Any  # the entity fields, the global snapshot, or {status, json}
    expected_expr: str
    violation_id: str = field(default_factory=lambda: "v_" + secrets.token_hex(4))


@dataclass
class _Compiled:
    rule: Rule
    expr: CompiledExpr


class Judge:
    def __init__(self, model: RookModel) -> None:
        self.model = model
        self.rule_errors: dict[str, str] = {}  # rule_id -> first error message
        self._unreported: list[str] = []
        self.checks = 0
        self.rules: list[Rule] = [r for r in model.rules if r.status == "approved"]
        compiled: list[_Compiled] = []
        for rule in self.rules:
            try:
                compiled.append(_Compiled(rule, compile_expr(rule.check)))
            except ExprError as exc:
                self._error(rule, exc)
        self._scoped = [c for c in compiled if c.rule.kind == "state" and c.rule.scope != "global"]
        self._global = [c for c in compiled if c.rule.kind == "state" and c.rule.scope == "global"]
        self._response = [c for c in compiled if c.rule.kind == "response"]

    @property
    def needs_full_state(self) -> bool:
        """True if a global state rule needs every entity, not just the touched ones."""
        return bool(self._global)

    @property
    def state_scopes(self) -> set[str]:
        """The state readers that some approved state rule needs (all readers if a rule is global)."""
        if self._global:
            return {r.name for r in self.model.state}
        return {c.rule.scope for c in self._scoped}

    def pop_new_errors(self) -> list[tuple[str, str]]:
        """Rule errors not yet handed out (each rule's first error is returned once)."""
        out = [(rule_id, self.rule_errors[rule_id]) for rule_id in self._unreported]
        self._unreported.clear()
        return out

    def _error(self, rule: Rule, exc: ExprError) -> None:
        if rule.id not in self.rule_errors:
            self.rule_errors[rule.id] = f"rule {rule.id!r} ({rule.check}): {exc}"
            self._unreported.append(rule.id)

    def _holds(self, c: _Compiled, context: Mapping[str, Any]) -> bool | None:
        """True / False, or None if the rule could not be evaluated (a rule error)."""
        self.checks += 1
        try:
            return bool(c.expr.evaluate(context))
        except ExprError as exc:
            self._error(c.rule, exc)
            return None

    def check_state(
        self,
        state: StateSnapshot,
        step_index: int = 0,
        touched: Mapping[str, Collection[Any]] | None = None,
    ) -> Violation | None:
        """Evaluate state rules. Scoped rules run for each entity of their scope in `state`
        (only the ids in `touched[scope]` when `touched` is given); global rules see all of `state`.
        """
        for c in self._scoped:
            entities = state.get(c.rule.scope, {})
            ids = (
                entities.keys()
                if touched is None
                else [i for i in touched.get(c.rule.scope, ()) if i in entities]
            )
            for entity_id in ids:
                fields = entities[entity_id]
                if self._holds(c, {c.rule.scope: fields}) is False:
                    return Violation(c.rule.id, step_index, entity_id, dict(fields), c.rule.check)
        if self._global:
            context = {name: list(entities.values()) for name, entities in state.items()}
            for c in self._global:
                if self._holds(c, context) is False:
                    return Violation(c.rule.id, step_index, None, context, c.rule.check)
        return None

    def check_response(self, result: StepResult, step_index: int = 0) -> Violation | None:
        """Evaluate response rules whose `when` matches the step's action and actor.

        A step that never got an HTTP response (skipped, transport error) is not judged.
        """
        if result.status is None:
            return None
        for c in self._response:
            when = c.rule.when
            assert when is not None  # enforced by the schema for response rules
            if when.action != result.action or (when.actor is not None and when.actor != result.actor):
                continue
            response = {"status": result.status, "json": result.response_json}
            if self._holds(c, {"response": response}) is False:
                return Violation(c.rule.id, step_index, None, response, c.rule.check)
        return None

    async def publish_violation(
        self, bus: EventBus, run_id: str, violation: Violation, steps_count: int
    ) -> None:
        """Emit `violation.found` (only the Judge does this)."""
        await bus.publish(
            run_id,
            "violation.found",
            ViolationFound(
                violation_id=violation.violation_id,
                rule_id=violation.rule_id,
                steps_count=steps_count,
                observed=violation.observed,
            ),
        )
