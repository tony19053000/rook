from rook.cli.logo import WORD, logo_lines
from rook.cli.tui import commands
from rook.cli.tui.history import InputHistory


def test_spec_commands_are_all_registered() -> None:
    names = {c.name for c in commands.COMMANDS}
    assert names == {"run", "repo", "rules", "replay", "explain", "verify", "dashboard", "login", "github",
                     "logout", "auto", "help"}


def test_complete_single_match_adds_space() -> None:
    assert commands.complete("/he") == commands.Completion("/help ", ("help",))
    assert commands.complete("/DASH").value == "/dashboard "


def test_complete_several_matches_extends_to_common_prefix() -> None:
    result = commands.complete("/r")
    assert result.value == "/r"
    assert set(result.candidates) == {"run", "repo", "rules", "replay"}
    assert commands.complete("/rep") == commands.Completion("/rep", ("repo", "replay"))
    assert commands.complete("/lo").candidates == ("login", "logout")
    assert commands.complete("/lo").value == "/log"


def test_complete_ignores_non_commands() -> None:
    for text in ("", "find bugs", "/zzz", "/run shop"):
        assert commands.complete(text) == commands.Completion(text, ())


def test_parse_and_validate() -> None:
    assert commands.parse("find bugs") is None
    assert commands.parse("/") is None
    assert commands.parse(" /Run  shop-app ") == commands.Parsed("run", "shop-app")
    assert commands.validate(commands.Parsed("run", "")) is None
    assert "Unknown command /nope" in (commands.validate(commands.Parsed("nope", "")) or "")
    assert commands.validate(commands.Parsed("replay", "")) == "Usage: /replay <cx>"
    assert commands.validate(commands.Parsed("auto", "maybe")) == "Usage: /auto on|off"
    assert commands.validate(commands.Parsed("auto", "on")) is None


def test_help_and_shortcut_lines_fit_80_columns() -> None:
    lines = commands.help_lines() + commands.shortcut_lines()
    assert all(len(line) + 2 <= 78 for line in lines)
    assert any(line.startswith("/run [repo]") for line in commands.help_lines())


def test_history_browse_and_draft() -> None:
    history = InputHistory()
    assert history.previous("x") is None
    for text in ("one", "two", "two", "  "):
        history.add(text)
    assert history.items == ["one", "two"]
    assert history.previous("draft") == "two"
    assert history.previous("two") == "one"
    assert history.previous("one") is None
    assert history.next() == "two"
    assert history.next() == "draft"
    assert history.next() is None


def test_history_limit() -> None:
    history = InputHistory(limit=2)
    for text in ("a", "b", "c"):
        history.add(text)
    assert history.items == ["b", "c"]


def test_logo_reveal() -> None:
    assert logo_lines(0) == ["", "", ""]
    assert logo_lines(1) == ["┬─┐", "├┬┘", "┴└─"]
    full = logo_lines()
    assert full == logo_lines(len(WORD)) and len(full) == 3
    assert all(len(row) == len(full[0]) <= 80 for row in full)
