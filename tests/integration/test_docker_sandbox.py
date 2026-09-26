"""ROOK-014: DockerSandbox against a real Docker daemon (`uv run pytest -m docker`).

Every test checks that nothing labelled with its sandbox name survives: containers, networks, volumes
and the images the sandbox built.
"""

import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import httpx
import pytest

from rook.agents.schemas import SandboxPlan
from rook.sandbox import DockerSandbox, SandboxError
from rook.sandbox.reaper import docker

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed"),
]

MINISHOP_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
# A fake value: it must never show up inside a container.
FAKE_HOST_SECRET = "fake-bob-key-for-leak-test"
HTTP_SERVER = "python -m http.server 8000"
SIMPLE_DOCKERFILE = textwrap.dedent(
    """
    FROM python:3.12-slim
    WORKDIR /srv
    COPY index.html /srv/index.html
    CMD ["python", "-m", "http.server", "8000"]
    """
)


def leftovers(name: str) -> dict[str, list[str]]:
    label = f"label=rook.run={name}"
    return {
        kind: docker([*cmd, "--filter", label]).stdout.split()
        for kind, cmd in {
            "containers": ["ps", "-aq"],
            "networks": ["network", "ls", "-q"],
            "volumes": ["volume", "ls", "-q"],
            "images": ["image", "ls", "-q"],
        }.items()
    }


def assert_clean(name: str, wait: float = 0.0) -> None:
    deadline = time.monotonic() + wait
    while True:
        left = leftovers(name)
        if not any(left.values()) or time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    assert not any(left.values()), left


def inspect(container: str) -> dict:
    return json.loads(docker(["inspect", container]).stdout)[0]


def assert_hardened(info: dict, *, read_only: bool = False) -> None:
    host = info["HostConfig"]
    assert host["Privileged"] is False
    assert host["CapDrop"] == ["ALL"] and not host.get("CapAdd")
    assert any(opt.startswith("no-new-privileges") for opt in host["SecurityOpt"])
    assert host["PidsLimit"] == 512
    assert host["Memory"] == 2 * 1024**3
    assert host["NanoCpus"] == 2 * 10**9
    assert host["NetworkMode"] not in ("host", "default", "bridge")
    assert host["PidMode"] == "" and host["IpcMode"] in ("private", "shareable")
    assert not host.get("Devices")
    assert all(m["Type"] != "bind" for m in info["Mounts"])
    for bindings in (host.get("PortBindings") or {}).values():
        assert all(b["HostIp"] == "127.0.0.1" for b in bindings)
    assert info["Config"]["User"] not in ("", "0", "root")
    assert not info["Config"]["User"].startswith("0:")
    assert host["ReadonlyRootfs"] is read_only
    env_names = {e.partition("=")[0] for e in info["Config"]["Env"]}
    assert "BOB_API_KEY" not in env_names
    assert not any(FAKE_HOST_SECRET in e for e in info["Config"]["Env"])


@pytest.fixture(autouse=True)
def fake_host_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOB_API_KEY", FAKE_HOST_SECRET)


@pytest.fixture
def minishop_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    shutil.copytree(MINISHOP_DIR, ws, ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    return ws


@pytest.fixture
def static_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / ".rook-sandbox").mkdir(parents=True)
    (ws / "index.html").write_text("hello from the sandbox\n")
    (ws / ".rook-sandbox" / "Dockerfile").write_text(SIMPLE_DOCKERFILE)
    return ws


def test_minishop_builds_and_runs_from_a_generated_dockerfile(minishop_ws: Path) -> None:
    plan = SandboxPlan(
        mode="command",
        build="pip install --no-cache-dir fastapi==0.141.1 uvicorn==0.54.0",
        start="uvicorn app:app --host 0.0.0.0 --port 8000",
        port=8000,
        health_path="/health",
        env_required=["MINISHOP_ADMIN_PASSWORD"],
        env_defaults={"MINISHOP_MODE": "bugs"},
    )
    sandbox = DockerSandbox(
        minishop_ws, run_id="minishop", env={"MINISHOP_ADMIN_PASSWORD": "admin-pass"}, read_only=True
    )
    with sandbox:
        base_url = sandbox.start(plan)
        name = sandbox.name
        assert name is not None and base_url.startswith("http://127.0.0.1:")
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            assert client.get("/health").status_code == 200
            signup = client.post("/auth/signup", json={"email": "a@b.c", "password": "pw-1"})
            assert signup.status_code == 200, signup.text
        assert sandbox._container is not None
        assert_hardened(inspect(sandbox._container), read_only=True)
        env = sandbox.exec(["python", "-c", "import json, os; print(json.dumps(dict(os.environ)))"])
        assert env.ok, env.stderr
        app_env = json.loads(env.stdout)
        assert app_env["MINISHOP_ADMIN_PASSWORD"] == "admin-pass" and app_env["MINISHOP_MODE"] == "bugs"
        assert "BOB_API_KEY" not in app_env and FAKE_HOST_SECRET not in env.stdout
        assert sandbox.exec(["id", "-u"]).stdout.strip() == "10001"
        assert "Uvicorn running" in sandbox.logs(50) or "Application startup complete" in sandbox.logs(50)
    assert_clean(name)
    assert "Application startup complete" in sandbox.logs(50)  # kept after stop


def test_dockerfile_mode_restart_gives_a_fresh_container_on_the_same_url(static_ws: Path) -> None:
    sandbox = DockerSandbox(static_ws, run_id="restart")
    try:
        plan = SandboxPlan(mode="dockerfile", port=8000, health_path="/index.html")
        base_url = sandbox.start(plan)
        name, first = sandbox.name, sandbox._container
        assert httpx.get(base_url + "/index.html", trust_env=False).text == "hello from the sandbox\n"
        assert_hardened(inspect(first))
        assert sandbox.restart() == base_url
        assert sandbox._container != first
        assert sandbox.running
        assert httpx.get(base_url + "/index.html", trust_env=False).status_code == 200
    finally:
        sandbox.stop()
    assert name is not None
    assert_clean(name)
    assert not sandbox.running
    sandbox.stop()  # idempotent


def test_compose_mode_is_hardened_and_never_sees_host_secrets(static_ws: Path) -> None:
    (static_ws / "compose.yaml").write_text(
        textwrap.dedent(
            """
        services:
          web:
            build: {context: ., dockerfile: .rook-sandbox/Dockerfile}
            ports: ["8000:8000"]
            container_name: fixed-name
            restart: always
            environment:
              LEAK: "${BOB_API_KEY:-none}"
            volumes: ["data:/data", "./index.html:/srv/copy.html:ro"]
          helper:
            image: python:3.12-slim
            command: ["python", "-c", "import time; time.sleep(600)"]
            user: root
        volumes:
          data: {}
        """
        )
    )
    plan = SandboxPlan(
        mode="compose", start="web", port=8000, health_path="/copy.html", env_defaults={"GREETING": "cost $5"}
    )
    sandbox = DockerSandbox(static_ws, run_id="compose")
    with sandbox:
        base_url = sandbox.start(plan)
        name = sandbox.name
        assert name is not None
        assert httpx.get(base_url + "/copy.html", trust_env=False).status_code == 200
        env = sandbox.exec(["python", "-c", "import os; print(os.environ['LEAK'], os.environ['GREETING'])"])
        assert env.stdout.strip() == "none cost $5"
        containers = docker(["ps", "-q", "--filter", f"label=rook.run={name}"]).stdout.split()
        assert len(containers) == 3  # web, helper and Rook's proxy
        for cid in containers:
            info = inspect(cid)
            if info["Config"]["Labels"]["com.docker.compose.service"] == "rook-proxy":
                assert info["Config"]["User"] == "65534:65534" and info["HostConfig"]["ReadonlyRootfs"]
                assert info["HostConfig"]["CapDrop"] == ["ALL"]
                continue
            assert not info["HostConfig"].get("PortBindings")  # only the proxy publishes
            assert_hardened_compose(info)
            assert info["HostConfig"]["RestartPolicy"]["Name"] == "no"
            assert info["Name"] != "/fixed-name"
        assert sandbox.restart() == base_url
    assert_clean(name)


def assert_hardened_compose(info: dict) -> None:
    host = info["HostConfig"]
    assert host["Privileged"] is False and host["CapDrop"] == ["ALL"] and not host.get("CapAdd")
    assert any(opt.startswith("no-new-privileges") for opt in host["SecurityOpt"])
    assert host["PidsLimit"] == 512 and host["Memory"] == 2 * 1024**3
    assert info["Config"]["User"] == "10001:10001"
    for bindings in (host.get("PortBindings") or {}).values():
        assert all(b["HostIp"] == "127.0.0.1" for b in bindings)
    assert "BOB_API_KEY" not in {e.partition("=")[0] for e in info["Config"]["Env"]}


def test_a_failing_build_reports_its_output_and_leaves_nothing(static_ws: Path) -> None:
    sandbox = DockerSandbox(static_ws, run_id="badbuild")
    plan = SandboxPlan(mode="command", build="echo build-broke-here && exit 3", start=HTTP_SERVER, port=8000)
    with pytest.raises(SandboxError, match="docker build failed") as info:
        sandbox.start(plan)
    assert "build-broke-here" in str(info.value)
    assert "build-broke-here" in sandbox.logs(200)
    assert sandbox.name is None
    assert not docker(
        ["ps", "-aq", "--filter", "label=rook.run", "--filter", "name=rook-badbuild-"]
    ).stdout.strip()
    images = docker(
        ["image", "ls", "--filter", "label=rook.run", "--format", "{{.Repository}}"]
    ).stdout.split()
    assert not [i for i in images if i.startswith("rook-badbuild-")]


def test_an_app_that_exits_fails_fast_with_its_logs(static_ws: Path) -> None:
    sandbox = DockerSandbox(static_ws, run_id="crashapp", health_timeout=30)
    plan = SandboxPlan(mode="command", start="echo app-says-bye; exit 1", port=8000)
    started = time.monotonic()
    with pytest.raises(SandboxError, match="exited before it was healthy") as info:
        sandbox.start(plan)
    assert time.monotonic() - started < 25
    assert "app-says-bye" in str(info.value)


CRASH_SCRIPT = textwrap.dedent(
    """
    import os, signal, sys, time
    from pathlib import Path
    from rook.agents.schemas import SandboxPlan
    from rook.sandbox import DockerSandbox

    how = sys.argv[2]
    sandbox = DockerSandbox(Path(sys.argv[1]), run_id="crash-" + how)
    sandbox.start(SandboxPlan(mode="command", start="python -m http.server 8000", port=8000, health_path="/"))
    print(sandbox.name, flush=True)
    if how == "exception":
        raise RuntimeError("boom mid-run")
    if how == "sigkill":
        os.kill(os.getpid(), signal.SIGKILL)
    time.sleep(120)  # "sigterm": the test kills us
    """
)


@pytest.mark.parametrize("how", ["exception", "sigterm", "sigkill"])
def test_nothing_survives_a_crash_of_the_rook_process(static_ws: Path, tmp_path: Path, how: str) -> None:
    script = tmp_path / "crash.py"
    script.write_text(CRASH_SCRIPT)
    proc = subprocess.Popen(
        [sys.executable, str(script), str(static_ws), how],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        name = proc.stdout.readline().strip()
        assert name.startswith(f"rook-crash-{how}-"), proc.stderr.read() if proc.stderr else ""
        if how == "sigterm":
            assert leftovers(name)["containers"], "the sandbox should be running before the crash"
            proc.send_signal(signal.SIGTERM)
        code = proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    expected = {"exception": 1, "sigterm": -signal.SIGTERM, "sigkill": -signal.SIGKILL}[how]
    assert code == expected
    # sigkill: only the watchdog can clean up, asynchronously.
    assert_clean(name, wait=60.0 if how == "sigkill" else 0.0)
    assert os.environ["BOB_API_KEY"] == FAKE_HOST_SECRET  # the fixture is still active


PROBE = textwrap.dedent(
    """
    import json, socket, sys
    results = {}
    for target in json.loads(sys.argv[1]):
        host, port = target.rsplit(":", 1)
        try:
            socket.create_connection((host, int(port)), timeout=3).close()
            results[target] = "open"
        except OSError as exc:
            results[target] = type(exc).__name__
    try:
        socket.getaddrinfo("example.com", 80)
        results["dns"] = "resolved"
    except OSError as exc:
        results["dns"] = type(exc).__name__
    print(json.dumps(results))
    """
)


def _gateways(network: str) -> list[str]:
    info = json.loads(docker(["network", "inspect", network]).stdout)[0]
    out = []
    for cfg in info["IPAM"]["Config"] or []:
        if cfg.get("Gateway"):
            out.append(cfg["Gateway"])
        if cfg.get("Subnet") and ":" not in cfg["Subnet"]:  # where the gateway would be
            out.append(str(next(ipaddress.ip_network(cfg["Subnet"]).hosts())))
    return out


@pytest.fixture
def host_listener() -> "tuple[int, threading.Event]":
    """A TCP service on every host interface, like a dev database the app must not reach."""
    server = socket.create_server(("0.0.0.0", 0))
    server.settimeout(0.2)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
                conn.close()
            except OSError:
                continue

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1], stop
    stop.set()
    thread.join()
    server.close()


def assert_no_egress(sandbox: DockerSandbox, networks: list[str], port: int) -> None:
    gateways = sorted({gw for net in [*networks, "bridge"] for gw in _gateways(net)})
    # Positive control: the listener is reachable on the publish/bridge gateways from the host itself.
    socket.create_connection((_gateways("bridge")[0], port), timeout=3).close()
    targets = ["1.1.1.1:80", "8.8.8.8:53", "169.254.169.254:80", *(f"{gw}:{port}" for gw in gateways)]
    result = sandbox.exec(["python", "-c", PROBE, json.dumps(targets)], timeout=120)
    assert result.ok, result.stderr
    reached = json.loads(result.stdout)
    assert reached.pop("dns") != "resolved"
    assert all(v != "open" for v in reached.values()), reached


def test_the_app_cannot_reach_the_internet_or_the_host(static_ws: Path, host_listener: tuple) -> None:
    port, _ = host_listener
    sandbox = DockerSandbox(static_ws, run_id="egress")
    with sandbox:
        base_url = sandbox.start(SandboxPlan(mode="command", start=HTTP_SERVER, port=8000, health_path="/"))
        name = sandbox.name
        assert name is not None
        # The engine still reaches the app through the proxy on 127.0.0.1.
        assert httpx.get(base_url + "/index.html", trust_env=False).status_code == 200
        internal = json.loads(docker(["network", "inspect", name]).stdout)[0]
        assert internal["Internal"] is True
        app = inspect(f"{name}-app")
        assert list(app["NetworkSettings"]["Networks"]) == [name]
        assert not app["HostConfig"].get("PortBindings")
        proxy = inspect(f"{name}-proxy")
        assert proxy["HostConfig"]["CapDrop"] == ["ALL"] and proxy["HostConfig"]["ReadonlyRootfs"] is True
        assert proxy["Config"]["User"] == "65534:65534"
        for bindings in proxy["HostConfig"]["PortBindings"].values():
            assert all(b["HostIp"] == "127.0.0.1" for b in bindings)
        assert_no_egress(sandbox, [name, f"{name}-pub"], port)
    assert_clean(name)


def test_compose_services_cannot_reach_the_internet_or_the_host(
    static_ws: Path, host_listener: tuple
) -> None:
    port, _ = host_listener
    (static_ws / "compose.yaml").write_text(
        "services:\n  web:\n    build: {context: ., dockerfile: .rook-sandbox/Dockerfile}\n"
    )
    sandbox = DockerSandbox(static_ws, run_id="compose-egress")
    with sandbox:
        base_url = sandbox.start(SandboxPlan(mode="compose", port=8000, health_path="/index.html"))
        name = sandbox.name
        assert name is not None
        assert httpx.get(base_url + "/index.html", trust_env=False).status_code == 200
        networks = docker(["network", "ls", "--filter", f"label=rook.run={name}", "--format", "{{.Name}}"])
        assert_no_egress(sandbox, networks.stdout.split(), port)
    assert_clean(name)


def test_a_second_service_cannot_take_over_the_apps_name(static_ws: Path) -> None:
    """Reviewer repro: `evil` with `hostname: web` used to receive about half of the proxied requests."""
    (static_ws / "compose.yaml").write_text(
        textwrap.dedent(
            """
            services:
              web:
                build: {context: ., dockerfile: .rook-sandbox/Dockerfile}
              evil:
                image: python:3.12-slim
                hostname: web
                domainname: local
                command: ["sh", "-c", "mkdir -p /tmp/e && echo evil > /tmp/e/index.html && cd /tmp/e && python -m http.server 8000"]
            """
        )
    )
    sandbox = DockerSandbox(static_ws, run_id="dns-takeover")
    with sandbox:
        base_url = sandbox.start(
            SandboxPlan(mode="compose", start="web", port=8000, health_path="/index.html")
        )
        name = sandbox.name
        assert name is not None
        # Make sure evil is up and serving, so a round-robin would really hit it.
        evil = docker(
            [
                "ps",
                "-q",
                "--filter",
                f"label=rook.run={name}",
                "--filter",
                "label=com.docker.compose.service=evil",
            ]
        ).stdout.split()
        assert len(evil) == 1
        time.sleep(3)
        served = docker(
            [
                "exec",
                evil[0],
                "python",
                "-c",
                "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/').read())",
            ]
        )
        assert "evil" in served.stdout, served.stderr
        with httpx.Client(base_url=base_url, trust_env=False) as client:
            bodies = [client.get("/index.html", headers={"Connection": "close"}).text for _ in range(30)]
        assert set(bodies) == {"hello from the sandbox\n"}, bodies
    assert_clean(name)
