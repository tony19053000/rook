"""PREPARE and SHIP's git side: the run's workspace copy, and the verified fix committed to a branch.

PREPARE (02 section 4, 03 sections 3-4) makes `<root>/<run_id>/`, the only folder Bob and the sandbox
ever touch:
- local folder: a plain copy of the folder (without `.git`, caches and dependency folders), then a
  fresh git repo with one baseline commit. The user's folder (and its `.git`) is never written to;
- GitHub: `git clone` over HTTPS. The installation token goes to git only through the child env (as an
  `http.extraheader` config value), so it is never in argv, in `.git/config`, in events or in logs;
- demo: only allowlisted repos (`sandbox/allowlist.py`), copied from their pre-installed folder. The
  hosted server runs nothing else (`hosted=True` refuses every other kind).

SHIP in test mode (`LocalBranchShipper`) commits the verified fix, the regression test and Rook's files
to a new local branch `rook/fix-<cx>` and never pushes. The real push + PR (`github/pr.py`, ROOK-031)
implements the same `Shipper` interface. Git always runs with an arg list, a minimal env, no user or system config and
no hooks (the workspace is untrusted).

Symlinks (03 section 3): Bob runs on the host with the workspace as cwd, so no link in the workspace may
lead outside it. A copy drops every link that escapes the source root (absolute or `../` targets, chains,
directory links), every dangling or looping link, and every special file, each with a warning; a link
that stays inside is re-created as a relative link to its final target. A GitHub clone checks links out
as plain files (`core.symlinks=false`), then the same scan removes any escaping link that is left.

PREPARE can be cancelled: `cancel` (a threading.Event) stops the copy between entries and kills a running
git process group, and the half-made workspace is removed.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from rook.core.events import redact_text, register_secret
from rook.sandbox.allowlist import (
    DEFAULT_ALLOWLIST,
    REFUSED_MESSAGE,
    Allowlist,
    AllowlistEntry,
    NotAllowlistedError,
)

log = logging.getLogger(__name__)

DEFAULT_ROOT = Path.home() / ".rook" / "workspaces"
GITHUB_URL = "https://github.com"
GIT_TIMEOUT = 300.0
_RUN_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"  # base32
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_BRANCH_RE = re.compile(r"[A-Za-z0-9._/-]{1,100}")
# Never copied into the workspace: VCS data, Rook/Bob state, caches and installed dependencies.
COPY_IGNORE = (".git", ".bob", ".rook", ".rook-sandbox", "__pycache__", ".pytest_cache", ".mypy_cache",
               ".ruff_cache", ".tox", ".venv", "venv", "node_modules")
_GIT_CONFIG = ("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
               "-c", "user.name=Rook", "-c", "user.email=rook@localhost", "-c", "init.defaultBranch=main",
               "-c", "core.fsmonitor=false", "-c", "protocol.ext.allow=never")

RepoKind = Literal["local", "github", "demo"]


def new_run_id() -> str:
    """`r_` + 12 random base32 characters (03 section 7)."""
    return "r_" + "".join(secrets.choice(_RUN_ALPHABET) for _ in range(12))


class RepoSpec(BaseModel):
    """What to run on. local: `ref` is a folder; github: `ref` is `owner/name` (+ optional `branch`);
    demo: `ref` is `owner/name` and `commit` the pinned SHA of an allowlisted demo repo."""

    model_config = ConfigDict(extra="forbid")

    kind: RepoKind
    ref: str
    commit: str | None = None
    branch: str | None = None

    @field_validator("branch")
    @classmethod
    def _branch(cls, v: str | None) -> str | None:
        if v is not None and (not _BRANCH_RE.fullmatch(v) or v.startswith(("-", "/")) or ".." in v):
            raise ValueError(f"invalid branch name {v!r}")
        return v

    @property
    def name(self) -> str:
        return Path(self.ref).name if self.kind == "local" else self.ref.rsplit("/", 1)[-1]


class PrepareError(RuntimeError):
    """The workspace could not be prepared."""


class PrepareCancelled(PrepareError):
    """The run was cancelled while its workspace was being prepared."""


class GitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Workspace:
    path: Path
    repo: RepoSpec
    base_commit: str  # the workspace's HEAD after PREPARE
    demo: AllowlistEntry | None = None  # the allowlist entry of a demo repo
    skipped: tuple[str, ...] = ()  # repo-relative paths left out for safety (escaping links, special files)


def git(cwd: Path, *args: str, env: dict[str, str] | None = None, timeout: float = GIT_TIMEOUT,
        cancel: threading.Event | None = None) -> str:
    """Run git in `cwd` with a minimal env (no user/system config, no prompts, no hooks). Returns stdout.

    `env` adds values (e.g. a token header) that must never go into argv. Git runs in its own process
    group, which is killed on a timeout or when `cancel` is set (PrepareCancelled)."""
    child_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/false",
        **(env or {}),
    }
    try:
        proc = subprocess.Popen(["git", *_GIT_CONFIG, *args], cwd=cwd, env=child_env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
    except OSError as exc:
        raise GitError(redact_text(f"git {args[0]} failed: {exc}")) from exc
    deadline = time.monotonic() + timeout
    while True:
        try:
            out, err = proc.communicate(timeout=0.05)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                _kill_group(proc)
                raise PrepareCancelled("the run was cancelled") from None
            if time.monotonic() > deadline:
                _kill_group(proc)
                raise GitError(f"git {args[0]} failed: timed out after {timeout:g} s") from None
        except BaseException:
            _kill_group(proc)
            raise
    if proc.returncode != 0:
        tail = " ".join((err or out).split())[-300:]
        raise GitError(redact_text(f"git {args[0]} failed (exit {proc.returncode}): {tail}"))
    return out.strip()


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """Kill git and every helper it started (e.g. git-remote-https), then reap it."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.communicate()


def _init_baseline(ws: Path, name: str, cancel: threading.Event | None = None) -> str:
    git(ws, "init", "-q", cancel=cancel)
    git(ws, "add", "-A", cancel=cancel)
    git(ws, "commit", "-q", "--allow-empty", "-m", f"rook: baseline copy of {name}", cancel=cancel)
    return git(ws, "rev-parse", "HEAD", cancel=cancel)


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise PrepareCancelled("the run was cancelled")


def _inside_target(link: str, root: str) -> str | None:
    """The final target of `link` (every link in a chain followed) if it exists and is inside `root`."""
    try:
        target = os.path.realpath(link, strict=True)  # OSError for a dangling or looping link
    except OSError:
        return None
    return target if target == root or target.startswith(root + os.sep) else None


def _skip(skipped: list[str], rel: str, why: str) -> None:
    log.warning("PREPARE: left out %r: %s", rel, why)
    skipped.append(rel)


def _copy(src: Path, ws: Path, cancel: threading.Event | None = None) -> list[str]:
    """Copy the folder `src` to the new folder `ws` without COPY_IGNORE names. Links are never followed:
    one that stays inside `src` becomes a relative link to its final target; any other link and every
    special file (FIFO, socket, device) is left out. Returns the repo-relative paths left out."""
    root = os.path.realpath(src)
    skipped: list[str] = []

    def walk(rel: str) -> None:
        here = os.path.join(root, rel) if rel else root
        os.mkdir(os.path.join(ws, rel) if rel else ws, mode=0o700)
        with os.scandir(here) as it:
            entries = sorted(it, key=lambda e: e.name)
        for entry in entries:
            _check_cancel(cancel)
            if entry.name in COPY_IGNORE:
                continue
            sub = os.path.join(rel, entry.name) if rel else entry.name
            dst = os.path.join(ws, sub)
            if entry.is_symlink():
                target = _inside_target(entry.path, root)
                if target is None:
                    _skip(skipped, sub, "a symlink that leads outside the repo, dangles or loops")
                else:
                    os.symlink(os.path.relpath(target, here), dst)
            elif entry.is_dir(follow_symlinks=False):
                walk(sub)
            elif entry.is_file(follow_symlinks=False):
                shutil.copy2(entry.path, dst, follow_symlinks=False)
            else:
                _skip(skipped, sub, "not a regular file, folder or symlink")
        shutil.copystat(here, os.path.join(ws, rel) if rel else ws)

    walk("")
    return skipped


def _remove_escaping_links(ws: Path) -> list[str]:
    """Delete every symlink under `ws` that dangles, loops or leads outside `ws` (a clone's safety net)."""
    root = os.path.realpath(ws)
    removed: list[str] = []
    for here, dirs, files in os.walk(root):
        for name in [*dirs, *files]:
            path = os.path.join(here, name)
            if os.path.islink(path) and _inside_target(path, root) is None:
                os.unlink(path)
                _skip(removed, os.path.relpath(path, root), "a symlink that leads outside the repo, dangles or loops")
        dirs[:] = [d for d in dirs if d != ".git" and not os.path.islink(os.path.join(here, d))]
    return removed


def git_auth_env(token: str, base: str) -> dict[str, str]:
    """The child env that gives git the installation token for `base` only (an `http.<base>/.extraheader`),
    so it never appears in argv or `.git/config`. Both the token and its basic form are registered secrets."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    register_secret(token)
    register_secret(basic)
    return {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": f"http.{base}/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
            "GIT_CONFIG_KEY_1": "http.sslVerify", "GIT_CONFIG_VALUE_1": "true"}


def _remove_bob_config(ws: Path) -> list[str]:
    """Drop a cloned repo's own `.bob/` (Bob settings or modes it ships): Bob runs with cwd = the workspace,
    and only Rook writes `.bob/` there (a local copy leaves it out the same way, COPY_IGNORE)."""
    target = ws / ".bob"
    if not os.path.lexists(target):
        return []
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()
    return [".bob"]


def _clone(repo: RepoSpec, ws: Path, token: str | None, github_url: str,
           cancel: threading.Event | None = None) -> str:
    if not _REPO_RE.fullmatch(repo.ref) or repo.ref.startswith(("-", ".")):
        raise PrepareError(f"a GitHub repo must look like 'owner/name', not {repo.ref!r}")
    base = github_url.rstrip("/")
    env = git_auth_env(token, base) if token else {}
    # core.symlinks=false (kept in the clone's config): links are checked out as plain text files.
    args = ["clone", "-q", "--depth", "1", "--no-tags", "-c", "core.symlinks=false"]
    if repo.branch:
        args += ["--branch", repo.branch]
    git(ws.parent, *args, "--", f"{base}/{repo.ref}.git", ws.name, env=env, cancel=cancel)
    return git(ws, "rev-parse", "HEAD", cancel=cancel)


def prepare_workspace(
    repo: RepoSpec,
    run_id: str,
    *,
    root: Path = DEFAULT_ROOT,
    token: str | None = None,
    allowlist: Allowlist = DEFAULT_ALLOWLIST,
    hosted: bool = False,
    github_url: str = GITHUB_URL,
    cancel: threading.Event | None = None,
) -> Workspace:
    """Create `<root>/<run_id>/` for the run. Raises NotAllowlistedError, PrepareError (PrepareCancelled
    once `cancel` is set) or GitError. On any error the half-made workspace is removed."""
    if hosted and repo.kind != "demo":
        raise NotAllowlistedError(f"{repo.ref} {REFUSED_MESSAGE}")
    entry = allowlist.get(repo.ref, repo.commit or "") if repo.kind == "demo" else None
    if not re.fullmatch(r"r_[a-z2-7]{4,32}", run_id):
        raise PrepareError(f"invalid run id {run_id!r}")
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    ws = root / run_id
    if os.path.lexists(ws):
        raise PrepareError(f"the workspace {ws} already exists")
    try:
        if repo.kind == "local":
            src = Path(repo.ref).expanduser().resolve()
            if not src.is_dir():
                raise PrepareError(f"not a folder: {repo.ref}")
            if ws.is_relative_to(src):
                raise PrepareError(f"the workspace folder {root} may not be inside the repo {src}")
            skipped = _copy(src, ws, cancel)
            base = _init_baseline(ws, repo.name, cancel)
        elif repo.kind == "github":
            base = _clone(repo, ws, token, github_url, cancel)
            skipped = _remove_escaping_links(ws)
            skipped += _remove_bob_config(ws)
        else:
            assert entry is not None
            skipped = _copy(entry.app_dir, ws, cancel)
            base = _init_baseline(ws, repo.name, cancel)
        _check_cancel(cancel)
    except BaseException:
        shutil.rmtree(ws, ignore_errors=True)
        raise
    return Workspace(path=ws, repo=repo, base_commit=base, demo=entry, skipped=tuple(skipped))


# --- SHIP ---


@dataclass(frozen=True)
class ShipRequest:
    cx_id: str
    files: list[str]  # workspace-relative: the fix, the regression test, rook/rook.yaml, the cx JSON
    title: str
    body: str


@dataclass(frozen=True)
class ShipResult:
    branch: str
    commit: str
    files: list[str]
    pushed: bool = False
    pr_url: str | None = None
    pr_number: int | None = None


class Shipper(Protocol):
    """Takes a verified fix out of the workspace. Must never push to the default branch."""

    async def ship(self, workspace: Path, request: ShipRequest) -> ShipResult: ...


def branch_name(cx_id: str) -> str:
    return "rook/fix-" + cx_id.replace("_", "-")


def check_ship_paths(workspace: Path, paths: list[str]) -> list[str]:
    """Relative, normalised paths of regular files inside the workspace, reached without a symlink."""
    root = workspace.resolve()
    out = sorted(set(paths))
    for rel in out:
        pure = PurePosixPath(rel)
        if (not rel or pure.is_absolute() or str(pure) != rel or "\\" in rel
                or any(p in ("", ".", "..", ".git", ".bob") for p in pure.parts)):
            raise ValueError(f"refused path to commit: {rel!r}")
        current = root
        for part in pure.parts:
            current = current / part
            mode = os.lstat(current).st_mode  # FileNotFoundError for a missing file
            if stat.S_ISLNK(mode):
                raise ValueError(f"refused path to commit (symlink): {rel!r}")
        if not stat.S_ISREG(mode):
            raise ValueError(f"refused path to commit (not a file): {rel!r}")
    return out


def commit_fix_branch(workspace: Path, request: ShipRequest) -> ShipResult:
    """Commit `request.files` on a new branch `rook/fix-<cx>` from the current HEAD. Nothing is pushed."""
    files = check_ship_paths(workspace, request.files)
    branch = branch_name(request.cx_id)
    git(workspace, "checkout", "-q", "-b", branch)
    git(workspace, "add", "-A", "--", *files)
    git(workspace, "commit", "-q", "-m", request.title, "-m", request.body)
    return ShipResult(branch=branch, commit=git(workspace, "rev-parse", "HEAD"), files=files)


class LocalBranchShipper:
    """Test mode: the verified fix goes to a local branch in the workspace repo; nothing is pushed."""

    async def ship(self, workspace: Path, request: ShipRequest) -> ShipResult:
        return await asyncio.to_thread(commit_fix_branch, workspace, request)
