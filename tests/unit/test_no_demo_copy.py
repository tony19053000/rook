"""ROOK-048: the server and session messages a person sees in the web app never say "demo".

API values (`kind: "demo"`), config keys and identifiers are not user-facing and are not checked.
"""

import re

import pytest

from rook.core import session
from rook.sandbox.allowlist import REFUSED_MESSAGE
from rook.server.routes.runs import GUEST_LIMIT_MESSAGE

DEMO_WORD = re.compile(r"\bdemos?\b", re.IGNORECASE)

VISIBLE = {
    "guest limit (HTTP 429)": GUEST_LIMIT_MESSAGE,
    "not allowlisted (HTTP 403, run summary)": REFUSED_MESSAGE,
    "unverified fix (log, run summary)": session._PRISTINE_NOTE,
    "original copy (log)": session._ORIGINAL_COPY_NOTE,
}


def test_the_pattern_catches_the_word_only() -> None:
    assert DEMO_WORD.search("Demo limit reached") and DEMO_WORD.search("two demos")
    assert not DEMO_WORD.search("it demonstrates the bug")


@pytest.mark.parametrize("name", sorted(VISIBLE))
def test_visible_message_has_no_demo_word(name: str) -> None:
    assert not DEMO_WORD.search(VISIBLE[name]), f"{name}: {VISIBLE[name]!r}"
