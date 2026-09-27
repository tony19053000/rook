"""ROOK-041, the #1 trap of running user GitHub repos from the hosted server, which itself runs in a container
with the Docker socket: bind paths in `docker run -v` / compose are resolved by the DAEMON, on the host.

- With the workspace bind-mounted at the same path on the host and in the server container, a sandbox bind of a
  workspace file sees the file.
- With different paths, the same bind silently mounts the wrong (host) folder: the file is not there.
- `same_path_mount` (the server's startup probe) reads real `docker inspect` output correctly.

The "server container" here is python:3.12-slim-bookworm with the host's docker CLI and socket mounted, so no image
is built.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rook.server.github_runs import same_path_mount

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed"),
]

SOCKET = "/var/run/docker.sock"
IMAGE = "alpine:latest"
SERVER_IMAGE = "python:3.12-slim-bookworm"  # glibc, like the rook image: the host's docker CLI runs in it


def _docker(*args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, check=False,
                          stdin=subprocess.DEVNULL)


@pytest.fixture
def workspaces(tmp_path: Path) -> Path:
    for image in (IMAGE, SERVER_IMAGE):
        if _docker("image", "inspect", image).returncode != 0 and _docker("pull", image).returncode != 0:
            pytest.skip(f"{image} is not available")
    cli = shutil.which("docker")
    assert cli is not None
    root = tmp_path / "workspaces"
    (root / "r_abc").mkdir(parents=True)
    (root / "r_abc" / "hello.txt").write_text("from the workspace\n")
    root.chmod(0o755)
    (root / "r_abc").chmod(0o755)
    return root


def _sandbox_bind_from_server(root: Path, server_path: str) -> subprocess.CompletedProcess[str]:
    """The "server" container sees `root` at `server_path` and asks the daemon to bind a workspace file into a
    sandbox container, exactly as compose would with the server's own path."""
    cli = shutil.which("docker")
    assert cli is not None
    inner = f"docker run --rm -v {server_path}/r_abc/hello.txt:/x:ro {IMAGE} cat /x"
    return _docker("run", "--rm", "-v", f"{SOCKET}:{SOCKET}", "-v", f"{Path(cli).resolve()}:/usr/local/bin/docker:ro",
                   "-v", f"{root}:{server_path}", SERVER_IMAGE, "sh", "-c", inner)


def test_a_same_path_mount_lets_the_sandbox_see_the_workspace(workspaces: Path) -> None:
    proc = _sandbox_bind_from_server(workspaces, str(workspaces))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "from the workspace"


def test_a_different_path_binds_the_wrong_folder(workspaces: Path) -> None:
    proc = _sandbox_bind_from_server(workspaces, "/data/workspaces")
    assert "from the workspace" not in proc.stdout  # the daemon looked on the HOST's /data/workspaces


def test_the_probe_reads_real_inspect_output(workspaces: Path) -> None:
    name = f"rook-mount-probe-{workspaces.parent.name[-8:]}".lower().replace("_", "-")
    created = _docker("create", "--name", name, "-v", f"{workspaces}:{workspaces}", "-v", f"{workspaces}:/elsewhere",
                      IMAGE, "true")
    assert created.returncode == 0, created.stderr
    try:
        out = _docker("inspect", "--format", '{"mounts":{{json .Mounts}}}', name)
        mounts = json.loads(out.stdout)["mounts"]
    finally:
        _docker("rm", "-f", name)
    assert same_path_mount(mounts, workspaces / "r_abc")
    assert not same_path_mount([m for m in mounts if m["Destination"] == "/elsewhere"], Path("/elsewhere/r_abc"))
