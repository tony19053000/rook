"""Typer entry point for the `rook` command."""

import typer

from rook import __version__

app = typer.Typer(add_completion=False)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rook {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """Rook: find the smallest sequence of actions that breaks a business rule."""
    if ctx.invoked_subcommand is None:
        typer.echo("Interactive mode coming soon.")
