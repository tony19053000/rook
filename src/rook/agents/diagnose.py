"""The DIAGNOSE phase: Detective -> engine check -> Diagnosis Reviewer, up to 3 rounds (02 section 4).

Bob proposes and code decides (CLAUDE.md rule 1):
- the evidence bundle is built by code, deterministically: the broken rule, the counterexample's
  minimal steps, the responses and entity state after each step (from one exact replay of the
  counterexample, with the app-assigned ids shown as stable aliases), the sandbox logs (without request
  lines and volatile bits) and the related source files, all capped in size. The same counterexample on
  the same code gives the same prompts on any machine, so recorded Bob calls replay (02 section 5.1);
- the Detective proposes a file and line; the engine checks that the file is a regular file inside the
  workspace (no path or symlink escape) and that the line exists. An invalid diagnosis is a failed round,
  and the reason goes back to the Detective;
- only the Diagnosis Reviewer approves. After 3 rounds without approval the result is reported honestly
  as not reviewed (`diagnosis.ready.reviewed = false`).

Everything that comes from the app or from Bob is untrusted data (03 section 4): it reaches the prompts
inside <untrusted> blocks and is only validated and used as data, never executed.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.modes import write_modes
from rook.agents.schemas import Diagnosis, ReviewVerdict
from rook.agents.understand import SKIP_DIRS, check_not_rook_repo
from rook.agents.volatile import Masker, is_token_key, snake
from rook.core import rails
from rook.core.events import (
    DiagnosisReady,
    EngineFinished,
    EngineStarted,
    Log,
    RepoSummary,
    RunPhase,
    redact,
    redact_text,
)
from rook.engine.executor import Executor
from rook.engine.judge import Judge
from rook.export.counterexample import Counterexample, CxParallel, cap_value, rule_only_model
from rook.model.jsonpath import JSONPathError, compile_path
from rook.model.schema import RookModel
from rook.sandbox.base import Sandbox, SandboxError

MAX_ROUNDS = rails.MAX_RETRIES

# Related source files shown to both agents.
SOURCE_SUFFIXES = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt", ".php", ".rs",
    ".cs", ".ex", ".exs", ".scala", ".swift", ".sql",
})
# Top-level folders that hold Rook's own output or private data, never the app's code.
EXCLUDED_TOP = frozenset({".git", ".bob", ".rook", ".rook-sandbox", "rook"})
RELATED_MAX_FILES = 4
RELATED_FILE_MAX_CHARS = 20_000
RELATED_MAX_TOTAL = 60_000
SCAN_MAX_FILES = 2_000
SCAN_FILE_MAX_BYTES = 1_000_000
LOGS_MAX_CHARS = 4_000
LOGS_TAIL_LINES = 200
STEP_VALUE_MAX_CHARS = 2_000
# The cited file is read whole to count its lines; larger files are refused.
CITED_FILE_MAX_BYTES = 5_000_000
EXPLANATION_MAX_CHARS = 2_000
EVIDENCE_MAX_ITEMS = 10
EVIDENCE_ITEM_MAX_CHARS = 500
CITED_WINDOW = 15  # lines shown to the reviewer around the cited line


# --- the evidence bundle ---


@dataclass(frozen=True)
class EvidenceBundle:
    """The inputs both agents see. Deterministic for the same counterexample, replay and workspace."""

    cx_id: str
    rule: dict[str, Any]
    steps: list[dict[str, Any]]
    states: list[dict[str, Any]]
    logs: str
    files: dict[str, str]  # workspace-relative path -> numbered text


def _clip(value: Any, limit: int = STEP_VALUE_MAX_CHARS) -> Any:
    """App data capped in depth and size, and cut to `limit` characters of JSON if still larger."""
    capped = cap_value(value)
    text = json.dumps(capped, sort_keys=True, ensure_ascii=False)
    return capped if len(text) <= limit else {"_rook_truncated": f"{len(text)} chars", "preview": text[:limit]}


_ID_NAMES = frozenset({"id", "ids", "uuid", "uuids", "_id", "pk"})
# Field entities that name a user: resolved among the actors' setup captures (`customer.user_id`).
_USERISH = frozenset({"user", "owner", "customer", "buyer", "seller", "author", "account", "member",
                      "created_by", "payer", "payee", "actor"})


def _is_id_key(key: str, names: frozenset[str] = frozenset()) -> bool:
    if key in names:
        return True
    s = snake(key)
    return s in _ID_NAMES or s.endswith(("_id", "_ids", "_uuid", "_uuids"))


def _entity(name: str) -> str:
    """The entity a var or field names: `order_id`, `orderId`, `orders`, `order_ids`, `customer.user_id` ->
    `order`, `order`, `order`, `order`, `user` ("" for a bare `id`)."""
    s = snake(name.rsplit(".", 1)[-1])
    for suffix in ("_uuids", "_uuid", "_ids", "_id"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    else:
        if s in _ID_NAMES:
            s = ""
    return s.removesuffix("s")


def _aliasable(value: Any) -> bool:
    return isinstance(value, int | str) and not isinstance(value, bool)


@dataclass(frozen=True)
class IdAliases:
    """The replay's captured values, per var: `var -> {value: "var[n]"}` (n = its first index in the pool,
    as the steps' `refs` name it). Actors' setup captures are vars too, named `actor.name`.

    Apps often count ids per entity (order 1 and product 1), so one value can belong to several vars. A
    value is resolved in context (`lookup`): first among the vars its place names (a capture path, the
    field's name, the entity it sits in); only if none of them holds it, among all vars. If several vars
    still hold it, all their aliases are shown (`order_id[0]|product_id[0]`), never a guess."""

    by_var: dict[str, dict[tuple[type, Any], str]]

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self.by_var)

    def vars_for(self, name: str) -> tuple[str, ...]:
        """The vars a field or container name refers to: the var of that name, else those naming the
        same entity (`orderId`, `order` and `orders` -> `order_id`)."""
        if name in self.by_var:
            return (name,)
        entity = _entity(name)
        if not entity:
            return ()
        found = tuple(v for v in self.by_var if _entity(v) == entity)
        if found or entity not in _USERISH:
            return found
        # `owner_id`, `customer_id`, `userId`...: a user, i.e. an actor's own id from its setup
        return tuple(v for v in self.by_var if "." in v and (
            _entity(v) in _USERISH or not _entity(v) or v.split(".", 1)[0] == entity))

    def lookup(self, value: Any, *groups: Sequence[str]) -> str | None:
        if not _aliasable(value):
            return None
        key = (type(value), value)
        for group in (*groups, tuple(self.by_var)):
            found = sorted({self.by_var[v][key] for v in group if key in self.by_var.get(v, {})})
            if found:
                return "|".join(found)
        return None


def id_aliases(pool: Mapping[str, list[Any]], actors: Mapping[str, Mapping[str, Any]] | None = None
               ) -> IdAliases:
    """The aliases of a replay's pool and actor setup captures. The ids themselves depend on what the app
    served before (the search), the aliases do not."""
    by_var: dict[str, dict[tuple[type, Any], str]] = {}
    for var, values in pool.items():
        aliases = by_var.setdefault(var, {})
        for index, value in enumerate(values):
            if _aliasable(value):
                aliases.setdefault((type(value), value), f"{var}[{index}]")
    for actor, namespace in (actors or {}).items():
        for name, value in namespace.items():
            if _aliasable(value) and not is_token_key(name):
                by_var[f"{actor}.{name}"] = {(type(value), value): f"{actor}.{name}"}
    return IdAliases(by_var)


def capture_paths(captures: Mapping[str, str]) -> dict[tuple[str, ...], str]:
    """An action's `capture` as `{key path in the response: var}` (list indexes and wildcards dropped)."""
    out: dict[tuple[str, ...], str] = {}
    for var, expr in captures.items():
        try:
            out[tuple(s for s in compile_path(expr) if isinstance(s, str))] = var
        except JSONPathError:
            continue
    return out


def alias_ids(value: Any, aliases: IdAliases, *, masker: Masker | None = None, key: str = "",
              owner: Sequence[str] = (), keys_of: Sequence[str] = (),
              captured: Mapping[tuple[str, ...], str] | None = None, path: tuple[str, ...] = ()) -> Any:
    """`value` with every captured id replaced by its alias: in the keys of a map keyed by ids (`keys_of`
    names their var; the state is `{reader: {id: fields}}`) and in the values of id-like fields (`id`,
    `*_id`, `*Id`, `*_ids` or a var name). A field's value is looked up first under the var its capture
    path names (`captured`, from the action that answered), then the vars its name names, then the entity
    it sits in (`owner`, for a bare `id`). With a `masker`, an id-like value that is in no var (an id Rook
    never captured) becomes a numbered label per field, like `<owner_id#1>`. Other values are left alone,
    so a price that happens to equal an id is never touched.

    In a list of objects, the entries that refer to nothing this replay made (`_mentions`) are what the app
    already held, i.e. what the search left behind (an admin export lists every order): they are replaced
    by one note naming their fields, so the evidence does not depend on the search."""
    captured = captured or {}
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for k, v in value.items():
            name = str(k)
            new_key = aliases.lookup(k, keys_of) if keys_of else aliases.lookup(k)
            # A nested object or list names its own entity (by the key it sits under); a scalar field
            # belongs to this object's.
            if keys_of:
                child_owner = tuple(keys_of)
            elif isinstance(v, dict | list | tuple):
                child_owner = aliases.vars_for(name)
            else:
                child_owner = tuple(owner)
            out[new_key if new_key is not None else k] = alias_ids(
                v, aliases, masker=masker, key=name, owner=child_owner, captured=captured,
                path=(*path, name) if not keys_of else path)
        return out
    if isinstance(value, list | tuple):
        items = list(value)
        other: list[dict[Any, Any]] = []
        if items and all(isinstance(v, dict) for v in items):
            other = [v for v in items if not _mentions(v, aliases, owner, captured, path)]
            items = [v for v in items if not any(v is o for o in other)]
        out_items = [alias_ids(v, aliases, masker=masker, key=key, owner=owner, captured=captured, path=path)
                     for v in items]
        if other:
            fields = ", ".join(sorted({str(k) for o in other for k in o}))
            out_items.append({"_rook_other_items": f"entries the app already held before this replay, not shown "
                                                   f"(they depend on the search); their fields: {fields}"})
        return out_items
    alias = _resolve(value, aliases, key, owner, captured, path)
    if alias is not None or not _is_id_key(key, aliases.names) or not _aliasable(value):
        return alias if alias is not None else value
    return masker.label(key, str(value)) if masker is not None else value


def _resolve(value: Any, aliases: IdAliases, key: str, owner: Sequence[str],
             captured: Mapping[tuple[str, ...], str], path: tuple[str, ...]) -> str | None:
    """The alias of an id-like field's value in its context, or None."""
    if not _is_id_key(key, aliases.names) or not _aliasable(value):
        return None
    by_path = (captured[path],) if path in captured else ()
    by_owner = tuple(owner) if snake(key) in _ID_NAMES else ()
    return aliases.lookup(value, by_path, aliases.vars_for(key), by_owner)


def _mentions(item: dict[Any, Any], aliases: IdAliases, owner: Sequence[str],
              captured: Mapping[tuple[str, ...], str], path: tuple[str, ...]) -> bool:
    """Whether a list entry refers to something this replay made (one of its id fields, or of a nested
    object's, is a captured value). Entries that do not are what the app held before: the search's data."""
    for k, v in item.items():
        name = str(k)
        if isinstance(v, dict) and _mentions(v, aliases, aliases.vars_for(name), captured, (*path, name)):
            return True
        if _resolve(v, aliases, name, owner, captured, (*path, name)) is not None:
            return True
    return False


async def collect_step_states(ex: Executor, model: RookModel, cx: Counterexample,
                              masker: Masker | None = None) -> list[dict[str, Any]]:
    """Replay the counterexample once, exactly, from a fresh context and record, after every step, each
    response (status and body) and the state of every pooled entity. The Judge marks where the rule
    breaks. Request bodies are left out: they hold fresh random values and the actors' credentials.
    App-assigned ids are shown as their aliases (`id_aliases`), and volatile values (tokens, times, random
    ids, Rook's fresh values) are masked by `masker` (`volatile.Masker`), so the records do not depend on
    the run."""
    restricted = rule_only_model(model, cx)
    judge = Judge(restricted)
    ctx = ex.new_context()
    rng = random.Random(f"{cx.cx_id}:diagnose")  # unused: every param and ref is pinned
    raw: list[tuple[list[dict[str, Any]], dict[str, Any], bool]] = []
    for index, (t, step) in enumerate(zip(cx.to_trace(restricted), cx.steps, strict=True)):
        pins = t.pinned_refs
        outcome = await ex.run_step(ctx, t.step, rng, pins if isinstance(step, CxParallel) else pins[0])
        results = outcome if isinstance(outcome, list) else [outcome]
        responses = [
            {"action": r.action, "actor": r.actor, "status": r.status, "body": r.response_json,
             **({"error": r.error} if r.error else {})}
            for r in results
        ]
        broken = any(judge.check_response(r, index) is not None for r in results)
        state = await ex.read_state(ctx)
        broken = judge.check_state(state, index) is not None or broken
        raw.append((responses, state, broken))
    masker = masker if masker is not None else Masker()
    masker.add_fresh(ctx.fresh_token)
    aliases = id_aliases(ctx.pool, ctx.actors)
    captures = {a.name: capture_paths(a.capture) for a in model.actions}
    each = {r.name: r.each for r in model.state}

    def body(r: dict[str, Any]) -> Any:
        return masker.value(alias_ids(r["body"], aliases, masker=masker, captured=captures.get(r["action"])))

    def entities(state: dict[str, Any]) -> dict[str, Any]:
        return {name: masker.value(alias_ids(items, aliases, masker=masker, keys_of=(each.get(name, name),)))
                for name, items in state.items()}

    records: list[dict[str, Any]] = []
    for index, (responses, state, broken) in enumerate(raw):
        records.append({
            "step": index + 1,
            "responses": [{**r, "body": _clip(body(r)),
                           **({"error": masker.text(r["error"])} if "error" in r else {})} for r in responses],
            "state": _clip(entities(state), 4 * STEP_VALUE_MAX_CHARS),
            "rule": "broken" if broken else "holds",
        })
    errors = [*ctx.state_errors, *judge.rule_errors.values()]
    if errors:
        records.append({"replay_problems": [masker.text(redact_text(e)) for e in errors[:10]]})
    return redact(records)


def _rule_input(cx: Counterexample, masker: Masker | None = None) -> dict[str, Any]:
    """The broken rule and what the engine observed, with volatile values masked (`volatile.Masker`)."""
    masker = masker if masker is not None else Masker()
    return {
        **cx.rule.model_dump(mode="json", exclude_none=True),
        "expected": cx.expected,
        # Found during the search: its ids are the search's, never this replay's (so none is an alias).
        "observed": _clip(masker.value(alias_ids(cx.observed, IdAliases({}), masker=masker))),
        "broken_at_step": cx.violated_at_step + 1,
        "reproduced": cx.reproduced,
    }


def _steps_input(cx: Counterexample) -> list[dict[str, Any]]:
    out = []
    for index, step in enumerate(cx.steps):
        subs = step.parallel if isinstance(step, CxParallel) else [step]
        items = [s.model_dump(mode="json") for s in subs]
        out.append({"step": index + 1, **({"parallel": items} if len(subs) > 1 else items[0])})
    return out


def _search_terms(model: RookModel, cx: Counterexample) -> list[str]:
    """Words the related code must contain: the counterexample's action names, the static parts of their
    request paths, and the rule's scope and the state reader's path."""
    names = {s.action for step in cx.steps for s in (step.parallel if isinstance(step, CxParallel) else [step])}
    terms: set[str] = set(names)
    paths = [a.request.path for a in model.actions if a.name in names]
    paths += [r.request.path for r in model.state if r.name == cx.rule.scope]
    for path in paths:
        for part in path.split("/"):
            if part and "{{" not in part and len(part) >= 3:
                terms.add("/" + part)
    if cx.rule.scope and cx.rule.scope != "response":
        terms.add(cx.rule.scope)
    return sorted(terms)


def _source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):  # never follows symlinked folders
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS
                             and not (rel_dir == Path(".") and d in EXCLUDED_TOP))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.suffix in SOURCE_SUFFIXES and not path.is_symlink() and path.is_file():
                files.append(path)
                if len(files) >= SCAN_MAX_FILES:
                    return files
    return files


def _is_test(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    return any(p in ("test", "tests", "__tests__", "spec") for p in parts[:-1]) or name.startswith("test_") \
        or ".test." in name or ".spec." in name or name.endswith("_test.py")


def number_lines(text: str, limit: int = RELATED_FILE_MAX_CHARS) -> str:
    """`text` with 1-based line numbers (`  12| code`), cut at whole lines to about `limit` characters."""
    out: list[str] = []
    size = 0
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        row = f"{n:>5}| {line}"
        if size + len(row) > limit:
            out.append(f"[truncated by Rook after line {n - 1} of {len(lines)}]")
            break
        out.append(row)
        size += len(row) + 1
    return "\n".join(out)


def related_files(workspace: Path, model: RookModel, cx: Counterexample,
                  summary: RepoSummary | None = None) -> dict[str, str]:
    """The app's source files most related to the counterexample, numbered and capped.

    A file's score is how many search terms it contains (plus one if the Scout listed it as a routes or
    models file). App code comes before tests; ties go by path, so the choice is deterministic."""
    root = workspace.resolve()
    terms = _search_terms(model, cx)
    listed = set(summary.routes_files + summary.models_files) if summary else set()
    scored: list[tuple[bool, int, str, str]] = []
    for path in _source_files(root):
        if path.stat().st_size > SCAN_FILE_MAX_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "\x00" in text:
            continue
        rel = path.relative_to(root).as_posix()
        score = sum(term in text for term in terms) + (rel in listed)
        if score:
            scored.append((_is_test(rel), -score, rel, text))
    out: dict[str, str] = {}
    total = 0
    for _, _, rel, text in sorted(scored)[:RELATED_MAX_FILES]:
        numbered = number_lines(text)
        if total + len(numbered) > RELATED_MAX_TOTAL:
            break
        out[rel] = numbered
        total += len(numbered)
    return out


# Log lines that say nothing the bundle does not already hold, and differ from run to run: one line per
# HTTP request (the replay's responses are in the states; the search's are noise), and the server's own
# start and stop lines (uvicorn, gunicorn, Node/Express dev loggers, ...).
_REQUEST_LINE = re.compile(
    r'"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) \S* HTTP/[\d.]+" \d{3}'  # uvicorn, gunicorn, common log
    r"|^\s*(?:\S+\s+)?(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /\S* \d{3}\b"  # morgan dev, Go, ...
)
_LIFECYCLE_LINE = re.compile(
    r"(?:Started|Finished) server process|Waiting for application (?:startup|shutdown)"
    r"|Application (?:startup|shutdown) complete|running on https?://|Shutting down|Listening (?:at|on)"
    r"|Booting worker|Started reloader process|Will watch for changes",
    re.IGNORECASE,
)


def clean_logs(text: str, workspace: Path | None = None, masker: Masker | None = None) -> str:
    """The app's log lines without request and start/stop lines, with volatile bits masked in place (not
    dropped: a traceback's text still matters): timestamps, addresses, pids, temp paths, durations,
    tokens and random ids (`volatile.Masker.text`); the workspace path is shown as `/workspace`."""
    masker = masker if masker is not None else Masker()
    root = str(workspace.resolve()) if workspace is not None else ""
    out = []
    for line in text.splitlines():
        if not line.strip() or _REQUEST_LINE.search(line) or _LIFECYCLE_LINE.search(line):
            continue
        if root:
            line = line.replace(root, "/workspace")
        out.append(masker.text(line).rstrip())
    return "\n".join(out)


def tail_logs(text: str, limit: int = LOGS_MAX_CHARS, workspace: Path | None = None,
              masker: Masker | None = None) -> str:
    """The cleaned, redacted logs, cut to their last `limit` characters at a line start."""
    text = clean_logs(redact_text(text), workspace, masker)
    if len(text) <= limit:
        return text
    cut = text[-limit:]
    newline = cut.find("\n")
    return "...\n" + (cut[newline + 1:] if 0 <= newline < len(cut) - 1 else cut)


def build_bundle(workspace: Path, model: RookModel, cx: Counterexample, states: list[dict[str, Any]],
                 logs: str, summary: RepoSummary | None = None, masker: Masker | None = None) -> EvidenceBundle:
    """`masker`: the one that masked `states`, so a value keeps its label across the bundle."""
    masker = masker if masker is not None else Masker()
    return EvidenceBundle(
        cx_id=cx.cx_id,
        rule=_rule_input(cx, masker),
        steps=_steps_input(cx),
        states=states,
        logs=tail_logs(logs, workspace=workspace, masker=masker),
        files=related_files(workspace, model, cx, summary),
    )


# --- the engine's check of a diagnosis ---


@dataclass(frozen=True)
class CheckedDiagnosis:
    file: str  # workspace-relative, POSIX
    line: int
    line_text: str
    explanation: str
    evidence: list[str]
    numbered: str  # the file's lines around the cited one, numbered


class InvalidDiagnosis(ValueError):
    pass


def _relative(root: Path, raw: str) -> PurePosixPath:
    if not raw or any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw) or "\\" in raw:
        raise InvalidDiagnosis(f"{raw!r} is not a usable path")
    path = PurePosixPath(raw)
    if path.is_absolute():
        # Bob reads files through its tools, so it may answer with the absolute path inside the workspace.
        try:
            path = path.relative_to(PurePosixPath(root.as_posix()))
        except ValueError:
            raise InvalidDiagnosis(f"{raw!r} is outside the workspace") from None
    if not path.parts or any(p in ("..", ".") for p in path.parts):
        raise InvalidDiagnosis(f"{raw!r} is outside the workspace")
    if path.parts[0] in EXCLUDED_TOP or any(p in SKIP_DIRS for p in path.parts[:-1]):
        raise InvalidDiagnosis(f"{raw!r} is not part of the app's source")
    return path


def check_diagnosis(workspace: Path, diagnosis: Diagnosis) -> CheckedDiagnosis:
    """Validate a Detective's answer against the workspace. Raises InvalidDiagnosis with the reason.

    No component of the path may be a symlink (so neither `..` nor a planted link can point outside),
    the file must be a regular text file, and `line` must be one of its lines."""
    root = workspace.resolve()
    rel = _relative(root, diagnosis.file.strip())
    current = root
    for part in rel.parts:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except OSError:
            raise InvalidDiagnosis(f"{rel} does not exist in the workspace") from None
        if stat.S_ISLNK(mode):
            raise InvalidDiagnosis(f"{rel} goes through a symlink ({current.relative_to(root)})")
    if not stat.S_ISREG(mode):
        raise InvalidDiagnosis(f"{rel} is not a regular file")
    if os.lstat(current).st_size > CITED_FILE_MAX_BYTES:
        raise InvalidDiagnosis(f"{rel} is too large to cite")
    text = current.read_text(encoding="utf-8", errors="replace")
    if "\x00" in text:
        raise InvalidDiagnosis(f"{rel} is not a text file")
    lines = text.splitlines()
    if not 1 <= diagnosis.line <= len(lines):
        raise InvalidDiagnosis(f"line {diagnosis.line} is out of range: {rel} has {len(lines)} lines")
    lo, hi = max(1, diagnosis.line - CITED_WINDOW), min(len(lines), diagnosis.line + CITED_WINDOW)
    numbered = "\n".join(f"{n:>5}| {lines[n - 1]}" for n in range(lo, hi + 1))
    evidence = [e[:EVIDENCE_ITEM_MAX_CHARS] for e in diagnosis.evidence[:EVIDENCE_MAX_ITEMS]]
    return CheckedDiagnosis(
        file=rel.as_posix(), line=diagnosis.line, line_text=lines[diagnosis.line - 1][:500],
        explanation=diagnosis.explanation.strip()[:EXPLANATION_MAX_CHARS], evidence=evidence,
        numbered=numbered,
    )


# --- the loop ---


@dataclass(frozen=True)
class Round:
    number: int
    diagnosis: dict[str, Any] | None  # what the Detective answered, if anything
    outcome: str  # "approved" | "rejected" (reviewer) | "invalid" (engine) | "failed" (no answer)
    reason: str


@dataclass
class DiagnosisResult:
    cx_id: str
    file: str  # "" if no diagnosis passed the engine check
    line: int | None
    explanation: str
    evidence: list[str] = field(default_factory=list)
    reviewed: bool = False  # True only when the Diagnosis Reviewer approved
    rounds: list[Round] = field(default_factory=list)


def _diag_json(diagnosis: Diagnosis) -> dict[str, Any]:
    return redact(diagnosis.model_dump(mode="json"))


def _reviewer_input(checked: CheckedDiagnosis) -> dict[str, Any]:
    return {
        "file": checked.file,
        "line": checked.line,
        "cited_line_text": checked.line_text,
        "explanation": checked.explanation,
        "evidence": checked.evidence,
        "engine_check": "the file exists in the workspace and the line is in range",
    }


class DiagnosePipeline:
    def __init__(self, client: AgentCaller, workspace: str | os.PathLike[str], *,
                 max_rounds: int = MAX_ROUNDS) -> None:
        """`workspace` is the run's copy of the target; Bob runs there with read-only modes."""
        self.client = client
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")
        check_not_rook_repo(self.workspace)
        self.max_rounds = max_rounds

    async def run(self, model: RookModel, cx: Counterexample, executor: Executor, *,
                  sandbox: Sandbox | None = None, summary: RepoSummary | None = None,
                  prior: str = "") -> DiagnosisResult:
        """Replay the counterexample for its per-step state, build the bundle and run the review loop.

        `prior` is what went wrong before this diagnosis (e.g. an earlier fix that failed verification);
        it is shown to the Detective with the round feedback."""
        await self._publish("run.phase", RunPhase(phase="DIAGNOSE"))
        await self._publish("engine.started", EngineStarted(
            worker="replayer", label=f"Replaying {cx.cx_id} to record the state after each step"))
        masker = Masker()
        states = await collect_step_states(executor, model, cx, masker)
        await self._publish("engine.finished", EngineFinished(
            worker="replayer", ok=True, summary=f"Recorded the state after {len(cx.steps)} steps"))
        logs = await self._logs(sandbox)
        bundle = await asyncio.to_thread(build_bundle, self.workspace, model, cx, states, logs, summary, masker)
        return await self.diagnose(bundle, prior=masker.text(prior))

    async def _logs(self, sandbox: Sandbox | None) -> str:
        if sandbox is None:
            return ""
        try:
            return await asyncio.to_thread(sandbox.logs, LOGS_TAIL_LINES)
        except (SandboxError, OSError) as exc:
            return f"(the sandbox logs could not be read: {exc})"

    async def diagnose(self, bundle: EvidenceBundle, *, prior: str = "") -> DiagnosisResult:
        """Detective -> engine check -> reviewer, up to `max_rounds`; publishes `diagnosis.ready`."""
        write_modes(self.workspace)
        rounds: list[Round] = []
        last_valid: CheckedDiagnosis | None = None
        for number in range(1, self.max_rounds + 1):
            outcome = await self._round(number, bundle, rounds, prior)
            rounds.append(outcome[0])
            if outcome[1] is not None:
                last_valid = outcome[1]
            if outcome[0].outcome == "approved":
                assert last_valid is not None
                return await self._finish(bundle, last_valid, True, rounds)
            await self._log("warn", f"Diagnosis round {number}/{self.max_rounds} not approved: "
                                    f"{outcome[0].reason}")
        return await self._finish(bundle, last_valid, False, rounds)

    async def _round(self, number: int, bundle: EvidenceBundle, history: list[Round], prior: str = ""
                     ) -> tuple[Round, CheckedDiagnosis | None]:
        feedback = "\n\n".join(part for part in (prior, _feedback(history)) if part)
        try:
            result = await call_agent(self.client, "detective", self.workspace, rule=bundle.rule,
                                      steps=bundle.steps, states=bundle.states, logs=bundle.logs,
                                      files=bundle.files, feedback=feedback)
        except BOB_FAILURES as exc:
            return Round(number, None, "failed", f"the Detective gave no valid answer: {exc}"), None
        diagnosis = result.output
        assert isinstance(diagnosis, Diagnosis)
        try:
            checked = await asyncio.to_thread(check_diagnosis, self.workspace, diagnosis)
        except InvalidDiagnosis as exc:
            return Round(number, _diag_json(diagnosis), "invalid", f"engine check failed: {exc}"), None
        files = dict(bundle.files)
        files[f"{checked.file} (lines around the cited one)"] = checked.numbered
        try:
            review = await call_agent(self.client, "diag_reviewer", self.workspace, rule=bundle.rule,
                                      diagnosis=_reviewer_input(checked), steps=bundle.steps,
                                      states=bundle.states, logs=bundle.logs, files=files)
        except BOB_FAILURES as exc:
            return Round(number, _diag_json(diagnosis), "failed",
                         f"the Diagnosis Reviewer gave no valid answer: {exc}"), checked
        verdict = review.output
        assert isinstance(verdict, ReviewVerdict)
        outcome = "approved" if verdict.verdict == "approve" else "rejected"
        reason = redact_text(verdict.reason.strip())[:EXPLANATION_MAX_CHARS]
        return Round(number, _diag_json(diagnosis), outcome, reason), checked

    async def _finish(self, bundle: EvidenceBundle, checked: CheckedDiagnosis | None, reviewed: bool,
                      rounds: list[Round]) -> DiagnosisResult:
        if checked is None:
            result = DiagnosisResult(
                cx_id=bundle.cx_id, file="", line=None, rounds=rounds,
                explanation=f"No diagnosis passed the engine check in {len(rounds)} rounds. "
                            f"Last problem: {rounds[-1].reason}")
        else:
            explanation = redact_text(checked.explanation)
            if not reviewed:
                explanation += (f" (Not approved by the Diagnosis Reviewer after {len(rounds)} rounds: "
                                f"{rounds[-1].reason})")
            result = DiagnosisResult(cx_id=bundle.cx_id, file=checked.file, line=checked.line,
                                     explanation=explanation, evidence=list(checked.evidence),
                                     reviewed=reviewed, rounds=rounds)
        await self._publish("diagnosis.ready", DiagnosisReady(
            cx_id=result.cx_id, file=result.file, line=result.line, explanation=result.explanation,
            reviewed=result.reviewed))
        return result

    async def _log(self, level: str, text: str) -> None:
        await self._publish("log", Log(level=level, text=text))  # type: ignore[arg-type]

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.client.bus.publish(self.client.run_id, event_type, data)


def _feedback(history: list[Round]) -> str:
    """What went wrong in earlier rounds, for the Detective's next try ("" in the first round)."""
    parts = []
    for r in history:
        answer = json.dumps(r.diagnosis, sort_keys=True, ensure_ascii=False) if r.diagnosis else "(none)"
        parts.append(f"Round {r.number}: {r.outcome}. {r.reason}\nYour answer was: {answer}")
    return "\n\n".join(parts)
