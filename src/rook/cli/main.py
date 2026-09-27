"""Typer entry point for the `rook` command (04_FRONTEND_SPEC.md §2, 01_PRD.md FR-C5).

`rook` alone opens the interactive shell. `rook run --ci` is the non-interactive run (ci.py). Exit codes of
`run --ci`, `replay` and `verify`: 0 the rule(s) held, 1 a rule is broken, 2 an error or bad arguments.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from rook import __version__
from rook.cli import ci, cx, runs, scaffold
from rook.core.session import SessionOptions

app = typer.Typer(add_completion=False, no_args_is_help=False)
CREDENTIALS = Path.home() / ".rook" / "credentials.json"

RepoOpt = Annotated[Path, typer.Option("--repo", help="The repo folder that holds rook/ (default: here).")]
ModelOpt = Annotated[Path | None, typer.Option("--model", help="The rook.yaml to use (default: <repo>/rook/rook.yaml).")]
BaseUrlOpt = Annotated[str, typer.Option("--base-url", help="Your running app on this machine, e.g. http://127.0.0.1:8000.")]


def _fail(message: str, code: int = 2) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rook {__version__}")
        raise typer.Exit()


def launch_tui(backend: Any) -> None:
    """Open the shell with `backend`, and stop its run (and sandboxes) when the shell quits."""
    from rook.cli.tui.app import run_tui
    from rook.cli.tui.auth import SavedAuth

    try:
        run_tui(backend=backend, auth=SavedAuth(CREDENTIALS))
    finally:
        backend.close()


def _session_backend(**kwargs: Any) -> Any:
    from rook.cli.tui.session_backend import SessionBackend

    return SessionBackend(factory=lambda repo, request, options: runs.build_session(repo, request, options), **kwargs)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Rook: find the smallest sequence of actions that breaks a business rule."""
    if ctx.invoked_subcommand is None:
        launch_tui(_session_backend())


@app.command()
def run(
    repo: Annotated[str, typer.Argument(help="A folder (copied, never changed) or a GitHub owner/name.")] = ".",
    request: Annotated[str, typer.Option("--request", "-r", help="What to look for.")] = "find bugs in my app",
    ci_mode: Annotated[bool, typer.Option("--ci", help="Non-interactive: plain output, reports, exit codes.")] = False,
    auto: Annotated[bool, typer.Option("--auto", help="Answer the questions automatically (see the rails).")] = False,
    budget: Annotated[float, typer.Option("--budget", min=0, help="Bob coin budget for the run.")] = 1.5,
    seed: Annotated[int | None, typer.Option("--seed", help="Search seed (default: random).")] = None,
    sequences: Annotated[int, typer.Option("--sequences", min=1, help="Search budget in sequences.")] = 20_000,
    seconds: Annotated[float, typer.Option("--seconds", min=1, help="Search budget in seconds.")] = 120.0,
    setup: Annotated[list[str] | None, typer.Option(
        "--setup", help="A setup value your app needs, read from the environment variable of that name.")] = None,
    report_dir: Annotated[Path, typer.Option("--report-dir", help="Where --ci writes rook-report.*")] = Path("."),
) -> None:
    """Search a repo for broken business rules (interactive, or --ci)."""
    try:
        spec = runs.parse_repo(repo)
        values = runs.setup_values(setup or [])
    except runs.CliError as exc:
        _fail(str(exc))
    fields: dict[str, Any] = {"auto": auto, "budget": budget, "search_sequences": sequences,
                              "search_seconds": seconds, "setup_values": values}
    if seed is not None:
        fields["seed"] = seed
    options = SessionOptions(**fields)
    if not ci_mode:
        launch_tui(_session_backend(repo=spec.ref, options=options, start_request=request))
        return
    session = runs.build_session(spec, request, options)
    console = ci.plain_console()
    report = asyncio.run(ci.run_ci(session, console, report_dir))
    typer.echo(f"Wrote {report_dir / ci.REPORT_JSON} and {report_dir / ci.REPORT_MD}")
    raise typer.Exit(report.exit_code)


def _cx_command(ref: str, repo: Path, model: Path | None) -> tuple[Any, Any]:
    try:
        return cx.load(ref, repo, model)
    except runs.CliError as exc:
        _fail(str(exc))


def _run_outcome(work: Callable[[], Any]) -> None:
    outcome: cx.Outcome = asyncio.run(work())
    for line in outcome.lines:
        typer.echo(line)
    raise typer.Exit(outcome.code)


@app.command()
def replay(
    cx_ref: Annotated[str, typer.Argument(metavar="CX", help="A counterexample id (cx_001) or its .json file.")],
    base_url: BaseUrlOpt,
    repo: RepoOpt = Path("."),
    model: ModelOpt = None,
    times: Annotated[int, typer.Option("--times", min=1, max=100, help="How many replays.")] = 10,
) -> None:
    """Replay a counterexample against your running app (exit 1 while the rule is still broken)."""
    loaded_model, loaded_cx = _cx_command(cx_ref, repo, model)
    try:
        url, env = runs.check_loopback(base_url), cx.model_env(loaded_model)
    except runs.CliError as exc:
        _fail(str(exc))
    _run_outcome(lambda: cx.replay(loaded_model, loaded_cx, url, env, times))


@app.command()
def verify(
    cx_ref: Annotated[str, typer.Argument(metavar="CX", help="A counterexample id (cx_001) or its .json file.")],
    base_url: BaseUrlOpt,
    repo: RepoOpt = Path("."),
    model: ModelOpt = None,
    sequences: Annotated[int, typer.Option("--sequences", min=1, help="Fresh search budget in sequences.")] = 2_000,
    seconds: Annotated[float, typer.Option("--seconds", min=1, help="Fresh search budget in seconds.")] = 60.0,
) -> None:
    """Check a fix on your running app: the exact replay plus a fresh search (exit 0 when both pass)."""
    loaded_model, loaded_cx = _cx_command(cx_ref, repo, model)
    try:
        url, env = runs.check_loopback(base_url), cx.model_env(loaded_model)
    except runs.CliError as exc:
        _fail(str(exc))
    _run_outcome(lambda: cx.verify(loaded_model, loaded_cx, url, env, sequences=sequences, seconds=seconds))


@app.command()
def explain(
    cx_ref: Annotated[str, typer.Argument(metavar="CX", help="A counterexample id (cx_001) or its .json file.")],
    repo: RepoOpt = Path("."),
    model: ModelOpt = None,
) -> None:
    """Explain a counterexample in plain words: the rule, the minimal steps and what was observed."""
    _, loaded_cx = _cx_command(cx_ref, repo, model)
    for line in cx.explain(loaded_cx):
        typer.echo(line)


@app.command()
def init(
    path: Annotated[Path, typer.Argument(help="The repo folder.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Replace files that already exist.")] = False,
) -> None:
    """Set up a repo: the rook/ folder and a GitHub workflow that runs `rook run --ci`."""
    try:
        written = scaffold.init_repo(path, force=force)
    except FileNotFoundError as exc:
        _fail(str(exc))
    for rel, what in written:
        typer.echo(f"{what:>8}  {rel.as_posix()}")
    typer.echo("Add the BOB_API_KEY secret to your GitHub repo for the workflow.")


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Interface to listen on.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8000,
) -> None:
    """Start the Rook API server (the web app's backend)."""
    import uvicorn

    try:
        from rook.server.app import create_app
    except ImportError as exc:
        _fail(f"the server is not available in this build ({exc})")
    uvicorn.run(create_app, factory=True, host=host, port=port)


@app.command()
def login(
    device: Annotated[bool, typer.Option("--device", help="No browser here: sign in on another device with a code.")] = False,
    server: Annotated[str | None, typer.Option("--server", help="The Rook server (default: ROOK_SERVER or the hosted one).")] = None,
) -> None:
    """Sign in with Google (saved to ~/.rook/credentials.json, readable only by you)."""
    import httpx

    from rook.cli import login as auth

    try:
        base = auth.server_url(server)
        with auth.http_client() as client:
            tokens = (auth.login_with_device_code(base, client, typer.echo) if device
                      else auth.login_in_browser(base, typer.echo))
            email = auth.fetch_email(base, client, tokens.access_token)
    except auth.LoginError as exc:
        _fail(str(exc), 1)
    except httpx.HTTPError as exc:
        _fail(f"could not reach the server ({type(exc).__name__})", 1)
    auth.save_credentials(CREDENTIALS, auth.Credentials(server=base, email=email, access_token=tokens.access_token,
                                                        refresh_token=tokens.refresh_token,
                                                        expires_at=tokens.expires_at))
    typer.echo(f"Signed in as {email or 'your Google account'}.")


@app.command()
def logout() -> None:
    """Sign out: revoke the session on the server and delete the saved credentials on this machine."""
    from rook.cli import login as auth

    if not (CREDENTIALS.is_file() or CREDENTIALS.is_symlink()):
        typer.echo("You were not signed in.")
        return
    creds = auth.load_credentials(CREDENTIALS)
    revoked = False
    if creds is not None:
        try:
            with auth.http_client() as client:
                revoked = auth.revoke(auth.server_url(creds.server), client, creds.access_token)
        except auth.LoginError:
            revoked = False
    CREDENTIALS.unlink()
    typer.echo("Signed out: removed the saved credentials." if revoked
               else "Signed out: removed the saved credentials (the server session could not be revoked; it expires on its own).")
