"""Deterministic masks for volatile app values in what Bob sees (02 section 5.1).

A recording's key is the prompt, so a prompt must not change from run to run for the same counterexample.
App responses and logs hold values that do: bearer tokens and session secrets, timestamps, random ids
(uuid4, long random hex or base64) and the random `fresh` values Rook itself sends. They are replaced by
fixed labels: `<time>`, and numbered labels (`<token#1>`, `<uuid#2>`, `<random#1>`) that keep equality
(the same token twice is `<token#1>` twice) because the equality of random values does not depend on
the run. Everything else stays as it is: money amounts, counts, statuses, booleans and nulls are
evidence. Times are not numbered: two entities made in the same second may or may not share a stamp.

Only what the agents see is masked; the engine always executes and judges the real values.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Any

TIME = "<time>"

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN_KEY = re.compile(
    r"^(?:.*_)?(?:token|jwt|authorization|auth|bearer|api_?key|secret|password|passwd|cookie|set_cookie"
    r"|session|session_id|sid|csrf|xsrf|nonce|signature|otp)$"
)
_TIME_KEY = re.compile(
    r"^(?:.*_)?(?:at|time|timestamp|ts|date|datetime|created|updated|modified|deleted|expires|expiry"
    r"|expiration|exp|iat|nbf|last_seen|last_login)$"
)

_ISO = r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
_RFC1123 = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} (?:GMT|UTC|[+-]\d{4})"
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_JWT = r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"

_ISO_FULL = re.compile(_ISO)
_RFC1123_FULL = re.compile(_RFC1123)
_UUID_FULL = re.compile(_UUID)
_JWT_FULL = re.compile(_JWT)
_BEARER_FULL = re.compile(r"(?i)(bearer|token|basic)\s+(\S+)")
_WORD = re.compile(r"[A-Za-z0-9_\-+/=]{16,}")

# Free text (logs, error messages): the order matters (whole timestamps before bare clock times).
_TEXT_FIXED = (
    (re.compile(r"\b" + _ISO), TIME),
    (re.compile(_RFC1123), TIME),
    (re.compile(r"\[\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}\]"), f"[{TIME}]"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), TIME),
    (re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|localhost|\[[0-9a-fA-F:]*\]):\d{1,5}\b"), "<addr>"),
    (re.compile(r"(?i)\b(pid[ =:]?|process \[)\d+"), r"\1<pid>"),
    (re.compile(r"/tmp/[^\s\"':,)]+"), "<tmp>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?ms\b"), "<ms>"),
)
_TEXT_BEARER = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9\-._~+/]+=*)")
_TEXT_JWT = re.compile(r"\b" + _JWT)
_TEXT_UUID = re.compile(r"\b" + _UUID + r"\b")
_TEXT_KEY_VALUE = re.compile(
    r"""(?i)(["']?[A-Za-z_-]*(?:token|secret|password|api_?key|session_?id|cookie)["']?\s*[:=]\s*["']?)"""
    r"""(?!bearer\b|basic\b|<)([^\s"',;}&<]+)"""
)
_TEXT_WORD = re.compile(r"(?<![A-Za-z0-9_\-+/=<])[A-Za-z0-9_\-+/=]{16,}(?![A-Za-z0-9_\-+/=>])")


def snake(key: str) -> str:
    """`createdAt` / `created-at` / `CreatedAt` -> `created_at`."""
    return _CAMEL.sub("_", key).replace("-", "_").lower()


def is_token_key(key: str) -> bool:
    return bool(_TOKEN_KEY.match(snake(key)))


def is_time_key(key: str) -> bool:
    return bool(_TIME_KEY.match(snake(key)))


def looks_random(word: str) -> bool:
    """A long word that reads like random bytes: hex of 24+ characters, or base64 / base64url of 20+ with
    letters and digits interleaved (so `SuperLongProductName2024` or `refund_le_paid_total` are kept)."""
    if len(word) < 16:
        return False
    core = word.rstrip("=")
    if len(core) >= 24 and re.fullmatch(r"[0-9a-fA-F]+", core) and re.search(r"\d", core) \
            and re.search(r"[a-fA-F]", core):
        return True
    if len(core) < 20 or not re.fullmatch(r"[A-Za-z0-9_\-+/]+", core):
        return False
    digits = sum(c.isdigit() for c in core)
    letters = sum(c.isalpha() for c in core)
    if digits < 3 or letters < 3:
        return False
    switches = sum(1 for a, b in pairwise(core) if a.isdigit() != b.isdigit())
    return switches >= max(5, len(core) // 6)


class Masker:
    """Masks volatile values in app data (`value`) and free text (`text`). Numbered labels count from 1
    per kind in order of first appearance, so use ONE Masker for everything one prompt shows."""

    def __init__(self, fresh: tuple[str, ...] = ()) -> None:
        """`fresh`: the random tokens Rook put into this replay's `fresh` values (shown as `<fresh>`)."""
        self.fresh: tuple[str, ...] = ()
        for token in fresh:
            self.add_fresh(token)
        self._labels: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def add_fresh(self, token: str) -> None:
        if len(token) >= 4 and token not in self.fresh:
            self.fresh = tuple(sorted({*self.fresh, token}, key=len, reverse=True))

    def label(self, kind: str, raw: str) -> str:
        key = (kind, raw)
        if key not in self._labels:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._labels[key] = f"<{kind}#{self._counts[kind]}>"
        return self._labels[key]

    # --- app data (JSON-like) ---

    def value(self, value: Any, key: str = "") -> Any:
        """`value` with volatile leaves masked. `key` is the field the value sits in (its context)."""
        if isinstance(value, dict):
            return {self._key(k): self.value(v, str(k)) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.value(v, key) for v in value]
        if isinstance(value, bool) or value is None:
            return value
        if key and is_time_key(key) and isinstance(value, str | int | float):
            return TIME
        if isinstance(value, str):
            if key and is_token_key(key) and value:
                return self.label("token", value)
            return self.string(value)
        return value

    def _key(self, key: Any) -> Any:
        return self.string(key) if isinstance(key, str) else key

    def string(self, text: str) -> str:
        """One string value: a whole-value timestamp, token, uuid or random word is masked; in a longer
        string only Rook's fresh values are."""
        if _ISO_FULL.fullmatch(text) or _RFC1123_FULL.fullmatch(text):
            return TIME
        if _JWT_FULL.fullmatch(text):
            return self.label("token", text)
        if m := _BEARER_FULL.fullmatch(text):
            return f"{m.group(1)} {self.label('token', m.group(2))}"
        if _UUID_FULL.fullmatch(text):
            return self.label("uuid", text.lower())
        masked = self._fresh(text)
        if masked != text:  # Rook's own fresh value inside a longer word (a slug): always `<fresh>`
            return masked
        if _WORD.fullmatch(text) and looks_random(text):
            return self.label("random", text)
        return text

    def _fresh(self, text: str) -> str:
        for token in self.fresh:
            text = text.replace(token, "<fresh>")
        return text

    # --- free text ---

    def text(self, text: str) -> str:
        """Free text (a log line, an error message) with volatile bits masked in place."""
        text = self._fresh(text)
        for pattern, mask in _TEXT_FIXED:
            text = pattern.sub(mask, text)
        text = _TEXT_BEARER.sub(lambda m: f"{m.group(1)} {self.label('token', m.group(2))}", text)
        text = _TEXT_JWT.sub(lambda m: self.label("token", m.group(0)), text)
        text = _TEXT_KEY_VALUE.sub(lambda m: m.group(1) + self.label("token", m.group(2)), text)
        text = _TEXT_UUID.sub(lambda m: self.label("uuid", m.group(0).lower()), text)
        return _TEXT_WORD.sub(lambda m: self.label("random", m.group(0)) if looks_random(m.group(0))
                              else m.group(0), text)


def mask_text(text: str) -> str:
    """`text` masked on its own (numbering starts at 1)."""
    return Masker().text(text)
