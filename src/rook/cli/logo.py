"""The ROOK wordmark drawn with box-drawing letters (04_FRONTEND_SPEC.md §2.1)."""

BRAND_COLOR = "#E0563F"
TAGLINE = "find the smallest sequence that breaks your software"
WORD = "ROOK"

# Three rows per letter, same style as the terminal mockup.
LETTERS: dict[str, tuple[str, str, str]] = {
    "R": ("┬─┐", "├┬┘", "┴└─"),
    "O": ("┌─┐", "│ │", "└─┘"),
    "K": ("┬┌─", "├┴┐", "┴ ┴"),
}


def logo_lines(letters: int | None = None) -> list[str]:
    """The three logo rows showing the first `letters` letters (all of them by default)."""
    shown = WORD if letters is None else WORD[: max(0, letters)]
    return [" ".join(LETTERS[ch][row] for ch in shown) for row in range(3)]
