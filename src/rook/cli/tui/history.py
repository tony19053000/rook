"""Input history for the prompt (↑/↓ when no menu is open)."""

from __future__ import annotations


class InputHistory:
    def __init__(self, limit: int = 200) -> None:
        self._items: list[str] = []
        self._limit = limit
        self._index: int | None = None  # None: not browsing
        self._draft = ""

    @property
    def items(self) -> list[str]:
        return list(self._items)

    def add(self, text: str) -> None:
        """Remember a sent line (skipping blanks and repeats) and stop browsing."""
        self._index = None
        if text.strip() and (not self._items or self._items[-1] != text):
            self._items.append(text)
            del self._items[: -self._limit]

    def previous(self, current: str) -> str | None:
        """The older entry, or None when there is nothing older. Saves `current` as the draft."""
        if not self._items:
            return None
        if self._index is None:
            self._draft = current
            self._index = len(self._items)
        if self._index == 0:
            return None
        self._index -= 1
        return self._items[self._index]

    def next(self) -> str | None:
        """The newer entry; past the newest, the saved draft. None when not browsing."""
        if self._index is None:
            return None
        self._index += 1
        if self._index >= len(self._items):
            self._index = None
            return self._draft
        return self._items[self._index]
