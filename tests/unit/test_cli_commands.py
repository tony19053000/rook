"""ROOK-024: every `rook` command and its flags, through Typer's CliRunner.

`run --ci` end to end is in test_cli_ci.py. replay/verify run the real engine against minishop in-process
(the executor factory is swapped for an in-process transport); nothing here needs Docker or Bob.
"""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from test_export import found_cx
from test_shrinker import BASE, FIXTURE_DIR, minishop
from typer.testing import CliRunner

from rook.cli import cx as cx_cli
from rook.cli import main as cli_main
from rook.cli.main import app
from rook.cli.runs import CliError, check_loopback, parse_repo, setup_values
from rook.cli.scaffold import README_PATH, WORKFLOW_PATH
from rook.cli.tui.session_backend import SessionBackend
from rook.engine.executor import Executor
from rook.engine.inprocess import InProcessTransport
from rook.export.counterexample import Counterexample

runner = CliRunner()
URL = "http://127.0.0.1:8000"


class Launched:
    """Stands in for the Textual shell: records the backend it was given."""

    def __init__(self) -> None:
        self.backends: list[Any] = []

    def __call__(self, backend: Any) -> None:
        self.backends.append(backend)


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> Launched:
    launch = Launched()
    monkeypatch.setattr(cli_main, "launch_tui", launch)
    return launch


# --- rook, --version, run -------------------------------------------------------------------------------


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and result.output.strip() == "rook 0.1.0"


def test_bare_rook_opens_the_shell_with_a_session_backend(launched: Launched) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    (backend,) = launched.backends
    assert isinstance(backend, SessionBackend) and backend.session is None and not backend.running


def test_launch_tui_builds_the_wired_app_and_closes_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr("rook.cli.tui.app.RookApp.run", lambda self: seen.append(self))

    class Backend:
        closed = False

        def close(self) -> None:
            self.closed = True

    backend = Backend()
    cli_main.launch_tui(backend)
    (shell,) = seen
    assert shell.backend is backend and backend.closed
    assert shell.views["question.asked"].__module__ == "rook.cli.tui.widgets.prompts"  # prompts registered


def test_run_without_ci_starts_the_run_in_the_shell(tmp_path: Path, launched: Launched) -> None:
    result = runner.invoke(app, ["run", str(tmp_path), "-r", "check refunds", "--auto", "--budget", "0.5",
                                 "--seed", "7", "--sequences", "100", "--seconds", "5"])
    assert result.exit_code == 0, result.output
    (backend,) = launched.backends
    assert backend.repo == str(tmp_path.resolve()) and backend._start_request == "check refunds"
    opts = backend.options
    assert (opts.auto, opts.budget, opts.seed, opts.search_sequences, opts.search_seconds) == (True, 0.5, 7, 100, 5.0)


@pytest.mark.parametrize("args", [["run", "/definitely/not/here"], ["run", "a/b/c/d"], ["run", ".", "--budget", "-1"],
                                  ["run", ".", "--sequences", "0"], ["run", ".", "--setup", "bad name"]])
def test_run_rejects_bad_arguments(args: list[str], launched: Launched) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert launched.backends == []


def test_parse_repo(tmp_path: Path) -> None:
    assert parse_repo(str(tmp_path)).kind == "local"
    (tmp_path / "sub").mkdir()
    assert parse_repo("sub", tmp_path).ref == str((tmp_path / "sub").resolve())
    assert parse_repo("octo/shop").model_dump(exclude_none=True) == {"kind": "github", "ref": "octo/shop"}
    assert parse_repo("https://github.com/octo/shop.git").ref == "octo/shop"
    for bad in ("/", str(Path.home()), "./missing", "not a repo"):
        with pytest.raises(CliError):
            parse_repo(bad)


def test_setup_values_and_loopback() -> None:
    assert setup_values(["A_KEY"], {"A_KEY": "v"}) == {"A_KEY": "v"}
    for names in (["A_KEY"], ["a-b"]):
        with pytest.raises(CliError):
            setup_values(names, {})
    assert check_loopback("http://localhost:3000/") == "http://localhost:3000"
    for url in ("http://example.com", "file:///etc/passwd", "http://10.0.0.1:80", "http://u:p@127.0.0.1:1",
                "ftp://127.0.0.1"):
        with pytest.raises(CliError):
            check_loopback(url)


# --- replay, verify, explain ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cx() -> Counterexample:
    return asyncio.run(found_cx())


@pytest.fixture
def repo(tmp_path: Path, cx: Counterexample, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "rook" / "counterexamples").mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "rook.yaml", tmp_path / "rook" / "rook.yaml")
    (tmp_path / "rook" / "counterexamples" / "cx_001.json").write_text(cx.to_json())
    monkeypatch.setenv("ROOK_ENV_MINISHOP_ADMIN_PASSWORD", "admin-pass")  # the fixture's default
    return tmp_path


def serve_minishop(monkeypatch: pytest.MonkeyPatch, *, fixed: bool) -> list[str]:
    urls: list[str] = []

    def make(model: Any, base_url: str, env: Any) -> Executor:
        urls.append(base_url)
        return Executor(model, BASE, transport=InProcessTransport(minishop.create_app(fixed=fixed)), env=env)

    monkeypatch.setattr(cx_cli, "make_executor", make)
    return urls


def test_replay_exits_1_while_the_rule_is_broken(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    urls = serve_minishop(monkeypatch, fixed=False)
    result = runner.invoke(app, ["replay", "cx_001", "--repo", str(repo), "--base-url", URL + "/", "--times", "3"])
    assert result.exit_code == 1, result.output
    assert "✗ rule refund_le_paid broken in 3/3 replays" in result.output
    assert urls == [URL]


def test_replay_exits_0_on_the_fixed_app_and_takes_a_file(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_minishop(monkeypatch, fixed=True)
    path = repo / "rook" / "counterexamples" / "cx_001.json"
    result = runner.invoke(app, ["replay", str(path), "--repo", str(repo), "--base-url", URL, "--times", "2"])
    assert result.exit_code == 0, result.output
    assert "✓ rule refund_le_paid held in 2/2 replays" in result.output


@pytest.mark.parametrize("args", [
    ["replay", "cx_001", "--base-url", "http://example.com"],   # not the user's own app
    ["replay", "cx_999", "--base-url", URL],                    # no such counterexample
    ["replay", "../../etc/passwd", "--base-url", URL],          # not an id or a .json file
    ["replay", "cx_001"],                                       # --base-url is required
    ["replay", "cx_001", "--base-url", URL, "--times", "0"],
    ["verify", "cx_001", "--base-url", "http://192.168.1.2:80"],
    ["explain", "cx_002"],
])
def test_cx_commands_reject_bad_arguments(repo: Path, args: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    urls = serve_minishop(monkeypatch, fixed=False)
    result = runner.invoke(app, [*args, "--repo", str(repo)])
    assert result.exit_code == 2, result.output
    assert urls == []  # no request was sent anywhere


def test_replay_needs_the_model_env(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_minishop(monkeypatch, fixed=False)
    monkeypatch.delenv("ROOK_ENV_MINISHOP_ADMIN_PASSWORD")
    result = runner.invoke(app, ["replay", "cx_001", "--repo", str(repo), "--base-url", URL])
    assert result.exit_code == 2 and "ROOK_ENV_MINISHOP_ADMIN_PASSWORD" in result.output


def test_replay_with_an_explicit_model(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_minishop(monkeypatch, fixed=False)
    model = repo / "other.yaml"
    (repo / "rook" / "rook.yaml").rename(model)
    args = ["replay", "cx_001", "--repo", str(repo), "--base-url", URL, "--times", "1"]
    assert runner.invoke(app, args).exit_code == 2  # the default model is gone
    assert runner.invoke(app, [*args, "--model", str(model)]).exit_code == 1


def test_verify_on_the_fixed_and_the_buggy_app(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    serve_minishop(monkeypatch, fixed=True)
    args = ["verify", "cx_001", "--repo", str(repo), "--base-url", URL, "--sequences", "200", "--seconds", "30"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "✓ replay: rule refund_le_paid held" in result.output and "✓ fresh search: no violation" in result.output
    assert "not run here" in result.output
    serve_minishop(monkeypatch, fixed=False)
    result = runner.invoke(app, args)
    assert result.exit_code == 1, result.output
    assert "✗ replay: rule refund_le_paid still broken" in result.output and "✗ Not verified" in result.output


def test_explain(repo: Path, cx: Counterexample) -> None:
    result = runner.invoke(app, ["explain", "cx_001", "--repo", str(repo)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert out.startswith("Counterexample cx_001\nRule refund_le_paid: ")
    assert "Minimal steps:" in out and f"Reproduced {cx.reproduced} on the real app" in out
    assert f"  {len(cx.steps)}. " in out


# --- init, serve, login, logout ---------------------------------------------------------------------------


def test_init_writes_the_starter_files_once(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    workflow = (tmp_path / WORKFLOW_PATH).read_text()
    assert "rook run . --ci --auto" in workflow and "${{ secrets.BOB_API_KEY }}" in workflow
    assert (tmp_path / README_PATH).is_file() and (tmp_path / "rook" / "counterexamples").is_dir()
    assert "created  .github/workflows/rook.yml" in result.output
    (tmp_path / WORKFLOW_PATH).write_text("mine")
    again = runner.invoke(app, ["init", str(tmp_path)])
    assert "kept  .github/workflows/rook.yml" in again.output and (tmp_path / WORKFLOW_PATH).read_text() == "mine"
    forced = runner.invoke(app, ["init", str(tmp_path), "--force"])
    assert "replaced  .github/workflows/rook.yml" in forced.output
    assert runner.invoke(app, ["init", str(tmp_path / "missing")]).exit_code == 2


def test_init_never_writes_through_a_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    repo = tmp_path / "repo"
    (repo / "rook").mkdir(parents=True)
    (repo / README_PATH).symlink_to(outside)
    runner.invoke(app, ["init", str(repo), "--force"])
    assert outside.read_text() == "keep"


def test_serve_starts_uvicorn_with_the_app_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setattr("uvicorn.run", lambda target, **kw: calls.append((target, kw)))
    result = runner.invoke(app, ["serve", "--port", "9123"])
    assert result.exit_code == 0, result.output
    (target, kw) = calls[0]
    assert target.__name__ == "create_app" and kw == {"factory": True, "host": "127.0.0.1", "port": 9123}
    assert runner.invoke(app, ["serve", "--port", "0"]).exit_code == 2


def test_logout_deletes_the_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    creds = tmp_path / "credentials.json"
    creds.write_text(json.dumps({"token": "x"}))
    monkeypatch.setattr(cli_main, "CREDENTIALS", creds)
    result = runner.invoke(app, ["logout"])
    assert result.exit_code == 0 and "Signed out" in result.output and not creds.exists()
    assert "not signed in" in runner.invoke(app, ["logout"]).output
