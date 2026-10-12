"""ROOK-037: the hosted server image and the AWS EC2 deploy kit (deploy/).

Static checks of the Dockerfile, compose file, Caddyfile and demo config; the secret helper that runs on the
host (deploy/aws/remote/set_env.py); and the bash scripts driven with stub `uvx` / `ssh` / `curl` commands on
PATH, so no AWS call and no network ever happens. The image build and the in-container replay run are manual
(see the report) plus one `-m docker` test of the env-file round trip.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from rook.sandbox.allowlist import Allowlist, AllowlistEntry
from rook.server.config import load_demo_repos

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
AWS = DEPLOY / "aws"
SCRIPTS = sorted([*AWS.glob("*.sh"), *AWS.glob("scripts/*.sh"), *DEPLOY.glob("*.sh"), DEPLOY / "demos/build-demos.sh"])
SECRET_NAMES = ("BOB_API_KEY", "ROOK_GUEST_SECRET", "ROOK_PROXY_SECRET", "SUPABASE_JWT_SECRET", "SUPABASE_URL",
                "SUPABASE_ANON_KEY", "GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET")
# Built at runtime so no PEM marker sits in the repo.
DASH = "-" * 5
PEM = f"{DASH}BEGIN TEST KEY{DASH}\nQUJDREVG+/0123\nR0hJSktM==\n{DASH}END TEST KEY{DASH}\n"


def load_set_env() -> ModuleType:
    spec = importlib.util.spec_from_file_location("rook_set_env", AWS / "remote" / "set_env.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


set_env = load_set_env()


# --- image ---


def test_dockerfile_non_root_replay_default_and_no_secrets() -> None:
    text = (DEPLOY / "Dockerfile").read_text()
    users = [ln.split()[1] for ln in text.splitlines() if ln.startswith("USER ")]
    assert users == ["rook"]
    assert "ROOK_BOB_MODE=replay" in text
    assert "python:3.12" in text and "NODE22_SHA256=" in text and "NODE24_SHA256=" in text and "GO_SHA256=" in text
    for name in SECRET_NAMES:
        assert name not in text, f"{name} must never be baked into the image"
    assert 'CMD ["rook-start"]' in text and "tini" in text


def test_dockerfile_copies_every_minishop_recording_folder() -> None:
    text = (DEPLOY / "Dockerfile").read_text()
    folders = sorted(p.name for p in (ROOT / "tests/fixtures/recordings").glob("*_minishop") if p.is_dir())
    assert folders, "the minishop recordings are the replay demo"
    for folder in folders:
        assert f"tests/fixtures/recordings/{folder}/" in text
    hosted = sorted(p.name for p in (ROOT / "tests/fixtures/recordings").glob("hosted_*") if p.is_dir())
    assert {"hosted_minishop", "hosted_shop-app"} <= set(hosted)
    for folder in hosted:  # every demo app's hosted recordings reach the image (ROOK-039)
        assert f"tests/fixtures/recordings/{folder}/" in text
    # A demo started from its workspace copy finds shop-app's node_modules via /node_modules; Go needs its cache.
    assert "ln -s /opt/rook/demos/shop-app/node_modules /node_modules" in text
    assert "chown -R rook:rook /opt/rook/demos/.go/cache" in text


def test_bob_is_optional_and_vendored_only() -> None:
    text = (DEPLOY / "Dockerfile").read_text()
    assert "COPY deploy/vendor/ /tmp/vendor/" in text
    assert "REPLAY-ONLY" in text
    ignored = subprocess.run(["git", "check-ignore", "-q", "deploy/vendor/bobshell-2.0.5.tgz"], cwd=ROOT, check=False)
    assert ignored.returncode == 0, "the vendored Bob must be gitignored"
    kept = subprocess.run(["git", "check-ignore", "-q", "deploy/vendor/README.md"], cwd=ROOT, check=False)
    assert kept.returncode == 1, "deploy/vendor/README.md keeps the folder in git (COPY needs it)"
    assert subprocess.run(["git", "check-ignore", "-q", "deploy/any.pem"], cwd=ROOT, check=False).returncode == 0


def test_dockerignore_is_an_allowlist() -> None:
    lines = [ln.strip() for ln in (ROOT / ".dockerignore").read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    assert lines[0] == "*"
    assert "**/.env*" in lines and "**/*.pem" in lines
    for secretish in ("!.env", "!.git", "!web", "!deploy/aws", "!deploy/"):
        assert secretish not in lines


def test_dockerignore_lets_every_copied_recording_folder_in() -> None:
    allowed = [ln.strip()[1:].rstrip("/") for ln in (ROOT / ".dockerignore").read_text().splitlines()
               if ln.strip().startswith("!tests/fixtures/recordings/")]
    copied = re.findall(r"tests/fixtures/recordings/[\w-]+", (DEPLOY / "Dockerfile").read_text())
    assert copied
    for folder in copied:
        assert any(fnmatch.fnmatch(folder, pattern) for pattern in allowed), f"{folder} is not in the build context"


def test_start_sh_refuses_live_mode_without_bob(tmp_path: Path) -> None:
    env = {"PATH": "/usr/bin:/bin", "ROOK_BOB_MODE": "live", "ROOK_BOB_BIN": str(tmp_path / "nope"),
           "BOB_API_KEY": "unused"}
    proc = subprocess.run(["bash", str(DEPLOY / "start.sh")], env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 1
    assert "NO Bob Shell" in proc.stdout and "needs Bob Shell" in proc.stderr


def test_start_sh_refuses_live_mode_without_key(tmp_path: Path) -> None:
    bob = tmp_path / "bob"
    bob.write_text("#!/bin/sh\n")
    bob.chmod(0o755)
    env = {"PATH": "/usr/bin:/bin", "ROOK_BOB_MODE": "live", "ROOK_BOB_BIN": str(bob)}
    proc = subprocess.run(["bash", str(DEPLOY / "start.sh")], env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and "BOB_API_KEY" in proc.stderr


# --- demo catalog and allowlist ---


def test_demo_catalog_is_allowlisted_and_pinned() -> None:
    allowlist = Allowlist.from_yaml(DEPLOY / "demos" / "allowlist.yaml")
    demos = load_demo_repos(DEPLOY / "demos" / "demos.yaml")
    # ROOK-039: a demo app is offered once its recorded hosted replay ends "Fixed and verified".
    assert [d.ref for d in demos] == ["rook-demo/minishop", "tony19053000/shop-app"]
    for demo in demos:
        entry: AllowlistEntry = allowlist.get(demo.ref, demo.commit)
        assert entry.app_dir == Path("/opt/rook/demos") / demo.name
    assert "/opt/rook/demos/minishop/" in (DEPLOY / "Dockerfile").read_text()


def test_minishop_features_the_rule_its_hosted_replay_verifies() -> None:
    """The web's guest default approves only the featured rule: the one whose recorded path verifies."""
    demos = load_demo_repos(DEPLOY / "demos" / "demos.yaml")
    assert next(d for d in demos if d.name == "minishop").featured_rule == "refunded_total_le_paid"


def test_the_hosted_image_can_run_the_minishop_regression_tests() -> None:
    """ROOK-039c: replay runs execute the allowlisted `test` command (pytest) from the workspace copy."""
    entry = Allowlist.from_yaml(DEPLOY / "demos" / "allowlist.yaml").get(
        "rook-demo/minishop", "406059b53767b10f157b4eb92105d10af6a0c44d")
    assert entry.commands["test"][:3] == ["{python}", "-m", "pytest"]
    assert "asyncio_mode=auto" in entry.commands["test"] and entry.command_timeout <= 600
    assert "uv sync --frozen --no-dev --group sandbox" in (DEPLOY / "Dockerfile").read_text()


def test_build_demos_skips_comments_and_rejects_unpinned(tmp_path: Path) -> None:
    script = DEPLOY / "demos" / "build-demos.sh"
    comments = tmp_path / "comments.txt"  # the real repos.txt clones from GitHub: keep only its comments
    comments.write_text("".join(ln for ln in (DEPLOY / "demos" / "repos.txt").read_text().splitlines(True)
                                if ln.startswith("#") or not ln.strip()))
    ok = subprocess.run(["bash", str(script), str(comments), str(tmp_path / "d")],
                        capture_output=True, text=True, check=False)
    assert ok.returncode == 0, ok.stderr
    bad = tmp_path / "repos.txt"
    bad.write_text("owner/app main https://example.invalid/app.git none\n")
    proc = subprocess.run(["bash", str(script), str(bad), str(tmp_path / "d")], capture_output=True, text=True, check=False)
    assert proc.returncode == 1 and "40-char SHA" in proc.stderr


# --- compose and Caddy ---


def compose() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY / "docker-compose.yml").read_text())


def test_rook_is_reachable_only_through_caddy() -> None:
    services = compose()["services"]
    assert "ports" not in services["rook"]
    assert services["rook"]["expose"] == ["8000"]
    assert services["caddy"]["ports"] == ["${ROOK_HTTP_PORT:-80}:80", "${ROOK_HTTPS_PORT:-443}:443"]


def test_rook_settings_and_secret_source() -> None:
    rook = compose()["services"]["rook"]
    env = rook["environment"]
    assert env["ROOK_TRUSTED_PROXY_HOPS"] == "2"
    assert env["ROOK_PUBLIC_URL"].startswith("https://${ROOK_HOST:?")  # the `rook login` OAuth callback
    assert env["ROOK_BOB_MODE"] == "${ROOK_BOB_MODE:-replay}"
    assert env["ROOK_DB_PATH"].startswith("/data/") and "rook-data:/data" in rook["volumes"]
    assert "ROOK_DAILY_COIN_CAP" in env and "ROOK_WEB_ORIGINS" in env
    assert rook["env_file"] == ["${ROOK_ENV_FILE:-/etc/rook/rook.env}"]
    for name in SECRET_NAMES:
        assert name not in env, f"{name} comes only from the root-only env file"
    assert rook["cap_drop"] == ["ALL"]


def github_runs_override() -> dict[str, Any]:
    return yaml.safe_load((DEPLOY / "docker-compose.github-runs.yml").read_text())


def test_the_default_stack_has_no_docker_socket_and_github_runs_off() -> None:
    """ROOK-050: the hosted server runs only the allowlisted example repos (ProcessSandbox, no Docker), so the
    default compose gives no container the socket, needs no DOCKER_GID and keeps workspaces on the data volume."""
    text = (DEPLOY / "docker-compose.yml").read_text()
    doc = compose()
    rook = doc["services"]["rook"]
    assert rook["environment"]["ROOK_GITHUB_RUNS_MAX"] == "0"
    assert rook["environment"]["ROOK_WORKSPACES"].startswith("/data/") and "rook-data:/data" in rook["volumes"]
    assert "ROOK_SANDBOX_NETWORK" not in rook["environment"]
    assert "group_add" not in rook and "networks" not in rook and "networks" not in doc
    for service in doc["services"].values():
        assert not any("docker.sock" in v for v in service.get("volumes", []))
        assert not any(v.startswith("/var/lib/rook/") for v in service.get("volumes", []))
    assert "DOCKER_GID" not in text and "docker.sock:" not in text


def test_the_github_runs_override_adds_the_socket_same_path_workspaces_and_the_sandbox_network() -> None:
    """ROOK-041, opt-in since ROOK-050: sibling sandbox containers through the host socket. The daemon resolves
    bind paths on the host, so the workspaces folder is mounted at the same path; the proxy joins `rook-sandbox`."""
    doc = github_runs_override()
    assert set(doc["services"]) == {"rook"}  # Caddy never gets the socket or the sandbox network
    rook = doc["services"]["rook"]
    workspaces = rook["environment"]["ROOK_WORKSPACES"]
    assert workspaces == "/var/lib/rook/workspaces" and f"{workspaces}:{workspaces}" in rook["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in rook["volumes"]
    assert len(rook["group_add"]) == 1 and rook["group_add"][0].startswith("${DOCKER_GID:?")
    assert rook["environment"]["ROOK_GITHUB_RUNS_MAX"] == "${ROOK_GITHUB_RUNS_MAX:-1}"
    assert rook["environment"]["ROOK_SANDBOX_NETWORK"] == doc["networks"]["sandbox"]["name"] == "rook-sandbox"
    assert rook["networks"] == ["default", "sandbox"] and "privileged" not in rook
    assert compose()["services"]["rook"]["cap_drop"] == ["ALL"]  # the base hardening stays (override adds only)
    dockerfile = (DEPLOY / "Dockerfile").read_text()
    assert re.search(r"COPY --from=docker:[0-9.]+-cli@sha256:[0-9a-f]{64} \\\n\s+/usr/local/bin/docker ", dockerfile)
    assert "/usr/local/libexec/docker/cli-plugins/" in dockerfile


def compose_config(tmp_path: Path, *files: str, extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    empty = tmp_path / "rook.env"
    empty.touch()
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "ROOK_ENV_FILE": str(empty),
           "ROOK_HOST": "203-0-113-7.sslip.io", **(extra or {})}
    args = [arg for name in files for arg in ("-f", name)]
    return subprocess.run(["docker", "compose", *args, "config"], cwd=DEPLOY, env=env, capture_output=True,
                          text=True, timeout=60, check=False)


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI (compose config only, no daemon)")
def test_compose_renders_without_docker_gid_and_the_override_needs_it(tmp_path: Path) -> None:
    base = compose_config(tmp_path, "docker-compose.yml")
    assert base.returncode == 0, base.stderr
    assert "docker.sock" not in base.stdout and "group_add" not in base.stdout
    both = ("docker-compose.yml", "docker-compose.github-runs.yml")
    assert "DOCKER_GID" in compose_config(tmp_path, *both).stderr  # the override refuses to render without it
    on = compose_config(tmp_path, *both, extra={"DOCKER_GID": "998"})
    assert on.returncode == 0, on.stderr
    assert "/var/run/docker.sock" in on.stdout and "group_add" in on.stdout and '"998"' in on.stdout


def test_caddy_appends_forwarded_for_and_streams() -> None:
    text = (DEPLOY / "Caddyfile").read_text()
    assert "trusted_proxies static 0.0.0.0/0 ::/0" in text
    assert "handle /api/v1/*" in text and "reverse_proxy rook:8000" in text
    assert "flush_interval -1" in text
    assert 'respond "Not found" 404' in text


# --- the secret helper (runs on the host as root) ---


def test_encode_single_line_is_literal() -> None:
    assert set_env.encode("BOB_API_KEY", "abc$HOME#x\\y\n") == "BOB_API_KEY='abc$HOME#x\\y'"


@pytest.mark.parametrize(("name", "value", "problem"), [
    ("PATH", "x", "not a settable secret"),
    ("BOB_API_KEY", "", "empty"),
    ("BOB_API_KEY", "a'b", "single quote"),
    ("BOB_API_KEY", "a\nb", "one line"),
    ("BOB_API_KEY", "a\x00b", "NUL"),
    ("ROOK_GUEST_SECRET", "short", "at least 32"),
    ("GITHUB_APP_PRIVATE_KEY", "not a pem", "not a PEM"),
    ("SUPABASE_JWT_SECRET", PEM, "one line"),
])
def test_encode_rejects(name: str, value: str, problem: str) -> None:
    with pytest.raises(set_env.SecretError, match=problem) as info:
        set_env.encode(name, value)
    if value.strip():
        assert value.strip() not in str(info.value)


def test_encode_pem_as_escaped_double_quoted_line() -> None:
    line = set_env.encode("GITHUB_APP_PRIVATE_KEY", PEM.replace("\n", "\r\n"))
    assert "\n" not in line
    assert line == 'GITHUB_APP_PRIVATE_KEY="' + PEM.replace("\n", "\\n") + '"'


def test_write_replaces_one_entry_and_is_private(tmp_path: Path) -> None:
    env_file = tmp_path / "rook.env"
    env_file.write_text("ROOK_GUEST_SECRET='g'\nBOB_API_KEY='old'\n")
    set_env.write(env_file, "BOB_API_KEY", "BOB_API_KEY='new'")
    assert env_file.read_text() == "ROOK_GUEST_SECRET='g'\nBOB_API_KEY='new'\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["rook.env"]


def test_main_reads_stdin_and_never_prints_the_value(tmp_path: Path) -> None:
    env_file = tmp_path / "rook.env"
    value = "bob_value_that_must_not_leak_0123456789"
    proc = subprocess.run([sys.executable, str(AWS / "remote" / "set_env.py"), "BOB_API_KEY", "--file",
                           str(env_file)], input=value + "\n", capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert value not in proc.stdout + proc.stderr
    assert env_file.read_text() == f"BOB_API_KEY='{value}'\n"
    bad = subprocess.run([sys.executable, str(AWS / "remote" / "set_env.py"), "BOB_API_KEY", "--file",
                          str(env_file)], input="it's\n", capture_output=True, text=True, check=False)
    assert bad.returncode == 2 and "it's" not in bad.stderr


# --- bash scripts with stub commands ---


def test_every_script_is_strict() -> None:
    for script in SCRIPTS:
        text = script.read_text()
        assert "set -euo pipefail" in text, script
        if script.name != "lib.sh":
            assert os.access(script, os.X_OK), f"{script} must be executable"


def test_aws_calls_go_through_the_uvx_wrapper() -> None:
    lib = (AWS / "lib.sh").read_text()
    assert 'uvx --from awscli aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"' in lib
    assert "AWS_PROFILE_NAME=rook" in lib and "AWS_REGION_NAME=us-west-2" in lib
    for script in SCRIPTS:
        if script.name != "lib.sh":
            assert "uvx" not in script.read_text(), f"{script} must call AWS only via lib.sh"


STUB_UVX = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Fake `uvx --from awscli aws ...`: logs the argv and answers from a tiny state dir.
    set -eu
    echo "$*" >> "$STUB_LOG"
    [[ "$1 $2 $3 $4 $5 $6 $7" == "--from awscli aws --profile rook --region us-west-2" ]] || { echo bad-prefix >&2; exit 9; }
    shift 7
    case "$1 $2" in
      "sts get-caller-identity") echo 123456789012 ;;
      "ec2 describe-vpcs") echo vpc-0stub ;;
      "ec2 describe-images") echo ami-0stub ;;
      "ec2 describe-key-pairs") echo None ;;
      "ec2 describe-security-groups") echo None ;;
      "ec2 describe-instances") cat "$STUB_STATE/instance" 2>/dev/null || echo None ;;
      "ec2 describe-addresses")
        if [[ -f "$STUB_STATE/eip" ]]; then
          case "$*" in *PublicIp*) echo 203.0.113.7 ;; *) echo eipalloc-0stub ;; esac
        else echo None; fi ;;
      "ec2 create-key-pair") echo "fake-key-material" ;;
      "ec2 create-security-group") echo sg-0stub ;;
      "ec2 run-instances") echo i-0stub | tee "$STUB_STATE/instance" ;;
      "ec2 allocate-address") touch "$STUB_STATE/eip"; echo eipalloc-0stub ;;
      *) : ;;
    esac
    """)


def stub_env(tmp_path: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    home = tmp_path / "home"
    for d in (bin_dir, state, home):
        d.mkdir(exist_ok=True)
    stubs = {
        "uvx": STUB_UVX,
        "curl": "#!/bin/sh\necho 198.51.100.4\n",
        "ssh": '#!/bin/sh\necho "ARGV $*" >> "$STUB_LOG"\ncat > "$STUB_STATE/ssh_stdin_$$"\n',
    }
    for name, body in stubs.items():
        path = bin_dir / name
        path.write_text(body)
        path.chmod(0o755)
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), "STUB_LOG": str(tmp_path / "log"),
            "STUB_STATE": str(state), **(extra or {})}


def run(script: Path, env: dict[str, str], stdin: str = "", *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], env=env, input=stdin, capture_output=True, text=True,
                          timeout=30, check=False)


def test_create_prints_the_plan_and_creates_nothing_on_no(tmp_path: Path) -> None:
    env = stub_env(tmp_path)
    proc = run(AWS / "create.sh", env, "n\n")
    assert proc.returncode == 1
    assert "WILL CREATE: key pair rook-ec2" in proc.stdout and "Nothing was created." in proc.stdout
    assert "SSH 22 from 198.51.100.4/32 only" in proc.stdout
    log = (tmp_path / "log").read_text()
    for verb in ("create-", "run-instances", "allocate-address", "authorize-", "associate-address"):
        assert verb not in log
    assert not (tmp_path / "home/.ssh/rook-ec2.pem").exists()


def test_create_on_yes_makes_a_locked_down_host(tmp_path: Path) -> None:
    env = stub_env(tmp_path)
    proc = run(AWS / "create.sh", env, "y\n")
    assert proc.returncode == 0, proc.stderr
    assert "https://203-0-113-7.sslip.io" in proc.stdout
    key = tmp_path / "home/.ssh/rook-ec2.pem"
    assert stat.S_IMODE(key.stat().st_mode) == 0o600
    log = (tmp_path / "log").read_text().splitlines()
    run_line = next(ln for ln in log if " run-instances " in ln)
    for part in ("--instance-type t3.small", "VolumeSize=30", "VolumeType=gp3", "HttpTokens=required",
                 "Key=Project,Value=rook", "file://", "--image-id ami-0stub"):
        assert part in run_line
    ssh_rules = [ln for ln in log if "authorize-security-group-ingress" in ln and "FromPort=22" in ln]
    assert len(ssh_rules) == 1 and "CidrIp=198.51.100.4/32" in ssh_rules[0]
    web = [ln for ln in log if "authorize-security-group-ingress" in ln and "FromPort=22" not in ln]
    assert len(web) == 4  # 80 and 443, IPv4 and IPv6


def test_user_data_has_no_secrets() -> None:
    text = (AWS / "user-data.sh").read_text()
    assert "docker.io" in text and "docker-compose-v2" in text and "unattended-upgrades" in text
    for name in SECRET_NAMES:
        assert name not in text


def test_set_secret_rejects_unknown_names_before_any_call(tmp_path: Path) -> None:
    env = stub_env(tmp_path)
    proc = run(AWS / "scripts" / "set-secret.sh", env, "x", "PATH")
    assert proc.returncode == 1 and "not a settable secret" in proc.stderr
    assert not (tmp_path / "log").exists()


def test_set_secret_pipes_the_pem_over_ssh_stdin_only(tmp_path: Path) -> None:
    env = stub_env(tmp_path)
    (tmp_path / "state" / "eip").touch()
    (tmp_path / "home" / ".ssh").mkdir()
    (tmp_path / "home" / ".ssh" / "rook-ec2.pem").write_text("k")
    proc = run(AWS / "scripts" / "set-secret.sh", env, PEM, "GITHUB_APP_PRIVATE_KEY")
    assert proc.returncode == 0, proc.stderr
    log = (tmp_path / "log").read_text()
    ssh_lines = [ln for ln in log.splitlines() if ln.startswith("ARGV ")]
    assert "set_env.py GITHUB_APP_PRIVATE_KEY" in ssh_lines[0]
    assert "docker compose up -d --force-recreate rook" in ssh_lines[1]
    assert "TEST KEY" not in log and "TEST KEY" not in proc.stdout + proc.stderr
    stdins = [p.read_text() for p in (tmp_path / "state").glob("ssh_stdin_*")]
    assert PEM in stdins


def test_deploy_validates_settings_before_any_call(tmp_path: Path) -> None:
    env = stub_env(tmp_path, {"ROOK_WEB_ORIGINS": "*"})
    proc = run(AWS / "deploy.sh", env)
    assert proc.returncode == 1 and "ROOK_WEB_ORIGINS" in proc.stderr
    env = stub_env(tmp_path, {"ROOK_BOB_MODE": "yolo"})
    proc = run(AWS / "deploy.sh", env)
    assert proc.returncode == 1 and "ROOK_BOB_MODE" in proc.stderr
    assert not (tmp_path / "log").exists()


def test_deploy_rsync_excludes_secrets_and_local_state() -> None:
    text = (AWS / "deploy.sh").read_text()
    for pattern in (".git/", "node_modules/", ".venv/", "/web/", ".env*", "*.pem"):
        assert f"--exclude '{pattern}'" in text
    assert "sudo docker compose $compose_files up -d --build --remove-orphans" in text and "/api/v1/health" in text


DEPLOY_SSH = textwrap.dedent("""\
    #!/bin/sh
    echo "ARGV $*" >> "$STUB_LOG"
    cat > "$STUB_STATE/ssh_stdin_$$"
    case "$*" in *"stat -c %g /var/run/docker.sock"*) echo 998 ;; esac
    """)


def deploy_with_stubs(tmp_path: Path, extra: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """deploy.sh end to end against stub ssh/rsync/curl: (the remote commands, what was written to deploy/.env)."""
    env = stub_env(tmp_path, extra)
    for name, body in {"ssh": DEPLOY_SSH, "rsync": "#!/bin/sh\nexit 0\n"}.items():
        (tmp_path / "bin" / name).write_text(body)
        (tmp_path / "bin" / name).chmod(0o755)
    (tmp_path / "state" / "eip").touch()
    (tmp_path / "home" / ".ssh").mkdir()
    (tmp_path / "home" / ".ssh" / "rook-ec2.pem").write_text("k")
    proc = run(AWS / "deploy.sh", env)
    assert proc.returncode == 0, proc.stderr
    remote = [ln for ln in (tmp_path / "log").read_text().splitlines() if ln.startswith("ARGV ")]
    stdins = [p.read_text() for p in (tmp_path / "state").glob("ssh_stdin_*")]
    dotenv = next(s for s in stdins if s.startswith("ROOK_HOST="))
    return remote, dotenv.splitlines()


def test_deploy_by_default_needs_no_docker_socket(tmp_path: Path) -> None:
    remote, dotenv = deploy_with_stubs(tmp_path)
    assert not any("docker.sock" in ln or "/var/lib/rook/workspaces" in ln for ln in remote)
    assert not any(ln.startswith(("DOCKER_GID=", "COMPOSE_FILE=")) for ln in dotenv)
    assert "ROOK_HOST=203-0-113-7.sslip.io" in dotenv
    up = next(ln for ln in remote if "docker compose" in ln)
    assert "docker compose -f docker-compose.yml up -d --build --remove-orphans" in up
    assert "github-runs" not in up


def test_deploy_with_github_runs_uses_the_override_and_the_socket_group(tmp_path: Path) -> None:
    remote, dotenv = deploy_with_stubs(tmp_path, {"ROOK_GITHUB_RUNS": "1"})
    assert any("stat -c %g /var/run/docker.sock" in ln for ln in remote)
    assert any("install -d -o 10001 -g 10001 -m 750 /var/lib/rook/workspaces" in ln for ln in remote)
    # COMPOSE_FILE keeps the override on for every later `docker compose` in deploy/ (set-secret.sh's recreate)
    assert "DOCKER_GID=998" in dotenv and "COMPOSE_FILE=docker-compose.yml:docker-compose.github-runs.yml" in dotenv
    up = next(ln for ln in remote if "docker compose" in ln)
    assert "docker compose -f docker-compose.yml -f docker-compose.github-runs.yml up -d --build --remove-orphans" in up


def test_deploy_rejects_a_bad_github_runs_flag(tmp_path: Path) -> None:
    proc = run(AWS / "deploy.sh", stub_env(tmp_path, {"ROOK_GITHUB_RUNS": "yes"}))
    assert proc.returncode == 1 and "ROOK_GITHUB_RUNS" in proc.stderr
    assert not (tmp_path / "log").exists()


# --- the smoke client ---


def test_smoke_answers_like_a_demo_user() -> None:
    spec = importlib.util.spec_from_file_location("rook_deploy_smoke", DEPLOY / "smoke.py")
    assert spec and spec.loader
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    rules = {"rules": [{"id": "r1", "accepted": True, "check": "refunded <= paid"},
                       {"id": "r2", "accepted": True, "check": "stock >= 0"}]}
    assert smoke.answer_for({"kind": "approve_rules", "payload": rules}) == ["r1"]
    featured = {"rules": [{**rules["rules"][0], "featured": False}, {**rules["rules"][1], "featured": True}]}
    assert smoke.answer_for({"kind": "approve_rules", "payload": featured}) == ["r2"]
    assert smoke.answer_for({"kind": "approve_rules", "payload": featured}, "all") == "all"
    assert smoke.answer_for({"kind": "fix"}) == "yes"
    assert smoke.answer_for({"kind": "menu", "options": [{"id": "retry"}, {"id": "report"}]}) == "report"
    verify = {"cx_id": "cx_001", "verified": True, "summary": "4/4 checks passed"}
    committed = {"cx_id": "cx_001", "branch": "rook/fix-cx-001"}
    done = {"status": "done", "summary": "Fixed and verified cx_001 (rule r1); committed to local branch"}
    assert smoke.fix_verified(done, {"verify.done": verify, "fix.committed": committed})
    assert not smoke.fix_verified(done, {"verify.done": {**verify, "verified": False}, "fix.committed": committed})
    assert not smoke.fix_verified(done, {"verify.done": verify})  # never committed
    live = {"status": "done", "summary": "a fix was written to the run's workspace but NOT verified"}
    assert not smoke.fix_verified(live, {})
    fresh = {"cx_id": "cx_001", "check": "fresh_search", "status": "failed", "detail": "new violation of rule r2"}
    unverified = {"verify.done": {**verify, "verified": False}, "fresh_search": fresh}
    honest = {"status": "done", "summary": "Found and saved cx_001; the fix for rule r1 was written and the exact "
              "replay now passes, but the fresh search found another approved rule still broken: r2. NOT "
              "verified: the patch was reverted and not shipped. Run `rook` from the CLI on your own copy to continue."}
    assert smoke.honestly_unverified(honest, unverified)
    assert not smoke.honestly_unverified(honest, {**unverified, "fix.committed": committed})
    assert not smoke.honestly_unverified(honest, {"verify.done": verify, "fresh_search": fresh})
    assert not smoke.honestly_unverified(honest, {})  # VERIFY never ran
    leaky = {**honest, "summary": honest["summary"] + " no recording for key " + "a" * 64}
    assert not smoke.honestly_unverified(leaky, unverified)


# --- Docker: the env file reaches the container as the server expects ---


@pytest.mark.docker
def test_env_file_round_trip_through_compose(tmp_path: Path) -> None:
    env_file = tmp_path / "rook.env"
    set_env.write(env_file, "GITHUB_APP_PRIVATE_KEY", set_env.encode("GITHUB_APP_PRIVATE_KEY", PEM))
    set_env.write(env_file, "BOB_API_KEY", set_env.encode("BOB_API_KEY", "a$HOME#b\\c"))
    (tmp_path / "compose.yml").write_text(textwrap.dedent(f"""\
        services:
          t:
            image: python:3.12-slim-bookworm
            env_file: [{env_file}]
            command: ["python", "-c", "import os, json; print(json.dumps([os.environ['GITHUB_APP_PRIVATE_KEY'], os.environ['BOB_API_KEY']]))"]
        """))
    proc = subprocess.run(["docker", "compose", "-p", "rookenvtest", "run", "--rm", "-T", "t"], cwd=tmp_path,
                          capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    pem, key = json.loads(proc.stdout.strip().splitlines()[-1])
    assert pem == PEM and key == "a$HOME#b\\c"
