"""Hosted runs of a signed-in user's own GitHub repos (ROOK-041, 02 §11, 03 §3).

Whether the server can run them at all (`not_configured`): the GitHub App, BOB_API_KEY (they use live Bob),
`github_runs_max > 0` and a working Docker (`DockerProbe`). When the server itself runs in a container, the
probe also checks the two things that make a DockerSandbox work from there:
- the workspaces folder is on a bind mount with the SAME path on the host and in the container (the Docker
  daemon resolves compose bind paths on the host, so `/x/ws/<run>` must mean the same folder to both);
- the server container is on `sandbox_network`, the network the sandbox's port proxy joins (a port published
  on the host's 127.0.0.1 is not reachable from inside a container).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rook.agents.bob import resolve_bin
from rook.sandbox import reaper
from rook.server.config import ServerSettings

log = logging.getLogger(__name__)

PROBE_TTL = 60.0
IN_CONTAINER_MARKER = Path("/.dockerenv")
NOT_CONFIGURED = "Running your own GitHub repos is not available on this server"
BUSY = "Rook is busy with another run on a GitHub repo; try again in a few minutes"
NOT_LINKED = "Connect GitHub first (the Rook GitHub App is not installed for you)"
NOT_YOURS = "This repo is not shared with the Rook GitHub App in your GitHub installation"
DockerRun = Callable[[list[str]], tuple[int, str]]


def _docker(args: list[str]) -> tuple[int, str]:
    result = reaper.docker(args, timeout=15)
    return result.returncode, result.stdout


def user_limit_message(runs: int) -> str:
    return f"You've used today's {runs} runs on your GitHub repos; try again tomorrow"


def same_path_mount(mounts: Any, folder: Path) -> bool:
    """`folder` lies inside a bind mount whose host path equals its container path."""
    if not isinstance(mounts, list):
        return False
    for mount in mounts:
        if not isinstance(mount, dict) or mount.get("Type") != "bind":
            continue
        source, target = mount.get("Source"), mount.get("Destination")
        if isinstance(source, str) and source == target and folder.is_relative_to(Path(target)):
            return True
    return False


@dataclass
class DockerProbe:
    """Are Docker (and Bob Shell) usable for user GitHub runs? Cached for PROBE_TTL seconds; the reason is logged,
    never sent to a client."""

    workspaces_root: Path
    sandbox_network: str | None
    run: DockerRun = _docker
    in_container: Callable[[], bool] = IN_CONTAINER_MARKER.exists
    container_id: Callable[[], str] = socket.gethostname
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._checked: tuple[float, bool] | None = None

    def __call__(self) -> bool:
        with self._lock:
            if self._checked is not None and self.clock() - self._checked[0] < PROBE_TTL:
                return self._checked[1]
            problem = self.problem()
            if problem:
                log.warning("GitHub runs are off: %s", problem)
            self._checked = (self.clock(), problem is None)
            return problem is None

    def problem(self) -> str | None:
        if shutil.which("docker", path=reaper.cli_env().get("PATH")) is None:
            return "no docker CLI"
        if shutil.which(resolve_bin()) is None:
            return "no Bob Shell (these runs use live Bob)"
        code, _ = self.run(["version", "--format", "{{.Server.Version}}"])
        if code != 0:
            return "the Docker daemon is not reachable"
        if not self.in_container():
            return None
        if self.sandbox_network is None:
            return "ROOK_SANDBOX_NETWORK is not set (needed when the server runs in a container)"
        code, out = self.run(["inspect", "--format",
                              '{"mounts":{{json .Mounts}},"networks":{{json .NetworkSettings.Networks}}}',
                              self.container_id()])
        try:
            info = json.loads(out) if code == 0 else None
        except ValueError:
            info = None
        if not isinstance(info, dict):
            return "could not inspect the server's own container"
        root = Path(os.path.realpath(self.workspaces_root))
        if not same_path_mount(info.get("mounts"), root):
            return f"{root} is not bind-mounted at the same path on the host"
        networks = info.get("networks")
        if not isinstance(networks, dict) or self.sandbox_network not in networks:
            return f"the server container is not on the network {self.sandbox_network}"
        return None


def settings_allow(settings: ServerSettings) -> bool:
    """BOB_API_KEY is set (these runs use live Bob) and the runs are not turned off."""
    return settings.bob_key_set and settings.github_runs_max > 0


def not_configured(settings: ServerSettings, app_configured: bool, docker_ready: Callable[[], bool]) -> bool:
    """True when this server can't run user GitHub repos (the cheap checks first; Docker last)."""
    return not (app_configured and settings_allow(settings) and docker_ready())
