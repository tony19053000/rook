from typer.testing import CliRunner

import rook
from rook.cli.main import app

runner = CliRunner()


def test_version_is_importable() -> None:
    assert rook.__version__ == "0.1.0"


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "rook 0.1.0"


def test_cli_no_args_prints_placeholder() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "coming soon" in result.output
