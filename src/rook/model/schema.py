"""Pydantic v2 models for `rook/rook.yaml` (docs/02_ARCHITECTURE.md section 6, a CONTRACT).

Structural checks only: rule `check` expressions are evaluated by `model/expr.py` (ROOK-004).
"""

import re
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, field_validator, model_validator

from rook.model.jsonpath import JSONPathError, compile_path
from rook.model.template import MAX_DEPTH, TemplateError, placeholders

SANDBOX_BASE_URL = "{{sandbox.base_url}}"
MAX_CHECK_LEN = 500

# Placeholder roots allowed in each part of the model.
ACTION_ROOTS = frozenset({"p", "ref", "fresh", "env", "actor"})
ACTOR_ROOTS = frozenset({"fresh", "env", "actor"})

_IDENT = r"^[A-Za-z_][A-Za-z0-9_]*$"

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _strings(obj: Any, depth: int = 0) -> list[str]:
    if depth > MAX_DEPTH:
        raise ValueError(f"request data is nested deeper than {MAX_DEPTH} levels")
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in (*_strings(k, depth + 1), *_strings(v, depth + 1))]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v, depth + 1)]
    return []


def _reject_absolute_urls(obj: Any) -> None:
    for text in _strings(obj):
        # Linear checks (no backtracking regex): any "scheme://" or a scheme-relative "//host".
        if "://" in text or text.lstrip().startswith("//"):
            shown = text if len(text) <= 80 else text[:77] + "..."
            raise ValueError(f"absolute URLs are not allowed (requests go only to the sandbox): {shown!r}")


def _check_placeholders(obj: Any, allowed_roots: frozenset[str], where: str) -> set[str]:
    try:
        names = placeholders(obj)
    except TemplateError as exc:
        raise ValueError(str(exc)) from exc
    for name in names:
        root = name.split(".", 1)[0]
        if root not in allowed_roots:
            allowed = ", ".join(sorted(allowed_roots))
            raise ValueError(
                f"template variable '{{{{{name}}}}}' is not allowed in {where} (allowed: {allowed})"
            )
    return names


def _check_jsonpaths(paths: dict[str, str]) -> dict[str, str]:
    for key, expr in paths.items():
        if not re.match(_IDENT, key):
            raise ValueError(f"invalid name {key!r}: use letters, digits and '_'")
        try:
            compile_path(expr)
        except JSONPathError as exc:
            raise ValueError(f"{key}: {exc}") from exc
    return paths


def _relative_path(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError(f"path must start with a single '/': {path!r}")
    return path


class ReferenceIssues(ValueError):
    """Cross-reference problems, each with its field path (the loader reports them one per line)."""

    def __init__(self, issues: list[tuple[tuple[str | int, ...], str]]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{'.'.join(map(str, loc))}: {msg}" for loc, msg in issues))


def _duplicates(
    items: list[Any], field: str, attr: str, what: str
) -> list[tuple[tuple[str | int, ...], str]]:
    seen: set[str] = set()
    issues: list[tuple[tuple[str | int, ...], str]] = []
    for i, item in enumerate(items):
        value = getattr(item, attr)
        if value in seen:
            issues.append(((field, i, attr), f"duplicate {what} {value!r}"))
        seen.add(value)
    return issues


class HttpRequest(_Strict):
    method: HttpMethod
    path: str
    json_body: Any = Field(default=None, alias="json")
    query: dict[str, Any] | None = None
    headers: dict[str, str] | None = None

    @field_validator("method", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return v.upper() if isinstance(v, str) else v

    @field_validator("path")
    @classmethod
    def _relative(cls, v: str) -> str:
        return _relative_path(v)

    @model_validator(mode="after")
    def _no_absolute_urls(self) -> Self:
        _reject_absolute_urls([self.path, self.json_body, self.query, self.headers])
        return self


class SetupRequest(HttpRequest):
    capture: dict[str, str] = Field(default_factory=dict)

    @field_validator("capture")
    @classmethod
    def _jsonpaths(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_jsonpaths(v)


class StateRequest(HttpRequest):
    actor: str | None = None


class Health(_Strict):
    method: HttpMethod = "GET"
    path: str = "/health"
    expect_status: int = Field(default=200, ge=100, le=599)

    @field_validator("path")
    @classmethod
    def _relative(cls, v: str) -> str:
        return _relative_path(v)


class App(_Strict):
    base_url: str = SANDBOX_BASE_URL
    health: Health = Field(default_factory=Health)
    isolation: Literal["fresh_entities", "restart"] = "fresh_entities"

    @field_validator("base_url")
    @classmethod
    def _sandbox_only(cls, v: str) -> str:
        if v.replace(" ", "") != SANDBOX_BASE_URL:
            raise ValueError(f"base_url must be {SANDBOX_BASE_URL!r} (injected at runtime), not {v!r}")
        return SANDBOX_BASE_URL


class Auth(_Strict):
    header: str = Field(min_length=1)
    value: str

    @model_validator(mode="after")
    def _templates(self) -> Self:
        _reject_absolute_urls(self.value)
        _check_placeholders(self.value, ACTOR_ROOTS, "actor auth")
        return self


class Actor(_Strict):
    name: str = Field(pattern=_IDENT)
    setup: list[SetupRequest] = Field(default_factory=list)
    auth: Auth | None = None

    @model_validator(mode="after")
    def _templates(self) -> Self:
        for req in self.setup:
            _check_placeholders(req.model_dump(by_alias=True), ACTOR_ROOTS, f"setup of actor {self.name!r}")
        return self


class IntRange(_Strict):
    int_range: tuple[int, int] = Field(alias="int")
    edges: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        lo, hi = self.int_range
        if lo > hi:
            raise ValueError(f"int range [{lo}, {hi}]: low bound is greater than high bound")
        outside = [e for e in self.edges if not lo <= e <= hi]
        if outside:
            raise ValueError(f"edges {outside} are outside the range [{lo}, {hi}]")
        return self


class Choice(_Strict):
    choice: list[Any] = Field(min_length=1)


class StringSpec(_Strict):
    pattern: str | None = None
    values: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.pattern is None) == (self.values is None):
            raise ValueError("string param needs exactly one of 'pattern' or 'values'")
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern {self.pattern!r}: {exc}") from exc
        return self


class StringParam(_Strict):
    string: StringSpec


def _param_kind(v: Any) -> str | None:
    if isinstance(v, dict):
        for key in ("int", "choice", "string"):
            if key in v:
                return key
        return None
    return {IntRange: "int", Choice: "choice", StringParam: "string"}.get(type(v))


Param = Annotated[
    Annotated[IntRange, Tag("int")]
    | Annotated[Choice, Tag("choice")]
    | Annotated[StringParam, Tag("string")],
    Discriminator(
        _param_kind,
        custom_error_type="param_kind",
        custom_error_message="a param needs one of 'int: [lo, hi]', 'choice: [...]' or 'string: {...}'",
    ),
]


class Action(_Strict):
    name: str = Field(pattern=_IDENT)
    actor: str
    request: HttpRequest
    params: dict[str, Param] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    capture: dict[str, str] = Field(default_factory=dict)
    weight: float = Field(default=1.0, gt=0)

    @field_validator("capture")
    @classmethod
    def _jsonpaths(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_jsonpaths(v)

    @model_validator(mode="after")
    def _templates(self) -> Self:
        names = _check_placeholders(self.request.model_dump(by_alias=True), ACTION_ROOTS, "an action request")
        for name in sorted(names):
            root, _, rest = name.partition(".")
            if root == "p" and rest.split(".")[0] not in self.params:
                raise ValueError(f"'{{{{{name}}}}}' uses param {rest!r}, which is not declared in params")
            if root == "ref" and rest.split(".")[0] not in self.requires:
                raise ValueError(f"'{{{{{name}}}}}' uses var {rest!r}, which is not listed in requires")
        return self


class StateReader(_Strict):
    name: str = Field(pattern=_IDENT)
    each: str = Field(pattern=_IDENT)
    request: StateRequest
    fields: dict[str, str] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def _jsonpaths(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_jsonpaths(v)

    @model_validator(mode="after")
    def _templates(self) -> Self:
        request = self.request.model_dump(by_alias=True, exclude={"actor"})
        _check_placeholders(request, frozenset({self.each, "env"}), f"state reader {self.name!r}")
        return self


class RuleWhen(_Strict):
    action: str
    actor: str | None = None


class Rule(_Strict):
    id: str = Field(pattern=_IDENT)
    text: str = Field(min_length=1)
    kind: Literal["state", "response"]
    scope: str = "global"
    when: RuleWhen | None = None
    check: str = Field(min_length=1, max_length=MAX_CHECK_LEN)
    evidence: list[str] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected"] = "proposed"

    @field_validator("check")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("check must not be blank")
        return v

    @model_validator(mode="after")
    def _kind_fields(self) -> Self:
        if self.kind == "response" and self.when is None:
            raise ValueError("a response rule needs 'when: {action, actor?}'")
        return self


class Step(_Strict):
    """One step of a generated or designed sequence (02 section 7.1)."""

    action: str
    actor: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ParallelStep(_Strict):
    """Steps sent concurrently, e.g. to catch check-then-act races."""

    parallel: list[Step] = Field(min_length=2)


SequenceStep = Step | ParallelStep


class RookModel(_Strict):
    version: Literal[1]
    app: App = Field(default_factory=App)
    actors: list[Actor] = Field(default_factory=list)
    actions: list[Action] = Field(min_length=1)
    state: list[StateReader] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references(self) -> Self:
        issues: list[tuple[tuple[str | int, ...], str]] = []
        issues += _duplicates(self.actors, "actors", "name", "actor")
        issues += _duplicates(self.actions, "actions", "name", "action")
        issues += _duplicates(self.state, "state", "name", "state reader")
        issues += _duplicates(self.rules, "rules", "id", "rule id")
        actors = {a.name for a in self.actors}
        actions = {a.name for a in self.actions}
        states = {s.name for s in self.state}
        for i, action in enumerate(self.actions):
            if action.actor not in actors:
                issues.append((("actions", i, "actor"), f"unknown actor {action.actor!r}"))
        for i, reader in enumerate(self.state):
            if reader.request.actor is not None and reader.request.actor not in actors:
                issues.append((("state", i, "request", "actor"), f"unknown actor {reader.request.actor!r}"))
        for i, rule in enumerate(self.rules):
            if rule.scope != "global" and rule.scope not in states:
                issues.append((("rules", i, "scope"), f"{rule.scope!r} is not a state name or 'global'"))
            if rule.when is not None:
                if rule.when.action not in actions:
                    issues.append((("rules", i, "when", "action"), f"unknown action {rule.when.action!r}"))
                if rule.when.actor is not None and rule.when.actor not in actors:
                    issues.append((("rules", i, "when", "actor"), f"unknown actor {rule.when.actor!r}"))
        if issues:
            raise ReferenceIssues(issues)
        return self

    def action(self, name: str) -> Action:
        for action in self.actions:
            if action.name == name:
                return action
        raise KeyError(name)

    def check_step(self, step: SequenceStep) -> None:
        """Raise ValueError if a sequence step names an unknown action or actor."""
        steps = step.parallel if isinstance(step, ParallelStep) else [step]
        actors = {a.name for a in self.actors}
        actions = {a.name for a in self.actions}
        for s in steps:
            if s.action not in actions:
                raise ValueError(f"step uses unknown action {s.action!r}")
            if s.actor is not None and s.actor not in actors:
                raise ValueError(f"step uses unknown actor {s.actor!r}")
