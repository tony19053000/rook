"""ProcessSandbox: runs an allowlisted demo app as a local subprocess (02 section 8, 03 section 3).

Used by the hosted server, which cannot run Docker. Only repos on the allowlist are run, with the
start command and env from their allowlist entry (a SandboxPlan's commands are never executed here).

Where it runs from: by default the pristine, pre-installed `app_dir`. With `workspace=` (a capability the
server grants only in replay mode, 03 section 3) the app and the entry's commands run from the run's
workspace copy instead: the pinned repo plus the Surgeon's taped, path-guarded edits, so VERIFY executes
the patched code. Only then may the `test` command get one extra argument: the path of a regular test
file inside that workspace. The start command, env and commands still come only from the entry.

Each run gets a fresh temp dir (HOME, TMPDIR and the temp DB file live there) and a free port on
127.0.0.1. The child env is built from scratch: none of Rook's own env (API keys, tokens) is passed.
The app runs in its own process group, and the whole group is killed on stop, on an exception inside
`with ProcessSandbox(...)`, and at interpreter exit.
"""

import atexit
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import IO

import httpx

from rook.agents.schemas import SandboxPlan
from rook.sandbox.allowlist import (
    DEFAULT_ALLOWLIST,
    TEST_COMMAND,
    Allowlist,
    AllowlistEntry,
    check_env_name,
    check_env_value,
)
from rook.sandbox.base import ExecResult, Sandbox, SandboxError, free_port

HOST = "127.0.0.1"
STOP_GRACE = 5.0
_POLL_INTERVAL = 0.1
_SYSTEM_PATH = ("/usr/local/bin", "/usr/bin", "/bin")
# logs() reads at most this much from the end of app.log. The file itself lives in the run's temp
# dir and is deleted on stop; demo apps are trusted, so it is not rotated.
_LOG_TAIL_BYTES = 256_000
# exec() commands (tests) get no easy way out: every proxy variable points at a closed local port and
# package managers are told to stay offline. Best effort only (a subprocess has no network namespace of
# its own); what runs is the pinned repo plus reviewed, taped edits. Loopback stays reachable.
_DEAD_PROXY = "http://127.0.0.1:9"
_OFFLINE_ENV = {
    **{name: _DEAD_PROXY for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                                     "all_proxy")},
    "NO_PROXY": "127.0.0.1,localhost",
    "no_proxy": "127.0.0.1,localhost",
    "UV_OFFLINE": "1",
    "PIP_NO_INDEX": "1",
    "npm_config_offline": "true",
    "GOPROXY": "off",
    "GOTOOLCHAIN": "local",
}

# Strong refs: a sandbox dropped without stop() must still be stopped at exit.
_LIVE: "set[ProcessSandbox]" = set()
_LIVE_LOCK = threading.Lock()


@atexit.register
def _stop_all() -> None:
    with _LIVE_LOCK:
        live = list(_LIVE)
    for sandbox in live:
        sandbox.stop()


def _kill_group(pgid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def _resolve(argv: Sequence[str], port: int) -> list[str]:
    return [t.replace("{python}", sys.executable).replace("{port}", str(port)) for t in argv]


def _check_workspace(workspace: Path) -> Path:
    path = Path(workspace)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise ValueError(f"the workspace must be an existing, absolute folder (not a symlink): {workspace}")
    return path.resolve()


def _test_file(root: Path, rel: str) -> bool:
    """`rel` names a regular file inside `root`: relative, normalised, not an option, no symlink on the way."""
    pure = PurePosixPath(rel)
    if (not rel or rel.startswith("-") or "\\" in rel or "\x00" in rel or pure.is_absolute() or str(pure) != rel
            or any(part in ("", ".", "..") for part in pure.parts)):
        return False
    path = root.joinpath(*pure.parts)
    try:
        return os.path.realpath(path, strict=True) == str(path) and stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


class ProcessSandbox(Sandbox):
    def __init__(
        self,
        repo: str,
        commit: str,
        *,
        allowlist: Allowlist = DEFAULT_ALLOWLIST,
        env: Mapping[str, str] | None = None,
        workspace: Path | None = None,
    ) -> None:
        """Raises NotAllowlistedError if `repo@commit` is not allowlisted.

        `env` holds extra values for the app (e.g. setup values the user answered). Only names in the
        entry's `settable_env` are accepted, and never loader/interpreter/shell variables.

        `workspace` (default None: run the pristine `app_dir`) makes the app and the entry's commands run
        from that folder, the run's workspace copy. Only trusted config may grant it: the server does, in
        replay mode only, where every edit in the workspace comes from a committed, reviewed edit tape.
        """
        self.entry: AllowlistEntry = allowlist.get(repo, commit)
        self.workspace: Path | None = _check_workspace(workspace) if workspace is not None else None
        extra = dict(env or {})
        not_settable = sorted(set(extra) - self.entry.settable_env)
        if not_settable:
            raise ValueError(f"env may only set {sorted(self.entry.settable_env)}, not {not_settable}")
        for name, value in extra.items():  # defence in depth: the entry was validated too
            check_env_value(check_env_name(name), value)
        self._extra_env = extra
        self._port: int | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._tmp: Path | None = None
        self._log: IO[bytes] | None = None
        self._last_logs = ""

    # --- state ---

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def base_url(self) -> str:
        if self._proc is None or self._port is None:
            raise SandboxError("sandbox is not started")
        return f"http://{HOST}:{self._port}"

    @property
    def pid(self) -> int | None:
        """The app's pid, which is also its process group id."""
        return self._proc.pid if self._proc is not None else None

    @property
    def temp_dir(self) -> Path | None:
        return self._tmp

    @property
    def run_dir(self) -> Path:
        """The folder the app and its commands run from (cwd)."""
        return self.workspace if self.workspace is not None else self.entry.app_dir

    # --- env ---

    def _child_env(self, tmp: Path, port: int) -> dict[str, str]:
        path = os.pathsep.join(dict.fromkeys((str(Path(sys.executable).parent), *_SYSTEM_PATH)))
        env = {
            **self.entry.env,
            **self._extra_env,
            "PATH": path,
            "HOME": str(tmp),
            "TMPDIR": str(tmp),
            "LANG": "C.UTF-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if self.entry.port_env:
            env[self.entry.port_env] = str(port)
        if self.entry.db_env:
            env[self.entry.db_env] = str(tmp / "db" / "app.db")
        return env

    # --- lifecycle ---

    def start(self, plan: SandboxPlan | None = None) -> str:
        """Start the allowlisted app. `plan` is ignored: only the allowlist entry decides what runs."""
        if self._proc is not None:
            raise SandboxError("sandbox is already started")
        port = self._port or free_port(HOST)
        tmp = Path(tempfile.mkdtemp(prefix="rook-sandbox-"))
        (tmp / "db").mkdir()
        self._port, self._tmp = port, tmp
        self._log = open(tmp / "app.log", "wb")  # noqa: SIM115 - closed in stop()
        with _LIVE_LOCK:
            _LIVE.add(self)
        try:
            self._proc = subprocess.Popen(
                _resolve(self.entry.start, port),
                cwd=self.run_dir,
                env=self._child_env(tmp, port),
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # own process group, so stop() can kill the whole tree
                close_fds=True,
            )
            self._wait_healthy()
        except BaseException as exc:
            self.stop()
            if isinstance(exc, SandboxError):
                raise
            if isinstance(exc, OSError):
                raise SandboxError(f"could not start {self.entry.repo}: {exc}") from exc
            raise
        return self.base_url

    def _wait_healthy(self) -> None:
        assert self._proc is not None
        url = self.base_url + self.entry.health_path
        deadline = time.monotonic() + self.entry.health_timeout
        last = "no response"
        with httpx.Client(trust_env=False, timeout=2.0, follow_redirects=False) as client:
            while True:
                code = self._proc.poll()
                if code is not None:
                    raise SandboxError(
                        f"{self.entry.repo} exited with code {code} before it was healthy\n{self.logs(50)}"
                    )
                try:
                    response = client.get(url)
                    if response.status_code == 200:
                        return
                    last = f"HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    last = type(exc).__name__
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        f"{self.entry.repo} not healthy after {self.entry.health_timeout:g}s "
                        f"({url}: {last})\n{self.logs(50)}"
                    )
                time.sleep(_POLL_INTERVAL)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            _kill_group(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=STOP_GRACE)
            except subprocess.TimeoutExpired:
                pass
            # Always SIGKILL the group too: children left behind by the leader must not survive.
            _kill_group(proc.pid, signal.SIGKILL)
            proc.wait()
        if self._log is not None:
            self._log.close()
            self._log = None
        if self._tmp is not None:
            self._last_logs = self._read_log(self._tmp / "app.log")
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None
        with _LIVE_LOCK:
            _LIVE.discard(self)

    def restart(self) -> str:
        """Stop and start again on the same port (same base URL) with a fresh temp DB."""
        port = self._port
        self.stop()
        self._port = port
        return self.start()

    # --- commands and logs ---

    def _allowed(self, wanted: list[str], port: int) -> bool:
        """One of the entry's `commands` exactly (as argv lists). From a workspace, the `test` command may
        also get one extra argument: the path of a regular test file inside that workspace."""
        for name, argv in self.entry.commands.items():
            allowed = _resolve(argv, port)
            if wanted == allowed:
                return True
            if (self.workspace is not None and name == TEST_COMMAND and len(wanted) == len(allowed) + 1
                    and wanted[:-1] == allowed and _test_file(self.workspace, wanted[-1])):
                return True
        return False

    def exec(self, cmd: Sequence[str], timeout: float = 600.0) -> ExecResult:
        """Run one of the entry's `commands` (see `_allowed`) from `run_dir`, with the app's scrubbed env
        plus offline settings, for at most the entry's `command_timeout`; anything else is refused."""
        port = self._port or 0
        wanted = _resolve(cmd, port)
        if not self._allowed(wanted, port):
            raise SandboxError(f"command not allowlisted for {self.entry.repo}: {list(cmd)!r}")
        timeout = min(timeout, self.entry.command_timeout)
        own_tmp = self._tmp is None
        tmp = Path(tempfile.mkdtemp(prefix="rook-exec-")) if own_tmp else self._tmp
        assert tmp is not None
        try:
            proc = subprocess.Popen(
                wanted,
                cwd=self.run_dir,
                env={**self._child_env(tmp, port), **_OFFLINE_ENV},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
                close_fds=True,
            )
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(proc.pid, signal.SIGKILL)
                out, err = proc.communicate()
                return ExecResult(-1, out.decode(errors="replace"), f"timeout after {timeout:g}s")
            finally:
                _kill_group(proc.pid, signal.SIGKILL)
            return ExecResult(proc.returncode, out.decode(errors="replace"), err.decode(errors="replace"))
        finally:
            if own_tmp:
                shutil.rmtree(tmp, ignore_errors=True)

    def logs(self, tail: int = 200) -> str:
        """The app's last output lines (from the last run if it has stopped)."""
        text = self._read_log(self._tmp / "app.log") if self._tmp is not None else self._last_logs
        lines = text.splitlines()
        return "\n".join(lines[-tail:]) if tail > 0 else ""

    @staticmethod
    def _read_log(path: Path) -> str:
        try:
            with open(path, "rb") as f:
                size = f.seek(0, os.SEEK_END)
                f.seek(max(0, size - _LOG_TAIL_BYTES))
                return f.read().decode(errors="replace")
        except OSError:
            return ""
