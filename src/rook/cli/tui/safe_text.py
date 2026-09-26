"""Make untrusted strings (event payloads, Bob output) safe to draw in the terminal.

Rich Text passes C0/C1 control characters straight through, so an ESC or OSC sequence echoed from a repo
could recolour, retitle or rewrite the user's terminal. Every event-derived string goes through `clean`.
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"[\t\n\r\v\f]")
_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(text: str) -> str:
    """One display line: line breaks and tabs become spaces; other C0, DEL and C1 controls are dropped."""
    return _CONTROLS.sub("", _WHITESPACE.sub(" ", text))
