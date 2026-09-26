"""A minimal JSONPath subset for `capture` and `fields` in rook.yaml.

Supported: `$`, `$.a.b`, `$.a[0]`, `$.a[-1]`, `$.items[*].id` (a wildcard returns a list).
A path that does not resolve returns None.
"""

import re
from functools import lru_cache
from typing import Any

_WILDCARD = object()
_SEGMENT = re.compile(r"\.([A-Za-z_][A-Za-z0-9_-]*)|\[(-?\d+|\*)\]")

Segment = str | int | object


class JSONPathError(ValueError):
    """Raised when a JSONPath expression is not in the supported subset."""


@lru_cache(maxsize=512)
def compile_path(expr: str) -> tuple[Segment, ...]:
    if not isinstance(expr, str) or not expr.startswith("$"):
        raise JSONPathError(f"JSONPath must start with '$': {expr!r}")
    segments: list[Segment] = []
    pos = 1
    while pos < len(expr):
        match = _SEGMENT.match(expr, pos)
        if match is None:
            raise JSONPathError(f"unsupported JSONPath {expr!r} at position {pos}")
        name, index = match.groups()
        if name is not None:
            segments.append(name)
        elif index == "*":
            segments.append(_WILDCARD)
        else:
            segments.append(int(index))
        pos = match.end()
    return tuple(segments)


def _resolve(data: Any, segments: tuple[Segment, ...]) -> tuple[bool, Any]:
    """Return (found, value). Missing keys, bad indexes and type mismatches are 'not found'."""
    current = data
    for i, seg in enumerate(segments):
        if seg is _WILDCARD:
            if not isinstance(current, list):
                return False, None
            rest = segments[i + 1 :]
            results = []
            for item in current:
                found, value = _resolve(item, rest)
                if found:
                    results.append(value)
            return True, results
        if isinstance(seg, int):
            if not isinstance(current, list) or not -len(current) <= seg < len(current):
                return False, None
            current = current[seg]
        else:
            if not isinstance(current, dict) or seg not in current:
                return False, None
            current = current[seg]
    return True, current


def extract(data: Any, expr: str) -> Any:
    """Evaluate `expr` against `data`; returns None if the path does not resolve."""
    found, value = _resolve(data, compile_path(expr))
    return value if found else None
