"""Tiny `{{name.path}}` renderer for rook.yaml request templates (no Jinja).

The context is a mapping such as
`{"p": {...}, "ref": {...}, "fresh": {...}, "env": {...}, "actor": {...}, "sandbox": {...}, "order_id": 7}`.
A string that is exactly one placeholder keeps the value's native type; placeholders embedded in a
longer string are converted to text (strings as-is, everything else as JSON).

Strings are tokenized in one left-to-right pass with `str.find`, so the cost is linear in the input
(the model comes from Bob-written YAML and must not be able to stall the loader).
"""

import json
import re
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

MAX_DEPTH = 100

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


class TemplateError(ValueError):
    """Raised for malformed placeholders, missing variables or structures nested too deeply."""


class _Var(str):
    """A placeholder name inside a parsed template (literal text stays a plain `str`)."""


def _snippet(text: str) -> str:
    return repr(text if len(text) <= 80 else text[:77] + "...")


@lru_cache(maxsize=2048)
def _parse(text: str) -> tuple[str, ...]:
    """Split `text` into literal `str` parts and `_Var` names. Raises TemplateError on bad syntax."""
    parts: list[str] = []
    pos = 0
    while True:
        start = text.find("{{", pos)
        stray = text.find("}}", pos, len(text) if start < 0 else start)
        if stray >= 0:
            raise TemplateError(f"unbalanced '}}}}' at position {stray} in {_snippet(text)}")
        if start < 0:
            break
        end = text.find("}}", start + 2)
        if end < 0:
            raise TemplateError(f"unclosed '{{{{' at position {start} in {_snippet(text)}")
        inner = text[start + 2 : end].strip()
        if not _NAME.fullmatch(inner):
            raise TemplateError(
                f"malformed placeholder {_snippet(text[start : end + 2])} in {_snippet(text)}"
            )
        if start > pos:
            parts.append(text[pos:start])
        parts.append(_Var(inner))
        pos = end + 2
    if pos < len(text):
        parts.append(text[pos:])
    return tuple(parts)


def _too_deep() -> TemplateError:
    return TemplateError(f"template structure is nested deeper than {MAX_DEPTH} levels")


def placeholders(obj: Any, _depth: int = 0) -> set[str]:
    """All placeholder names used in `obj` (strings, dicts and lists, recursively)."""
    if _depth > MAX_DEPTH:
        raise _too_deep()
    if isinstance(obj, str):
        return {p for p in _parse(obj) if isinstance(p, _Var)}
    if isinstance(obj, Mapping):
        return set().union(*(placeholders(v, _depth + 1) for v in obj.values()))
    if isinstance(obj, list | tuple):
        return set().union(*(placeholders(v, _depth + 1) for v in obj))
    return set()


def lookup(name: str, context: Mapping[str, Any]) -> Any:
    current: Any = context
    walked: list[str] = []
    for part in name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            where = ".".join(walked) or "context"
            available = sorted(current) if isinstance(current, Mapping) else []
            raise TemplateError(
                f"unknown template variable '{{{{{name}}}}}': '{part}' not found in {where}"
                + (f" (available: {', '.join(map(str, available))})" if available else "")
            )
        current = current[part]
        walked.append(part)
    return current


def _to_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _render_str(text: str, context: Mapping[str, Any]) -> Any:
    parts = _parse(text)
    if len(parts) == 1 and isinstance(parts[0], _Var):
        return lookup(parts[0], context)
    return "".join(_to_text(lookup(p, context)) if isinstance(p, _Var) else p for p in parts)


def render(obj: Any, context: Mapping[str, Any], _depth: int = 0) -> Any:
    """Render every placeholder in `obj`. Dict keys are not rendered."""
    if _depth > MAX_DEPTH:
        raise _too_deep()
    if isinstance(obj, str):
        return _render_str(obj, context)
    if isinstance(obj, Mapping):
        return {k: render(v, context, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, context, _depth + 1) for v in obj]
    return obj
