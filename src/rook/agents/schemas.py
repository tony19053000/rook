"""Pydantic output models for the 12 Bob agents (docs/02_ARCHITECTURE.md §5.3).

Every agent ends its reply with one ```json block that must validate against its model here; BobClient
re-prompts with the validation error otherwise. Models are strict (`extra="forbid"`) so a reply cannot
smuggle in extra instructions or fields. Each model carries one example (`example_for`), used by the tests
and shown to the agent in its prompt.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rook.core.events import RepoSummary
from rook.model.schema import Action, Actor, Rule, SequenceStep, StateReader, _duplicates

__all__ = [
    "CoordinatorDecision",
    "Diagnosis",
    "FixReviewOutput",
    "GuideAnswer",
    "LawmakerOutput",
    "MapperOutput",
    "RepoSummary",
    "ReviewVerdict",
    "RuleCriticOutput",
    "RuleVerdict",
    "SandboxPlan",
    "Scenario",
    "StrategistOutput",
    "SurgeonOutput",
    "TestDesignerOutput",
    "example_for",
]


def _config(example: dict[str, Any]) -> ConfigDict:
    return ConfigDict(extra="forbid", json_schema_extra={"examples": [example]})


# RepoSummary lives in core/events.py (it is also an event payload), so its example is kept here.
_REPO_SUMMARY_EXAMPLE: dict[str, Any] = {
    "language": "python",
    "framework": "fastapi",
    "entrypoints": ["app.py"],
    "routes_files": ["app.py"],
    "models_files": ["app.py"],
    "test_command": "pytest -q",
    "run_hints": {"start": "uvicorn app:app --port 8000"},
    "business_summary": "A small shop: products, orders, refunds, cancel and ship, plus an admin export.",
}


def example_for(model: type[BaseModel]) -> dict[str, Any]:
    """The documented example reply for an agent output model."""
    if model is RepoSummary:
        return _REPO_SUMMARY_EXAMPLE
    extra = model.model_config.get("json_schema_extra")
    if not isinstance(extra, dict) or not extra.get("examples"):
        raise KeyError(f"{model.__name__} has no example")
    example = extra["examples"][0]
    assert isinstance(example, dict)
    return example


class CoordinatorDecision(BaseModel):
    """`next` is checked against the allowed set by the rails (core/rails.py), not here."""

    model_config = _config({"next": "diagnose", "reason": "A violation was found and replayed."})

    next: str = Field(min_length=1)
    reason: str


class SandboxPlan(BaseModel):
    model_config = _config({
        "mode": "command",
        "build": "pip install -r requirements.txt",
        "start": "uvicorn app:app --host 0.0.0.0 --port 8000",
        "port": 8000,
        "health_path": "/health",
        "env_required": ["MINISHOP_ADMIN_PASSWORD"],
        "env_defaults": {"MINISHOP_MODE": "bugs"},
    })

    mode: Literal["compose", "dockerfile", "command"]
    build: str | None = None
    start: str | None = None
    port: int = Field(ge=1, le=65535)
    health_path: str = "/health"
    env_required: list[str] = Field(default_factory=list)
    env_defaults: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _checks(self) -> Self:
        if not self.health_path.startswith("/") or self.health_path.startswith("//"):
            raise ValueError(f"health_path must start with a single '/': {self.health_path!r}")
        if self.mode == "command" and not self.start:
            raise ValueError("mode 'command' needs a start command")
        return self


class MapperOutput(BaseModel):
    """The actors, actions and state readers of rook.yaml (02 §6); cross-references are checked here."""

    model_config = _config({
        "actors": [{
            "name": "customer",
            "setup": [
                {"method": "POST", "path": "/auth/signup",
                 "json": {"email": "{{fresh.email}}", "password": "pw-{{fresh.id}}"}},
                {"method": "POST", "path": "/auth/login",
                 "json": {"email": "{{fresh.email}}", "password": "pw-{{fresh.id}}"},
                 "capture": {"token": "$.token"}},
            ],
            "auth": {"header": "Authorization", "value": "Bearer {{actor.token}}"},
        }],
        "actions": [{
            "name": "buy",
            "actor": "customer",
            "request": {"method": "POST", "path": "/orders",
                        "json": {"product_id": "{{ref.product_id}}", "quantity": "{{p.quantity}}"}},
            "params": {"quantity": {"int": [1, 3], "edges": [1]}},
            "requires": ["product_id"],
            "capture": {"order_id": "$.id"},
        }],
        "state": [{
            "name": "order",
            "each": "order_id",
            "request": {"method": "GET", "path": "/orders/{{order_id}}", "actor": "customer"},
            "fields": {"paid": "$.paid", "refunded": "$.refunded_total"},
        }],
    })

    actors: list[Actor] = Field(default_factory=list)
    actions: list[Action] = Field(min_length=1)
    state: list[StateReader] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references(self) -> Self:
        issues = [
            *_duplicates(self.actors, "actors", "name", "actor"),
            *_duplicates(self.actions, "actions", "name", "action"),
            *_duplicates(self.state, "state", "name", "state reader"),
        ]
        actors = {a.name for a in self.actors}
        issues += [(("actions", i, "actor"), f"unknown actor {a.actor!r}")
                   for i, a in enumerate(self.actions) if a.actor not in actors]
        issues += [(("state", i, "request", "actor"), f"unknown actor {s.request.actor!r}")
                   for i, s in enumerate(self.state)
                   if s.request.actor is not None and s.request.actor not in actors]
        if issues:
            raise ValueError("; ".join(f"{'.'.join(map(str, loc))}: {msg}" for loc, msg in issues))
        return self

    def to_model_parts(self) -> dict[str, list[dict[str, Any]]]:
        """The `actors`, `actions` and `state` sections as rook.yaml data (aliases, e.g. `json`, `int`)."""
        return {
            "actors": [a.model_dump(by_alias=True, exclude_none=True) for a in self.actors],
            "actions": [a.model_dump(by_alias=True, exclude_none=True) for a in self.actions],
            "state": [s.model_dump(by_alias=True, exclude_none=True) for s in self.state],
        }


class LawmakerOutput(BaseModel):
    """Proposed rules. Each needs evidence; the status is always forced to `proposed` (humans approve)."""

    model_config = _config({
        "rules": [{
            "id": "refund_le_paid",
            "text": "Total refunds never exceed the amount paid",
            "kind": "state",
            "scope": "order",
            "check": "order.refunded <= order.paid",
            "evidence": ["app.py: refund() compares each refund with paid on its own"],
        }],
    })

    rules: list[Rule] = Field(min_length=1)

    @model_validator(mode="after")
    def _evidence(self) -> Self:
        issues = [f"rules.{i}: rule {r.id!r} has no evidence" for i, r in enumerate(self.rules) if not r.evidence]
        issues += [f"{'.'.join(map(str, loc))}: {msg}"
                   for loc, msg in _duplicates(self.rules, "rules", "id", "rule id")]
        if issues:
            raise ValueError("; ".join(issues))
        for rule in self.rules:
            rule.status = "proposed"  # an agent can never approve its own rule
        return self

    def to_model_parts(self) -> dict[str, list[dict[str, Any]]]:
        """The `rules` section as rook.yaml data."""
        return {"rules": [r.model_dump(by_alias=True, exclude_none=True) for r in self.rules]}


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    rule_id: str
    steps: list[SequenceStep] = Field(min_length=1)


class TestDesignerOutput(BaseModel):
    __test__ = False  # not a pytest class

    model_config = _config({
        "scenarios": [{
            "name": "two partial refunds exceed the price",
            "rule_id": "refund_le_paid",
            "steps": [
                {"action": "create_product", "params": {"price": 100, "stock": 5}},
                {"action": "buy", "params": {"quantity": 1}},
                {"action": "refund", "params": {"amount": 60}},
                {"action": "refund", "params": {"amount": 60}},
            ],
        }],
    })

    scenarios: list[Scenario] = Field(min_length=1)


class StrategistOutput(BaseModel):
    model_config = _config({
        "weights": {"buy": 1.0, "refund": 2.0, "cancel": 0.5},
        "focus": ["refund_le_paid"],
        "reason": "Refund amounts near the paid price are the least explored edge.",
    })

    weights: dict[str, float]
    focus: list[str] = Field(default_factory=list)
    reason: str

    @model_validator(mode="after")
    def _non_negative(self) -> Self:
        negative = sorted(k for k, v in self.weights.items() if v < 0)
        if negative:
            raise ValueError(f"weights must be >= 0: {negative}")
        return self


class Diagnosis(BaseModel):
    model_config = _config({
        "file": "app.py",
        "line": 88,
        "explanation": "refund() checks each amount against paid, not the running refunded total.",
        "evidence": ["step 3 refunded 60 of 100", "step 4 refunded 60 more; refunded_total became 120"],
    })

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    explanation: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)


class SurgeonOutput(BaseModel):
    model_config = _config({
        "files": ["app.py"],
        "summary": "refund() now rejects a refund when refunded_total + amount exceeds paid.",
    })

    files: list[str]
    summary: str = Field(min_length=1)


class RuleVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    verdict: Literal["approve", "reject", "revise"]
    reason: str
    revised: Rule | None = None

    @model_validator(mode="after")
    def _revised(self) -> Self:
        if self.verdict == "revise" and self.revised is None:
            raise ValueError(f"verdict 'revise' for {self.rule_id!r} needs a 'revised' rule")
        if self.verdict != "revise" and self.revised is not None:
            raise ValueError(f"'revised' is only allowed with verdict 'revise' ({self.rule_id!r})")
        return self


class RuleCriticOutput(BaseModel):
    model_config = _config({
        "verdicts": [
            {"rule_id": "refund_le_paid", "verdict": "approve", "reason": "Backed by the refund code."},
            {"rule_id": "stock_positive", "verdict": "revise", "reason": "Stock may be zero.",
             "revised": {"id": "stock_non_negative", "text": "Product stock never goes below zero",
                         "kind": "state", "scope": "product", "check": "product.stock >= 0",
                         "evidence": ["app.py: buy() decrements stock"]}},
        ],
    })

    verdicts: list[RuleVerdict]


class ReviewVerdict(BaseModel):
    """The Diagnosis Reviewer's verdict."""

    model_config = _config({"verdict": "approve", "reason": "The cited line matches the failing step."})

    verdict: Literal["approve", "reject"]
    reason: str = Field(min_length=1)


class FixReviewOutput(BaseModel):
    model_config = _config({"verdict": "reject", "issues": ["The fix also removes the stock check."]})

    verdict: Literal["approve", "reject"]
    issues: list[str] = Field(default_factory=list)


class GuideAnswer(BaseModel):
    model_config = _config({"answer": "Rook is searching: 120 sequences run, no violation yet."})

    answer: str = Field(min_length=1)
