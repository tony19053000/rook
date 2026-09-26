"""DockerSandbox: builds and runs the target app in Docker from a SandboxPlan (02 section 8, 03 section 3).

Used by the local CLI. The plan is written by the Mechanic (Bob) and the repo is untrusted, so:
- `docker` is always called with an argv list, stdin closed and a minimal env (`reaper.cli_env`): none of
  Rook's own env (BOB_API_KEY, tokens) reaches the CLI, compose interpolation or the containers;
- the app gets only the plan's env (`env_defaults`, plus caller-supplied values for `env_required`),
  checked against the env denylist, passed through a 0600 env file (never argv);
- every container runs with `--cap-drop ALL`, `no-new-privileges`, pid/memory/CPU limits, `--init`, a
  non-root user and (optionally) a read-only root filesystem with a tmpfs `/tmp`;
- nothing from the host is mounted (compose may bind only paths inside the workspace copy), and the only
  published port is the app's, on 127.0.0.1;
- all resources carry the label `rook.run=<name>` and are removed on stop, at exit, on SIGTERM/SIGHUP,
  and by a watchdog process (`reaper.py`) if Rook itself is killed.

How the plan's fields are read in each mode (the contract names them `build` and `start`):
- `command`: Rook generates the Dockerfile: `base_image`, the workspace copied to /app, `build` run once
  at build time and `start` as the container command (both via `sh -c` inside the container).
- `dockerfile`: `build` may name the Dockerfile (a path in the workspace); otherwise
  `.rook-sandbox/Dockerfile` or `Dockerfile` is used. `start`, if set, replaces the image's command.
- `compose`: `build` may name the compose file; otherwise `.rook-sandbox/compose.yaml`,
  `compose.yaml`, `docker-compose.yml`, ... are tried. `start` names the service that serves `port`
  (not needed when there is one service). See compose.py for what a compose file may contain.
"""

import atexit
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import IO, Literal

import httpx
import yaml

from rook.agents.schemas import SandboxPlan
from rook.sandbox import reaper
from rook.sandbox.allowlist import check_env_name, check_env_value
from rook.sandbox.base import HEALTH_TIMEOUT, ExecResult, Sandbox, SandboxError
from rook.sandbox.compose import PROXY_SERVICE, ComposeError, Hardening, find_compose_file, inside, render
from rook.sandbox.proxy import APP_ALIAS, INTERNAL_NETWORK_OPTS, PROXY_PORT, proxy_run_argv

HOST = "127.0.0.1"
BUILD_TIMEOUT = 900.0
STOP_TIMEOUT = 10
DEFAULT_USER = "10001:10001"
_POLL_INTERVAL = 0.25
_RUNNING_CHECK_EVERY = 1.0
# logs() and error messages keep at most this much output (the end of it).
_LOG_TAIL_BYTES = 256_000
# Names the app must never get, on top of the loader/interpreter denylist: Rook's own settings and
# credentials, and the docker CLI's.
_CONTAINER_DENIED_PREFIXES = ("BOB_", "ROOK_", "SUPABASE_", "DOCKER_", "GITHUB_APP_")
_IMAGE_REF = re.compile(
    r"[a-z0-9][a-z0-9._/-]{0,127}(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[a-f0-9]{64})?"
)
_BASE_IMAGES = {
    "python": "python:3.12-slim",
    "javascript": "node:22-slim",
    "typescript": "node:22-slim",
    "node": "node:22-slim",
}
_DOCKERIGNORE = ".git\n**/__pycache__\n**/*.pyc\n.venv\nnode_modules\n.rook\n"

Mode = Literal["compose", "dockerfile", "command"]

# Strong refs: a sandbox dropped without stop() must still be cleaned up at exit.
_LIVE: "set[DockerSandbox]" = set()
_LIVE_LOCK = threading.Lock()
_SIGNALS_INSTALLED = False


@atexit.register
def _stop_all() -> None:
    with _LIVE_LOCK:
        live = list(_LIVE)
    for sandbox in live:
        sandbox.stop()


def _on_signal(signum: int, frame: FrameType | None) -> None:
    """Clean up, then die from the same signal as if Rook had never handled it."""
    _stop_all()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _install_signal_handlers() -> None:
    """Handle SIGTERM/SIGHUP (their default kills Python without running atexit), unless the program
    already handles them itself. SIGINT raises KeyboardInterrupt, so atexit and `with` cover it."""
    global _SIGNALS_INSTALLED
    if _SIGNALS_INSTALLED or threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGHUP):
        if signal.getsignal(sig) == signal.SIG_DFL:
            signal.signal(sig, _on_signal)
    _SIGNALS_INSTALLED = True


def sandbox_name(run_id: str) -> str:
    """A Docker-safe, unique name from an untrusted run id: `rook-<cleaned id>-<random>`."""
    cleaned = re.sub(r"[^a-z0-9_.-]+", "-", run_id.lower()).strip("-_.")[:32].strip("-_.") or "run"
    return reaper.check_name(f"rook-{cleaned}-{secrets.token_hex(3)}")


def base_image_for(language: str | None) -> str:
    """The base image for command mode, from `RepoSummary.language`."""
    return _BASE_IMAGES.get((language or "").strip().lower(), _BASE_IMAGES["python"])


def check_image_ref(ref: str) -> str:
    if not isinstance(ref, str) or not _IMAGE_REF.fullmatch(ref):
        raise ValueError(f"invalid image reference {ref!r}")
    return ref


def container_env(plan: SandboxPlan, values: Mapping[str, str]) -> dict[str, str]:
    """The app's env: `env_defaults`, then caller `values` for `env_required` names. Nothing else.

    Raises SandboxError naming any required value that is missing (so the caller can ASK for it)."""
    env: dict[str, str] = {}
    unknown = sorted(set(values) - set(plan.env_required) - set(plan.env_defaults))
    if unknown:
        raise ValueError(f"env values given for names the plan does not use: {unknown}")
    for name, value in {**plan.env_defaults, **values}.items():
        check_env_name(name)
        if name.upper().startswith(_CONTAINER_DENIED_PREFIXES):
            raise ValueError(f"env var {name!r} may not be set for a sandboxed app")
        check_env_value(name, value)
        if "\n" in value or "\r" in value:
            raise ValueError(f"env var {name!r} may not contain a newline")
        env[name] = value
    for name in plan.env_required:
        check_env_name(name)
    missing = [n for n in plan.env_required if n not in env]
    if missing:
        raise SandboxError(f"missing required setup values: {missing}")
    return env


def generated_dockerfile(base_image: str, build: str | None, start: str) -> str:
    """The command-mode Dockerfile. Commands go in JSON (exec) form, so a newline or quote in them cannot
    add Dockerfile instructions; they run under `sh -c` inside the build/app container only."""
    for what, cmd in (("build", build), ("start", start)):
        if cmd is not None and "\x00" in cmd:
            raise ValueError(f"the {what} command may not contain NUL bytes")
    lines = [
        f"FROM {check_image_ref(base_image)}",
        "WORKDIR /app",
        f"COPY --chown={DEFAULT_USER} . /app",
    ]
    if build and build.strip():
        lines.append(f"RUN {json.dumps(['sh', '-c', build])}")
    lines += [
        f"RUN {json.dumps(['chown', DEFAULT_USER, '/app'])}",
        f"USER {DEFAULT_USER}",
        "ENV HOME=/tmp",
        f"CMD {json.dumps(['sh', '-c', start])}",
    ]
    return "\n".join(lines) + "\n"


def run_user(image_user: str) -> str:
    """The image's own user if it is a numeric non-root uid[:gid], else DEFAULT_USER."""
    uid, _, gid = image_user.strip().partition(":")
    if uid.isdigit() and int(uid) != 0 and (not gid or (gid.isdigit() and int(gid) != 0)):
        return image_user.strip()
    return DEFAULT_USER


@dataclass(frozen=True, slots=True)
class Limits:
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 512
    tmpfs_size: str = "256m"


def run_argv(
    *,
    name: str,
    image: str,
    network: str,
    env_file: Path,
    user: str,
    labels: Mapping[str, str],
    limits: Limits,
    read_only: bool,
    start: str | None,
) -> list[str]:
    """`docker run` argv for dockerfile/command mode, with every 03 section 3 hardening flag.

    The app joins only the internal `network` (as `app`) and publishes nothing; the proxy does that."""
    argv = [
        "run",
        "-d",
        "--name",
        name,
        "--hostname",
        APP_ALIAS,
        "--network",
        network,
        "--network-alias",
        APP_ALIAS,
        "--env-file",
        str(env_file),
        "--user",
        user,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(limits.pids),
        "--memory",
        limits.memory,
        "--memory-swap",
        limits.memory,
        "--cpus",
        f"{limits.cpus:g}",
        "--init",
        "--restart",
        "no",
        "--stop-timeout",
        str(STOP_TIMEOUT),
        "--log-driver",
        "json-file",
        "--log-opt",
        "max-size=10m",
        "--log-opt",
        "max-file=1",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size={limits.tmpfs_size}",
    ]
    if read_only:
        argv.append("--read-only")
    for key, value in labels.items():
        argv += ["--label", f"{key}={value}"]
    if start:
        argv += ["--entrypoint", "sh", image, "-c", start]
    else:
        argv.append(image)
    return argv


DEFAULT_LIMITS = Limits()


def _tail(text: str, lines: int | None = None) -> str:
    text = text[-_LOG_TAIL_BYTES:]
    if lines is None:
        return text
    return "\n".join(text.splitlines()[-lines:]) if lines > 0 else ""


class DockerSandbox(Sandbox):
    def __init__(
        self,
        workspace: Path,
        *,
        run_id: str = "run",
        env: Mapping[str, str] | None = None,
        base_image: str = _BASE_IMAGES["python"],
        read_only: bool = False,
        limits: Limits = DEFAULT_LIMITS,
        health_timeout: float = HEALTH_TIMEOUT,
        build_timeout: float = BUILD_TIMEOUT,
    ) -> None:
        """`workspace` is the run's workspace copy (never the user's own folder); it is the build
        context. `env` holds values for the plan's `env_required` names (e.g. setup answers)."""
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise SandboxError(f"workspace is not a folder: {workspace}")
        self.run_id = run_id
        self._values = dict(env or {})
        self.base_image = check_image_ref(base_image)
        self.read_only = read_only
        self.limits = limits
        self.health_timeout = health_timeout
        self.build_timeout = build_timeout
        self.name: str | None = None
        self._plan: SandboxPlan | None = None
        self._mode: Mode | None = None
        self._tmp: Path | None = None
        self._host_port: int | None = None
        self._container: str | None = None  # the app's container id
        self._image: str | None = None
        self._compose_file: Path | None = None
        self._compose_dir: Path | None = None
        self._service: str | None = None
        self._watchdog: subprocess.Popen[bytes] | None = None
        self._watchdog_pipe: IO[bytes] | None = None
        self._network = False
        self._last_logs = ""

    # --- state ---

    @property
    def running(self) -> bool:
        if self._container is None:
            return False
        out = reaper.docker(["inspect", "-f", "{{.State.Running}}", self._container], timeout=30).stdout
        return out.strip() == "true"

    @property
    def base_url(self) -> str:
        if self._container is None or self._host_port is None:
            raise SandboxError("sandbox is not started")
        return f"http://{HOST}:{self._host_port}"

    @property
    def labels(self) -> dict[str, str]:
        assert self.name is not None
        return {reaper.SANDBOX_LABEL: "1", reaper.RUN_LABEL: self.name, reaper.OWNER_LABEL: str(os.getpid())}

    # --- lifecycle ---

    def start(self, plan: SandboxPlan | None = None) -> str:
        """Build and run the app from `plan`, wait for its health check and return its base URL."""
        if self._container is not None:
            raise SandboxError("sandbox is already started")
        if plan is None:
            raise SandboxError("DockerSandbox needs a SandboxPlan")
        plan = SandboxPlan.model_validate(plan.model_dump())  # re-check: callers may construct it loosely
        env = container_env(plan, self._values)
        # A new name per start: a watchdog of an earlier start may still be sweeping the old one.
        self.name = sandbox_name(self.run_id)
        self._tmp = Path(tempfile.mkdtemp(prefix="rook-docker-"))  # mode 0700
        with _LIVE_LOCK:
            _LIVE.add(self)
        _install_signal_handlers()
        self._plan, self._mode = plan, plan.mode
        try:
            self._start_watchdog()
            self._write_env_file(env)
            if plan.mode == "compose":
                self._up_compose(plan, env, build=True)
            else:
                self._build_image(plan)
                self._run_container(plan)
            self._wait_healthy(plan)
        except BaseException as exc:
            self.stop()
            if isinstance(exc, ComposeError | ValueError | OSError) and not isinstance(exc, SandboxError):
                raise SandboxError(str(exc)) from exc
            raise
        return self.base_url

    def restart(self) -> str:
        """Remove the app's containers (fresh state) and run them again on the same port and image."""
        if self._plan is None or self.name is None:
            raise SandboxError("sandbox is not started")
        plan = self._plan
        self._last_logs = self.logs(_LOG_TAIL_BYTES)
        self._remove_containers()
        try:
            if plan.mode == "compose":
                self._up_compose(plan, container_env(plan, self._values), build=False)
            else:
                self._run_container(plan)
            self._wait_healthy(plan)
        except BaseException:
            self.stop()
            raise
        return self.base_url

    def stop(self) -> None:
        """Remove every container, network, volume and image of this run. Safe to call more than once."""
        name = self.name
        if name is not None:
            if self._container is not None:
                logs = self.logs(_LOG_TAIL_BYTES)
                if logs:
                    self._last_logs = logs
            self._remove_containers()
            reaper.sweep(name)
        self._stop_watchdog()
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
        self.name = self._tmp = self._container = self._image = self._host_port = None
        self._compose_file = self._compose_dir = self._service = None
        self._plan = self._mode = None
        self._network = False
        with _LIVE_LOCK:
            _LIVE.discard(self)

    # --- watchdog ---

    def _start_watchdog(self) -> None:
        assert self.name is not None
        read_fd, write_fd = os.pipe()
        try:
            self._watchdog = subprocess.Popen(
                [sys.executable, "-m", "rook.sandbox.reaper", self.name],
                stdin=read_fd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**reaper.cli_env(), "PYTHONPATH": str(Path(__file__).parents[2])},
                start_new_session=True,  # a Ctrl-C to Rook's process group must not kill it first
                close_fds=True,
            )
        finally:
            os.close(read_fd)
        self._watchdog_pipe = os.fdopen(write_fd, "wb")

    def _stop_watchdog(self) -> None:
        pipe, self._watchdog_pipe = self._watchdog_pipe, None
        proc, self._watchdog = self._watchdog, None
        if pipe is not None:
            pipe.close()  # EOF: the watchdog sweeps (already clean) and exits
        if proc is not None:
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    # --- docker helpers ---

    def _docker(self, args: Sequence[str], what: str, timeout: float = 120.0) -> str:
        result = reaper.docker(args, timeout=timeout)
        if result.returncode != 0:
            output = _tail(result.stdout + result.stderr, 60)
            raise SandboxError(f"{what} failed (exit {result.returncode})\n{output}")
        return result.stdout

    def _write_env_file(self, env: Mapping[str, str]) -> None:
        assert self._tmp is not None
        path = self._tmp / "app.env"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in env.items())

    def _build_image(self, plan: SandboxPlan) -> None:
        assert self._tmp is not None and self.name is not None
        tag = f"{self.name}:latest"
        if plan.mode == "command":
            assert plan.start is not None
            dockerfile = self._tmp / "Dockerfile"
            dockerfile.write_text(
                generated_dockerfile(self.base_image, plan.build, plan.start), encoding="utf-8"
            )
            if not (self.workspace / ".dockerignore").exists():
                (self._tmp / "Dockerfile.dockerignore").write_text(_DOCKERIGNORE, encoding="utf-8")
        else:
            dockerfile = self._find_dockerfile(plan.build)
        args = ["build", "--progress", "plain", "--file", str(dockerfile), "--tag", tag]
        for key, value in self.labels.items():
            args += ["--label", f"{key}={value}"]
        self._image = tag  # set before building so a partial build is still swept
        try:
            self._docker([*args, str(self.workspace)], "docker build", timeout=self.build_timeout)
        except SandboxError as exc:
            self._last_logs = str(exc)
            raise

    def _find_dockerfile(self, hint: str | None) -> Path:
        root = self.workspace
        candidates = [root / hint.strip()] if hint and hint.strip() and " " not in hint.strip() else []
        candidates += [root / ".rook-sandbox" / "Dockerfile", root / "Dockerfile"]
        for path in candidates:
            if path.is_file():
                return inside(root, path, "Dockerfile")
        raise SandboxError("no Dockerfile found (.rook-sandbox/Dockerfile or Dockerfile)")

    def _create_networks(self) -> None:
        """`<name>`: internal, no host address (the app's). `<name>-pub`: normal, for the proxy only."""
        assert self.name is not None
        labels = [arg for key, value in self.labels.items() for arg in ("--label", f"{key}={value}")]
        internal = [
            "--internal",
            *(a for k, v in INTERNAL_NETWORK_OPTS.items() for a in ("--opt", f"{k}={v}")),
        ]
        self._docker(
            ["network", "create", "--driver", "bridge", *internal, *labels, self.name], "network create"
        )
        self._docker(
            ["network", "create", "--driver", "bridge", *labels, f"{self.name}-pub"], "network create"
        )
        self._network = True

    def _start_proxy(self, plan: SandboxPlan) -> None:
        assert self.name is not None
        proxy = f"{self.name}-proxy"
        argv = proxy_run_argv(
            name=proxy,
            network=f"{self.name}-pub",
            host_port=self._host_port,
            target_port=plan.port,
            labels=self.labels,
        )
        self._docker(argv, "docker run (proxy)")
        self._docker(["network", "connect", self.name, proxy], "docker network connect")
        self._host_port = self._published_port(["port", proxy, f"{PROXY_PORT}/tcp"])

    def _run_container(self, plan: SandboxPlan) -> None:
        assert self._tmp is not None and self.name is not None and self._image is not None
        network = self.name
        if not self._network:
            self._create_networks()
        image_user = self._docker(
            ["image", "inspect", "-f", "{{.Config.User}}", self._image], "docker inspect"
        )
        user = DEFAULT_USER if plan.mode == "command" else run_user(image_user)
        argv = run_argv(
            name=f"{self.name}-app",
            image=self._image,
            network=network,
            env_file=self._tmp / "app.env",
            user=user,
            labels=self.labels,
            limits=self.limits,
            read_only=self.read_only,
            start=plan.start if plan.mode == "dockerfile" else None,
        )
        self._container = self._docker(argv, "docker run").strip()
        if self._host_port is None:  # first run; on restart the proxy is still up on the same port
            self._start_proxy(plan)

    def _compose_args(self) -> list[str]:
        assert self.name is not None and self._compose_file is not None and self._compose_dir is not None
        args = [
            "compose",
            "--project-name",
            self.name,
            "--file",
            str(self._compose_file),
            "--project-directory",
            str(self._compose_dir),
        ]
        dotenv = self._compose_dir / ".env"
        if dotenv.is_file():
            args += ["--env-file", str(inside(self.workspace, dotenv, "compose .env"))]
        assert self._tmp is not None
        return [*args, "--env-file", str(self._tmp / "app.env")]

    def _up_compose(self, plan: SandboxPlan, env: Mapping[str, str], *, build: bool) -> None:
        assert self._tmp is not None and self.name is not None
        source = find_compose_file(self.workspace, plan.build)
        hardening = Hardening(
            user=DEFAULT_USER,
            memory=self.limits.memory,
            cpus=self.limits.cpus,
            pids=self.limits.pids,
            read_only=self.read_only,
            tmpfs_size=self.limits.tmpfs_size,
            labels=self.labels,
        )
        doc, service = render(
            source,
            self.workspace,
            service=plan.start,
            port=plan.port,
            host_port=self._host_port,
            env=env,
            hardening=hardening,
        )
        self._compose_file = self._tmp / "compose.rook.yaml"
        self._compose_file.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        self._compose_dir, self._service = source.parent, service
        if build:
            try:
                self._docker(
                    [*self._compose_args(), "build"], "docker compose build", timeout=self.build_timeout
                )
            except SandboxError as exc:
                self._last_logs = str(exc)
                raise
        self._docker(
            [*self._compose_args(), "up", "-d", "--no-build", "--remove-orphans"],
            "docker compose up",
            timeout=self.build_timeout,
        )
        container = self._docker([*self._compose_args(), "ps", "-q", "--all", service], "docker compose ps")
        self._container = container.strip().splitlines()[0] if container.strip() else None
        if self._container is None:
            raise SandboxError(f"compose service {service!r} did not start\n{self.logs(50)}")
        self._host_port = self._published_port(
            [*self._compose_args(), "port", PROXY_SERVICE, str(PROXY_PORT)]
        )

    def _published_port(self, args: list[str]) -> int:
        result = reaper.docker(args, timeout=30)
        if result.returncode != 0 and not self.running:  # Docker drops the port once the app has exited
            raise SandboxError(f"the app exited before it was healthy\n{self.logs(50)}")
        if result.returncode != 0:
            raise SandboxError(f"docker port failed\n{_tail(result.stdout + result.stderr, 20)}")
        out = result.stdout
        for line in out.splitlines():
            host, _, port = line.strip().rpartition(":")
            if host == HOST and port.isdigit():
                return int(port)
        raise SandboxError(f"the app port is not published on {HOST}: {out.strip()!r}")

    def _remove_containers(self) -> None:
        if self._mode == "compose" and self._compose_file is not None and self._compose_file.exists():
            reaper.docker(
                [
                    *self._compose_args(),
                    "down",
                    "--volumes",
                    "--remove-orphans",
                    "--timeout",
                    str(STOP_TIMEOUT),
                ]
            )
        elif self.name is not None:
            reaper.docker(["rm", "-f", "-v", f"{self.name}-app"])
        self._container = None

    def _wait_healthy(self, plan: SandboxPlan) -> None:
        url = self.base_url + plan.health_path
        deadline = time.monotonic() + self.health_timeout
        next_check = 0.0
        last = "no response"
        with httpx.Client(trust_env=False, timeout=2.0, follow_redirects=False) as client:
            while True:
                now = time.monotonic()
                if now >= next_check:
                    next_check = now + _RUNNING_CHECK_EVERY
                    if not self.running:
                        raise SandboxError(f"the app exited before it was healthy\n{self.logs(50)}")
                try:
                    response = client.get(url)
                    if response.status_code == 200:
                        return
                    last = f"HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    last = type(exc).__name__
                if time.monotonic() >= deadline:
                    raise SandboxError(
                        f"the app was not healthy after {self.health_timeout:g}s ({url}: {last})\n{self.logs(50)}"
                    )
                time.sleep(_POLL_INTERVAL)

    # --- commands and logs ---

    def exec(self, cmd: Sequence[str], timeout: float = 600.0) -> ExecResult:
        """Run an argv inside the app container (as its user, with its env).

        On timeout only the `docker exec` client is killed; the command keeps running inside the
        container until the next restart() or stop() removes it."""
        if self._container is None:
            raise SandboxError("sandbox is not started")
        if not cmd or not all(isinstance(t, str) and t and "\x00" not in t for t in cmd):
            raise SandboxError("a command must be a non-empty list of non-empty strings")
        result = reaper.docker(["exec", self._container, *cmd], timeout=timeout)
        if (
            result.returncode == 125
            and isinstance(result.stderr, str)
            and "timed out" in result.stderr.lower()
        ):
            return ExecResult(-1, "", f"timeout after {timeout:g}s")
        return ExecResult(result.returncode, _tail(result.stdout), _tail(result.stderr))

    def logs(self, tail: int = 200) -> str:
        """The app's last output lines (from the last run, or the build error, if it is not running)."""
        if tail <= 0:
            return ""
        if self._container is None:
            return _tail(self._last_logs, tail)
        if self._mode == "compose" and self._compose_file is not None:
            args = [*self._compose_args(), "logs", "--no-color", "--tail", str(tail)]
        else:
            args = ["logs", "--tail", str(tail), self._container]
        result = reaper.docker(args, timeout=30)
        return _tail(result.stdout + result.stderr, tail)
