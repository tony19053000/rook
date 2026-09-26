"""Counterexample export (02_ARCHITECTURE.md section 7.8): `rook/counterexamples/cx_NNN.json`.

A counterexample holds everything needed to replay it exactly: the concrete steps (actor and params
fixed) with the pool index of every `ref` each sub-step used, the broken rule, the observed and
expected values, the search seed and a hash of the model it was found with.

Files are written only inside the target root: every directory component is opened relative to
its parent with O_NOFOLLOW (a planted symlink is refused before anything is created past it), and
the file is created with O_EXCL | O_NOFOLLOW, so an existing file or a symlink is never overwritten.
`observed` (app data) is capped in depth and size, with the truncation marked, before it reaches the
JSON file, the event or the generated test.
"""

import hashlib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from rook.core.events import CounterexampleSaved, EventBus, now_ts
from rook.engine.executor import Executor, StepResult
from rook.engine.judge import Judge, StateSnapshot, Violation
from rook.engine.replayer import ReplayResult
from rook.engine.runner import TraceStep
from rook.model.schema import ParallelStep, RookModel, Rule, RuleWhen, SequenceStep, Step

CX_DIR = Path("rook") / "counterexamples"
CX_ID = re.compile(r"cx_\d{3,6}")  # always used with fullmatch; the id ends up in file and test names
_CX_FILE = re.compile(r"cx_(\d{3,6})\.json")


MAX_DEPTH = 8  # containers nested deeper than this are replaced by a marker
MAX_JSON_BYTES = 64 * 1024  # a larger observed value is replaced by a marked preview
PREVIEW_CHARS = 4096
MAX_SEED_CHARS = 256
TRUNCATED = "_rook_truncated"


def cap_value(value: Any) -> Any:
    """`value` (app data, e.g. a Violation's observed) made safe to store and embed: containers
    nested deeper than MAX_DEPTH become a marker string, keys become strings, non-JSON scalars and
    non-finite floats become their repr, and if the JSON is still over MAX_JSON_BYTES the whole
    value becomes `{"_rook_truncated": <why>, "preview": <start of its JSON>}`. Idempotent."""
    capped = _cap(value, 1)
    text = json.dumps(capped, ensure_ascii=True, allow_nan=False)
    if len(text) <= MAX_JSON_BYTES:
        return capped
    return {
        TRUNCATED: f"value was {len(text)} bytes of JSON (limit {MAX_JSON_BYTES})",
        "preview": text[:PREVIEW_CHARS],
    }


def _cap(value: Any, depth: int) -> Any:
    if isinstance(value, dict | list | tuple):
        if depth > MAX_DEPTH:
            return f"<{TRUNCATED}: nested deeper than {MAX_DEPTH} levels>"
        if isinstance(value, dict):
            return {str(k): _cap(v, depth + 1) for k, v in value.items()}
        return [_cap(v, depth + 1) for v in value]
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return repr(value)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CxStep(_Strict):
    """One concrete sub-step: `refs` maps each required var to its index in the sequence's pool."""

    action: str
    actor: str
    params: dict[str, Any] = Field(default_factory=dict)
    refs: dict[str, int] = Field(default_factory=dict)


class CxParallel(_Strict):
    parallel: list[CxStep] = Field(min_length=2)


class CxRule(_Strict):
    id: str
    text: str
    kind: Literal["state", "response"]
    scope: str
    when: RuleWhen | None = None
    check: str


class Counterexample(_Strict):
    version: Literal[1] = 1
    cx_id: str
    rule: CxRule
    steps: list[CxStep | CxParallel] = Field(min_length=1)
    violated_at_step: int = Field(ge=0)  # 0-based index into `steps`
    observed: Any
    expected: str  # the rule's check expression, which must hold
    reproduced: str = Field(pattern=r"^\d+/\d+$")
    flaky: bool
    seed: int | str
    model_hash: str
    created_at: str = Field(default_factory=now_ts)

    @field_validator("observed")
    @classmethod
    def _cap_observed(cls, v: Any) -> Any:
        return cap_value(v)

    @field_validator("seed")
    @classmethod
    def _short_seed(cls, v: int | str) -> int | str:
        if isinstance(v, str) and len(v) > MAX_SEED_CHARS:
            raise ValueError(f"seed is longer than {MAX_SEED_CHARS} characters")
        return v

    @field_validator("cx_id")
    @classmethod
    def _cx_id(cls, v: str) -> str:
        if not CX_ID.fullmatch(v):
            raise ValueError(f"cx_id must look like 'cx_001', not {v!r}")
        return v

    @classmethod
    def build(
        cls,
        cx_id: str,
        model: RookModel,
        violation: Violation,
        trace: list[TraceStep],
        replay: ReplayResult,
        seed: int | str,
    ) -> "Counterexample":
        """From a shrunk trace (ShrinkResult.trace), its violation and the Replayer's result."""
        rule = next((r for r in model.rules if r.id == violation.rule_id), None)
        if rule is None:
            raise ValueError(f"rule {violation.rule_id!r} is not in the model")
        return cls(
            cx_id=cx_id,
            rule=_cx_rule(rule),
            steps=[_cx_step(t) for t in trace],
            violated_at_step=violation.step_index,
            observed=violation.observed,
            expected=rule.check,
            reproduced=replay.reproduced,
            flaky=replay.flaky,
            seed=seed,
            model_hash=model_hash(model),
        )

    def sequence(self) -> list[SequenceStep]:
        """The steps as model sequence steps (without the ref pins)."""
        out: list[SequenceStep] = []
        for step in self.steps:
            subs = step.parallel if isinstance(step, CxParallel) else [step]
            steps = [Step(action=s.action, actor=s.actor, params=dict(s.params)) for s in subs]
            out.append(ParallelStep(parallel=steps) if isinstance(step, CxParallel) else steps[0])
        return out

    def to_trace(self, model: RookModel) -> list[TraceStep]:
        """A replayable trace (for `replay_trace` / the Replayer). Raises ValueError on unknown steps."""
        trace: list[TraceStep] = []
        for step, seq_step in zip(self.steps, self.sequence(), strict=True):
            model.check_step(seq_step)
            subs = step.parallel if isinstance(step, CxParallel) else [step]
            results = [
                StepResult(s.action, s.actor, dict(s.params), {}, {}, refs_index=dict(s.refs)) for s in subs
            ]
            trace.append(TraceStep(seq_step, results))
        return trace

    def steps_json(self) -> list[dict[str, Any]]:
        return [s.model_dump(mode="json") for s in self.steps]

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True, allow_nan=False) + "\n"


def rule_only_model(model: RookModel, cx: Counterexample) -> RookModel:
    """`model` with the counterexample's own rule as its only approved rule (as it was when found)."""
    r = cx.rule
    rule = Rule(
        id=r.id, text=r.text, kind=r.kind, scope=r.scope, when=r.when, check=r.check, status="approved"
    )
    return RookModel.model_validate(
        {**model.model_dump(mode="json", by_alias=True, exclude_none=True), "rules": [rule.model_dump()]}
    )


# --- one exact replay ---


@dataclass
class CxReplay:
    """One exact replay of a counterexample, judged on its rule only.

    `problems` lists what kept the replay from exercising the whole counterexample (a step without an
    HTTP response, a skipped step, a failed state read, a rule error). A replay with problems proves
    nothing, so it never counts as "the rule holds".
    """

    violation: Violation | None
    steps_run: int
    problems: list[str] = field(default_factory=list)

    @property
    def holds(self) -> bool:
        return self.violation is None and not self.problems

    @property
    def message(self) -> str:
        if self.violation is not None:
            return (
                f"rule {self.violation.rule_id!r} broken again at step {self.violation.step_index + 1}; "
                f"observed {json.dumps(cap_value(self.violation.observed))}"
            )
        if self.problems:
            return "the counterexample did not fully run: " + "; ".join(self.problems)
        return f"the rule held for all {self.steps_run} steps"


async def replay_counterexample(ex: Executor, model: RookModel, cx: Counterexample) -> CxReplay:
    """Run the counterexample's exact steps once from a fresh context; the Judge checks its rule
    after every step (response rules on each response, state rules on every pooled entity)."""
    restricted = rule_only_model(model, cx)
    judge = Judge(restricted)
    ctx = ex.new_context()
    rng = random.Random(f"{cx.cx_id}:replay")  # unused: every param and ref is pinned
    trace = cx.to_trace(restricted)
    problems: list[str] = []
    for index, (t, step) in enumerate(zip(trace, cx.steps, strict=True)):
        pins = t.pinned_refs
        outcome = await ex.run_step(ctx, t.step, rng, pins if isinstance(step, CxParallel) else pins[0])
        results = outcome if isinstance(outcome, list) else [outcome]
        for r in results:
            if r.status is None:
                problems.append(f"step {index + 1} ({r.action}) got no response: {r.error}")
        for r in results:
            violation = judge.check_response(r, index)
            if violation is not None:
                return CxReplay(violation, index + 1)
        state: StateSnapshot = {}
        if judge.needs_full_state:
            state = await ex.read_state(ctx)
        else:
            snapshot: dict[str, dict[Any, dict[str, Any]]] = {}
            for reader in sorted(judge.state_scopes):
                snapshot.update(await ex.read_state(ctx, reader))
            state = snapshot
        violation = judge.check_state(state, index)
        if violation is not None:
            return CxReplay(violation, index + 1)
        if problems:
            return CxReplay(None, index + 1, problems)
    problems += [f"state read failed: {e}" for e in ctx.state_errors]
    problems += [f"rule error: {e}" for e in judge.rule_errors.values()]
    return CxReplay(None, len(trace), problems)


def _cx_rule(rule: Rule) -> CxRule:
    return CxRule(
        id=rule.id, text=rule.text, kind=rule.kind, scope=rule.scope, when=rule.when, check=rule.check
    )


def _cx_step(t: TraceStep) -> CxStep | CxParallel:
    subs = t.step.parallel if isinstance(t.step, ParallelStep) else [t.step]
    pins = t.pinned_refs
    if len(pins) != len(subs):
        raise ValueError(f"trace step has {len(subs)} sub-steps but {len(pins)} results")
    steps = [
        CxStep(action=s.action, actor=s.actor or "", params=dict(s.params), refs=dict(pin))
        for s, pin in zip(subs, pins, strict=True)
    ]
    if any(not s.actor for s in steps):
        raise ValueError("a counterexample step needs a concrete actor (use the runner's concrete trace)")
    return CxParallel(parallel=steps) if isinstance(t.step, ParallelStep) else steps[0]


def model_hash(model: RookModel) -> str:
    """`sha256:<hex>` of the model's canonical JSON."""
    data = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


# --- files ---


def write_new_file(root: Path, relative_dir: Path, name: str, text: str) -> Path:
    """Create `root/relative_dir/name` with `text` and return its path. Nothing is followed or
    overwritten: each directory component is opened (or first created) relative to its parent's fd
    with O_NOFOLLOW, so a symlinked component anywhere is refused before anything is created past
    it, and there is no gap between checking a path and using it. The file is created with O_EXCL.
    """
    parts = [*relative_dir.parts, name]
    if relative_dir.is_absolute() or any(p in ("", ".", "..") or os.sep in p for p in parts):
        raise PermissionError(f"refused path {relative_dir / name}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o755, dir_fd=fd)
            except FileExistsError:
                pass  # an existing symlink is not followed by mkdir, and O_NOFOLLOW refuses it below
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=fd)
            except OSError as exc:
                raise PermissionError(f"{part!r} in {relative_dir} is not a plain directory: {exc}") from exc
            os.close(fd)
            fd = child
        file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o644, dir_fd=fd)
    finally:
        os.close(fd)
    with os.fdopen(file_fd, "w", encoding="utf-8") as f:
        f.write(text)
    return root / relative_dir / name


def next_cx_id(root: Path) -> str:
    """The next free `cx_NNN` id under `root/rook/counterexamples/`."""
    directory = root / CX_DIR
    numbers = [
        int(m.group(1))
        for p in (directory.iterdir() if directory.is_dir() else [])
        if (m := _CX_FILE.fullmatch(p.name))
    ]
    return f"cx_{max(numbers, default=0) + 1:03d}"


def save_counterexample(root: Path, cx: Counterexample) -> Path:
    """Write `root/rook/counterexamples/<cx_id>.json` and return its path."""
    return write_new_file(root, CX_DIR, f"{cx.cx_id}.json", cx.to_json())


def load_counterexample(path: Path) -> Counterexample:
    return Counterexample.model_validate_json(path.read_text(encoding="utf-8"))


async def publish_saved(bus: EventBus, run_id: str, cx: Counterexample, test_path: str | None) -> None:
    """Emit `counterexample.saved`."""
    await bus.publish(
        run_id,
        "counterexample.saved",
        CounterexampleSaved(
            cx_id=cx.cx_id,
            rule_id=cx.rule.id,
            rule_text=cx.rule.text,
            steps=cx.steps_json(),
            observed=cx.observed,
            expected=cx.expected,
            reproduced=cx.reproduced,
            flaky=cx.flaky,
            test_path=test_path,
        ),
    )
