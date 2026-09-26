from typing import Any

import pytest
from typer.testing import CliRunner

import rook
from rook.cli import main as cli_main
from rook.cli.main import app

runner = CliRunner()


def test_version_is_importable() -> None:
    assert rook.__version__ == "0.1.0"


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "rook 0.1.0"


def test_cli_no_args_opens_the_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Any] = []
    monkeypatch.setattr(cli_main, "launch_tui", opened.append)
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert len(opened) == 1


def test_cli_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "replay", "explain", "verify", "init", "serve", "login", "logout"):
        assert command in result.output
