"""What the CLI needs to start a run: the repo argument, setup values and the Session itself.

`build_session` is the one place the CLI makes a Session (tests replace it with a scripted Bob and an
in-process app). The CLI runs the core in-process (02_ARCHITECTURE.md section 1).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec

_GITHUB = re.compile(r"(?:https://github\.com/)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class CliError(ValueError):
    """A bad argument: shown to the user as one line, exit code 2."""


def parse_repo(ref: str, cwd: Path | None = None) -> RepoSpec:
    """A local folder (copied, never written to), else a GitHub `owner/name` or github.com URL."""
    path = Path(ref).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    if path.is_dir():
        path = path.resolve()
        if path == Path(path.anchor) or path == Path.home().resolve():
            raise CliError(f"{path} is too broad to copy; run Rook inside a project folder")
        return RepoSpec(kind="local", ref=str(path))
    match = _GITHUB.fullmatch(ref.strip())
    if match and not ref.startswith((".", "/", "~")):
        return RepoSpec(kind="github", ref=match.group(1))
    raise CliError(f"{ref!r} is not a folder or a GitHub repo (owner/name)")


def setup_values(names: Iterable[str], environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """`--setup NAME` takes the value from the environment variable NAME (never from argv, which `ps`
    shows)."""
    env = os.environ if environ is None else environ
    values: dict[str, str] = {}
    for name in names:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise CliError(f"--setup takes an environment variable name, not {name!r}")
        if not env.get(name):
            raise CliError(f"--setup {name}: the environment variable {name} is not set")
        values[name] = env[name]
    return values


def check_loopback(base_url: str) -> str:
    """The URL of an app the user runs on this machine. Rook sends HTTP only to the target app, so
    anything that is not a loopback http(s) URL is refused."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in LOOPBACK_HOSTS:
        raise CliError(f"--base-url must be your app on this machine (http://127.0.0.1:PORT), not {base_url!r}")
    if parsed.username or parsed.password:
        raise CliError("--base-url must not contain credentials")
    return base_url.rstrip("/")


CREDENTIALS = Path.home() / ".rook" / "credentials.json"


def build_session(repo: RepoSpec, request: str, options: SessionOptions) -> Session:
    """A GitHub repo gets a token from the Rook server (for the clone) and ships with a push + PR; a local
    folder ships to a local branch only."""
    if repo.kind != "github":
        return Session(repo, request, options)
    from rook.cli.github import GitHubTokenError, ServerTokens
    from rook.github.pr import GitHubShipper

    tokens = ServerTokens(repo.ref, CREDENTIALS)
    try:
        token = tokens.fetch()
    except GitHubTokenError as exc:
        raise CliError(str(exc)) from None
    return Session(repo, request, options, token=token, shipper=GitHubShipper(repo.ref, tokens, base=repo.branch))
