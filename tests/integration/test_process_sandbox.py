"""ROOK-013: ProcessSandbox runs real subprocesses (no Docker, no Bob, so it is in the default suite)."""

import os
import random
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

from rook.engine.executor import Executor, StepResult
from rook.model.loader import load_model
from rook.model.schema import Step
from rook.sandbox import Allowlist, AllowlistEntry, ProcessSandbox, SandboxError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")

MINISHOP_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
MINISHOP_SHA = "0" * 40
MINISHOP = AllowlistEntry(
    repo="rook-fixtures/minishop",
    commit=MINISHOP_SHA,
    app_dir=MINISHOP_DIR,
    start=["{python}", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "{port}"],
    db_env="MINISHOP_DB",
    env={"MINISHOP_ADMIN_PASSWORD": "admin-pass"},  # the fixture's built-in default, not a secret
)

# A stdlib HTTP app that reports its env and pids, and starts a long-lived child process.
PROBE_APP = textwrap.dedent(
    """
    import json, os, subprocess, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            info = {"env": dict(os.environ), "pid": os.getpid(), "child": child.pid, "cwd": os.getcwd()}
            body = json.dumps(info).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            print("request", *args, flush=True)

    print("probe starting", flush=True)
    HTTPServer(("127.0.0.1", int(os.environ["PORT"])), Handler).serve_forever()
    """
)
PROBE_SHA = "1" * 40


@pytest.fixture
def probe_allowlist(tmp_path: Path) -> Allowlist:
    (tmp_path / "probe.py").write_text(PROBE_APP)
    entries = [
        AllowlistEntry(
            repo="rook-fixtures/probe",
            commit=PROBE_SHA,
            app_dir=tmp_path,
            start=["{python}", "probe.py"],
            db_env="DATABASE_PATH",
            env={"APP_MODE": "demo"},
            settable_env=frozenset({"SETUP_VALUE"}),
            commands={"hello": ["{python}", "-c", "import os; print('hi', os.environ.get('BOB_API_KEY'))"]},
        ),
        AllowlistEntry(
            repo="rook-fixtures/never-healthy",
            commit=PROBE_SHA,
            app_dir=tmp_path,
            start=["{python}", "-c", "import time; print('booting', flush=True); time.sleep(300)"],
            health_timeout=1.0,
        ),
        AllowlistEntry(
            repo="rook-fixtures/crashes",
            commit=PROBE_SHA,
            app_dir=tmp_path,
            start=["{python}", "-c", "import sys; print('boom: missing config', flush=True); sys.exit(3)"],
        ),
    ]
    return Allowlist(entries)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie (exited, not yet reaped by init) still answers kill(0); it is not running.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return False


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_gone(pids: list[int], timeout: float = 5.0) -> list[int]:
    deadline = time.monotonic() + timeout
    while (alive := [p for p in pids if _alive(p)]) and time.monotonic() < deadline:
        time.sleep(0.05)
    return alive


def _probe(base_url: str) -> dict:
    return httpx.get(base_url + "/", trust_env=False, timeout=5).json()


# --- minishop over real HTTP ---


async def test_minishop_runs_as_real_uvicorn_and_engine_finds_refund_bug() -> None:
    model = load_model(MINISHOP_DIR / "rook.yaml")
    with ProcessSandbox("rook-fixtures/minishop", MINISHOP_SHA, allowlist=Allowlist([MINISHOP])) as sandbox:
        base_url = sandbox.start()
        assert base_url.startswith("http://127.0.0.1:") and sandbox.running
        pid = sandbox.pid
        assert pid is not None
        assert "uvicorn" in Path(f"/proc/{pid}/cmdline").read_bytes().decode()

        async with Executor(model, base_url, env={"MINISHOP_ADMIN_PASSWORD": "admin-pass"}) as ex:
            ctx = ex.new_context()
            rng = random.Random(0)

            async def step(action: str, **params) -> StepResult:
                result = await ex.run_step(ctx, Step(action=action, params=params), rng)
                assert isinstance(result, StepResult)
                return result

            created = await step("create_product", price=100, stock=5)
            assert created.status == 200, created.error
            bought = await step("buy", quantity=1)
            assert bought.status == 200
            assert (await step("refund", amount=60)).status == 200
            assert (await step("refund", amount=50)).status == 200
            order = (await ex.read_state(ctx, "order"))["order"][bought.response_json["id"]]
            assert order == {**order, "paid": 100, "refunded": 110}  # refunded more than paid

        assert "GET /health" in sandbox.logs()
    assert not sandbox.running and not _group_alive(pid)


# --- env allowlist ---


def test_child_env_is_an_allowlist_and_host_secrets_do_not_leak(
    probe_allowlist: Allowlist, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOB_API_KEY", "sentinel-host-value")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sentinel-host-value")
    monkeypatch.setenv("GITHUB_TOKEN", "sentinel-host-value")
    with ProcessSandbox(
        "rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist, env={"SETUP_VALUE": "answered"}
    ) as sandbox:
        base_url = sandbox.start()
        info = _probe(base_url)
        env = info["env"]
        tmp = sandbox.temp_dir
        assert tmp is not None

        assert "sentinel-host-value" not in str(env)
        assert not {"BOB_API_KEY", "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN"} & env.keys()
        assert env["PORT"] == base_url.rsplit(":", 1)[1]
        assert env["DATABASE_PATH"] == str(tmp / "db" / "app.db")
        assert env["HOME"] == env["TMPDIR"] == str(tmp)
        assert env["APP_MODE"] == "demo" and env["SETUP_VALUE"] == "answered"
        assert Path(info["cwd"]) == tmp_path
        # Only the vars the sandbox sets (Python may add a few of its own, e.g. LC_CTYPE).
        expected = {
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "PYTHONUNBUFFERED",
            "PYTHONDONTWRITEBYTECODE",
            "PORT",
            "DATABASE_PATH",
            "APP_MODE",
            "SETUP_VALUE",
        }
        assert set(env) - expected <= {"LC_CTYPE"}

        hello = sandbox.exec(["{python}", "-c", "import os; print('hi', os.environ.get('BOB_API_KEY'))"])
        assert hello.ok and hello.stdout.strip() == "hi None"
    assert not tmp.exists()  # the temp dir (and its DB) is removed on stop


def test_exec_works_without_a_running_app(
    probe_allowlist: Allowlist, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOB_API_KEY", "sentinel-host-value")
    sandbox = ProcessSandbox("rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist)
    result = sandbox.exec(["{python}", "-c", "import os; print('hi', os.environ.get('BOB_API_KEY'))"])
    assert result.exit_code == 0 and result.stdout.strip() == "hi None"


# --- cleanup ---


def test_stop_kills_the_whole_process_group(probe_allowlist: Allowlist) -> None:
    sandbox = ProcessSandbox("rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist)
    info = _probe(sandbox.start())
    pgid = sandbox.pid
    assert pgid == info["pid"] and os.getpgid(info["child"]) == pgid
    assert _alive(info["child"])
    sandbox.stop()
    assert _wait_gone([info["pid"], info["child"]]) == []
    assert not _group_alive(pgid)
    sandbox.stop()  # idempotent


def test_exception_inside_with_block_cleans_up(probe_allowlist: Allowlist) -> None:
    sandbox = ProcessSandbox("rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist)
    with pytest.raises(RuntimeError, match="engine crashed"), sandbox:
        info = _probe(sandbox.start())
        tmp = sandbox.temp_dir
        raise RuntimeError("engine crashed")
    assert _wait_gone([info["pid"], info["child"]]) == []
    assert not _group_alive(info["pid"])
    assert tmp is not None and not tmp.exists()


def test_health_timeout_kills_the_app_and_reports_logs(probe_allowlist: Allowlist) -> None:
    sandbox = ProcessSandbox("rook-fixtures/never-healthy", PROBE_SHA, allowlist=probe_allowlist)
    with pytest.raises(SandboxError, match=r"not healthy after 1s(.|\n)*booting"):
        sandbox.start()
    assert sandbox.pid is None and sandbox.temp_dir is None
    assert "booting" in sandbox.logs()  # the last run's output stays readable after stop


def test_app_that_exits_early_fails_fast_with_its_output(probe_allowlist: Allowlist) -> None:
    sandbox = ProcessSandbox("rook-fixtures/crashes", PROBE_SHA, allowlist=probe_allowlist)
    started = time.monotonic()
    with pytest.raises(SandboxError, match=r"exited with code 3(.|\n)*missing config"):
        sandbox.start()
    assert time.monotonic() - started < 10


def test_restart_keeps_the_url_and_gives_fresh_state(probe_allowlist: Allowlist) -> None:
    with ProcessSandbox("rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist) as sandbox:
        url = sandbox.start()
        first = _probe(url)
        first_tmp = sandbox.temp_dir
        assert sandbox.restart() == url
        second = _probe(url)
        assert second["pid"] != first["pid"]
        assert second["env"]["DATABASE_PATH"] != first["env"]["DATABASE_PATH"]
        assert first_tmp is not None and not first_tmp.exists()
        assert _wait_gone([first["pid"], first["child"]]) == []


def test_starting_twice_is_an_error(probe_allowlist: Allowlist) -> None:
    with ProcessSandbox("rook-fixtures/probe", PROBE_SHA, allowlist=probe_allowlist) as sandbox:
        sandbox.start()
        with pytest.raises(SandboxError, match="already started"):
            sandbox.start()


def test_sigterm_ignoring_app_is_still_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rook.sandbox.process.STOP_GRACE", 0.5)
    (tmp_path / "stubborn.py").write_text(
        textwrap.dedent(
            """
        import os, signal
        from http.server import BaseHTTPRequestHandler, HTTPServer
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.send_header("Content-Length", "0"); self.end_headers()

        HTTPServer(("127.0.0.1", int(os.environ["PORT"])), H).serve_forever()
        """
        )
    )
    entry = AllowlistEntry(
        repo="rook-fixtures/stubborn",
        commit=PROBE_SHA,
        app_dir=tmp_path,
        start=["{python}", "stubborn.py"],
        health_path="/",
    )
    sandbox = ProcessSandbox("rook-fixtures/stubborn", PROBE_SHA, allowlist=Allowlist([entry]))
    sandbox.start()
    pid = sandbox.pid
    assert pid is not None
    sandbox.stop()
    assert not _alive(pid) and not _group_alive(pid)
