"""ROOK-039c: ProcessSandbox's replay-only `workspace` capability, with real subprocesses (default suite).

- Default (live mode on the server): the app and its commands run from the pristine allowlisted app dir.
- With `workspace=`: they run from the run's workspace copy, so the Surgeon's patch (here: the committed
  surgeon_minishop edit tapes, read only) is executed and the engine's Verifier passes on minishop.
- The `test` command may get exactly one extra argument, a regular test file inside that workspace;
  commands keep the scrubbed env (no BOB_API_KEY), get offline settings and a capped timeout.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx
import pytest
from test_process_sandbox import MINISHOP_DIR, PROBE_APP
from test_verify_minishop import ENV, MODEL, refund_cx

from rook.agents import edit_tape
from rook.agents.fix import SandboxHarness, fails_as_expected
from rook.core.events import EventBus
from rook.core.workspace import RepoSpec, prepare_workspace
from rook.engine.executor import Executor
from rook.engine.testrunner import TestRunner
from rook.engine.verifier import Verifier
from rook.export.counterexample import rule_only_model
from rook.sandbox import Allowlist, AllowlistEntry, ProcessSandbox, SandboxError

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")

TAPES = Path(__file__).parents[1] / "fixtures" / "recordings" / "surgeon_minishop"
TEST_TAPE = TAPES / "f20cd3daf9bdf040adf2f01e2ad817fe9a84178f61ba42ffa003caebad2b780b.edits.json"  # the native test
FIX_TAPE = TAPES / "a0051e21889843f7b58dbedfdaf82b910af63e93584e607fbdcb1782298842f9.edits.json"  # the app.py fix
NATIVE_TEST = "test_rook_cx_001.py"
PYTEST = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "asyncio_mode=auto"]
SHA = "2" * 40
MINISHOP = AllowlistEntry(
    repo="rook-fixtures/minishop",
    commit=SHA,
    app_dir=MINISHOP_DIR,
    start=["{python}", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "{port}"],
    db_env="MINISHOP_DB",
    env=ENV,
    commands={"test": PYTEST},
)
FAKE_KEY = "fake-bob-key-for-tests-only"  # not a real key: it must never reach a sandboxed process
# No braces in these argvs: `{...}` is reserved for the allowlist's placeholders.
ARGV_ECHO = ["{python}", "-c", "import json, os, sys; print(json.dumps(dict(argv=sys.argv[1:], cwd=os.getcwd())))"]
ENV_DUMP = ["{python}", "-c", "import json, os; print(json.dumps(dict(os.environ)))"]


def minishop_workspace(tmp_path: Path) -> Path:
    """PREPARE of a hosted demo run: the allowlisted app copied into a fresh workspace."""
    ws = prepare_workspace(RepoSpec(kind="demo", ref=MINISHOP.repo, commit=SHA), "r_workspacetest",
                           root=tmp_path / "workspaces", allowlist=Allowlist([MINISHOP]), hosted=True)
    return ws.path


def minishop(workspace: Path | None) -> ProcessSandbox:
    return ProcessSandbox(MINISHOP.repo, SHA, allowlist=Allowlist([MINISHOP]), workspace=workspace)


# --- where the app runs from ---


@pytest.fixture
def probe(tmp_path: Path) -> tuple[Allowlist, Path, Path]:
    app_dir, ws = tmp_path / "app", tmp_path / "ws"
    for folder in (app_dir, ws):
        folder.mkdir()
        (folder / "probe.py").write_text(PROBE_APP)
    entry = AllowlistEntry(repo="rook-fixtures/probe", commit=SHA, app_dir=app_dir, start=["{python}", "probe.py"],
                           commands={"test": ARGV_ECHO, "env": ENV_DUMP})
    return Allowlist([entry]), app_dir, ws


@pytest.mark.parametrize("from_workspace", [False, True])
def test_the_app_runs_from_the_app_dir_unless_given_the_workspace(
    probe: tuple[Allowlist, Path, Path], from_workspace: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    allowlist, app_dir, ws = probe
    monkeypatch.setenv("BOB_API_KEY", FAKE_KEY)
    expected = ws if from_workspace else app_dir
    with ProcessSandbox("rook-fixtures/probe", SHA, allowlist=allowlist,
                        workspace=ws if from_workspace else None) as box:
        assert box.run_dir == expected.resolve()
        info = httpx.get(box.start(), timeout=5).json()
        echoed = json.loads(box.exec(ARGV_ECHO).stdout)
        env = json.loads(box.exec(ENV_DUMP).stdout)
    assert info["cwd"] == echoed["cwd"] == str(expected.resolve())
    for child_env in (info["env"], env):  # env scrubbing is unchanged: nothing of Rook's own env gets through
        assert "BOB_API_KEY" not in child_env and FAKE_KEY not in json.dumps(child_env)
    assert env["HTTP_PROXY"] == env["https_proxy"] == "http://127.0.0.1:9"  # commands: no way out via a proxy
    assert env["UV_OFFLINE"] == "1" and env["NO_PROXY"] == "127.0.0.1,localhost"
    assert "HTTP_PROXY" not in info["env"]  # the app's own env is exactly as before


def test_the_workspace_must_be_an_existing_absolute_folder(probe: tuple[Allowlist, Path, Path]) -> None:
    allowlist, _, ws = probe
    link = ws.parent / "link"
    link.symlink_to(ws)
    for bad in (ws / "missing", Path("relative"), link, ws / "probe.py"):
        with pytest.raises(ValueError, match="workspace"):
            ProcessSandbox("rook-fixtures/probe", SHA, allowlist=allowlist, workspace=bad)


# --- the one extra argument: a test file inside the workspace ---


def test_only_the_test_command_from_a_workspace_takes_a_test_file(probe: tuple[Allowlist, Path, Path]) -> None:
    allowlist, app_dir, ws = probe
    (ws / "tests").mkdir()
    (ws / "tests" / "test_x.py").write_text("")
    (ws / "folder").mkdir()
    (app_dir / "outside.py").write_text("")
    (ws / "link.py").symlink_to(app_dir / "outside.py")
    (ws / "inner.py").symlink_to(ws / "tests" / "test_x.py")  # a symlink even inside the workspace is refused
    (ws / "dirlink").symlink_to(ws / "tests")
    box = ProcessSandbox("rook-fixtures/probe", SHA, allowlist=allowlist, workspace=ws)
    ok = box.exec([*ARGV_ECHO, "tests/test_x.py"])
    assert ok.ok and json.loads(ok.stdout)["argv"] == ["tests/test_x.py"]
    refused = [
        [*ARGV_ECHO, bad]
        for bad in ("../app/outside.py", str(ws / "tests" / "test_x.py"), "-k", "--help", "./tests/test_x.py",
                    "tests/../tests/test_x.py", "tests//test_x.py", "tests\\test_x.py", "missing.py", "folder",
                    "link.py", "inner.py", "dirlink/test_x.py", "tests/test_x.py\x00")
    ]
    refused += [[*ARGV_ECHO, "tests/test_x.py", "tests/test_x.py"],  # one extra argument only
                [*ENV_DUMP, "tests/test_x.py"]]  # and only on the `test` command
    for argv in refused:
        with pytest.raises(SandboxError, match="not allowlisted"):
            box.exec(argv)
    pristine = ProcessSandbox("rook-fixtures/probe", SHA, allowlist=allowlist)  # live mode: exact commands only
    (app_dir / "tests").mkdir()
    (app_dir / "tests" / "test_x.py").write_text("")
    with pytest.raises(SandboxError, match="not allowlisted"):
        pristine.exec([*ARGV_ECHO, "tests/test_x.py"])


def test_a_command_never_runs_longer_than_the_entry_allows(tmp_path: Path) -> None:
    entry = AllowlistEntry(repo="rook-fixtures/slow", commit=SHA, app_dir=tmp_path, start=["{python}", "x.py"],
                           commands={"test": ["{python}", "-c", "import time; time.sleep(60)"]}, command_timeout=1)
    box = ProcessSandbox("rook-fixtures/slow", SHA, allowlist=Allowlist([entry]), workspace=tmp_path)
    started = time.monotonic()
    result = box.exec(entry.commands["test"], timeout=600)
    assert result.exit_code == -1 and "timeout after 1s" in result.stderr
    assert time.monotonic() - started < 15


# --- minishop: the taped Surgeon patch is executed, and the engine verifies it ---


def _second_refund_status(base_url: str) -> int:
    """buy 1 x price 100, refund 60 twice: the buggy app accepts the second refund (200)."""
    with httpx.Client(base_url=base_url, timeout=10) as http:
        admin = http.post("/auth/login", json={"email": "admin@demo.local", "password": "admin-pass"}).json()
        admin_h = {"Authorization": f"Bearer {admin['token']}"}
        http.post("/auth/signup", json={"email": "c@x.io", "password": "pw-c-123"})
        user = http.post("/auth/login", json={"email": "c@x.io", "password": "pw-c-123"}).json()
        user_h = {"Authorization": f"Bearer {user['token']}"}
        product = http.post("/products", json={"name": "p", "price": 100, "stock": 5}, headers=admin_h).json()
        order = http.post("/orders", json={"product_id": product["id"], "quantity": 1}, headers=user_h).json()
        http.post(f"/orders/{order['id']}/refunds", json={"amount": 60}, headers=user_h)
        return http.post(f"/orders/{order['id']}/refunds", json={"amount": 60}, headers=user_h).status_code


def test_the_patched_workspace_code_is_served_only_with_the_capability(tmp_path: Path) -> None:
    ws = minishop_workspace(tmp_path)
    edit_tape.apply(ws, edit_tape.load(FIX_TAPE))
    assert (ws / "app.py").read_text() != (MINISHOP_DIR / "app.py").read_text()
    with minishop(ws) as patched:
        assert _second_refund_status(patched.start()) == 400
    with minishop(None) as pristine:  # live mode on the server: the original app, whatever the workspace holds
        assert _second_refund_status(pristine.start()) == 200


async def _verify(box: ProcessSandbox, harness: SandboxHarness) -> tuple[bool, list[bool]]:
    cx = refund_cx()
    model = rule_only_model(MODEL, cx)
    await harness.reload()  # as FixPipeline.verify: the app restarts on the patched code
    async with Executor(model, harness.base_url, env=ENV) as ex:
        verifier = Verifier(model, ex, harness.runner.bus, harness.runner.run_id, seed=5, budget_sequences=300,
                            budget_seconds=60, concurrency=4)
        result = await verifier.verify(cx, regression_test=lambda: harness.run_native(NATIVE_TEST),
                                       project_tests=harness.run_project)  # type: ignore[arg-type]
    return result.verified, [c.passed for c in result.checks]


async def test_replay_mode_runs_the_taped_native_test_and_verifies_the_taped_fix(tmp_path: Path) -> None:
    ws = minishop_workspace(tmp_path)
    edit_tape.apply(ws, edit_tape.load(TEST_TAPE))  # FIX writes the native test first
    bus = EventBus()
    with minishop(ws) as box:
        base_url = box.start()
        harness = SandboxHarness(box, TestRunner(bus, "r_test"), base_url=base_url, test_command=MINISHOP.commands["test"],
                                 env=ENV)
        buggy = await harness.run_native(NATIVE_TEST)
        assert fails_as_expected(buggy)[0], buggy  # the taped test fails on the buggy app (exit 1, no errors)
        assert "1 failed" in buggy.summary
        edit_tape.apply(ws, edit_tape.load(FIX_TAPE))  # then the Surgeon's approved fix
        verified, checks = await _verify(box, harness)
    assert verified and checks == [True, True, True, True]


async def test_live_mode_cannot_verify_the_same_patch(tmp_path: Path) -> None:
    ws = minishop_workspace(tmp_path)
    edit_tape.apply(ws, edit_tape.load(TEST_TAPE))
    edit_tape.apply(ws, edit_tape.load(FIX_TAPE))
    with minishop(None) as box:
        harness = SandboxHarness(box, TestRunner(EventBus(), "r_test"), base_url=box.start(),
                                 test_command=MINISHOP.commands["test"], env=ENV)
        native = await harness.run_native(NATIVE_TEST)  # refused: not a file of the app dir's exact commands
        assert native.exit_code == -1 and "not allowlisted" in native.output + native.summary
        verified, checks = await _verify(box, harness)
    assert not verified and checks[0] is False  # the replay still breaks the rule: the pristine app has the bug


def test_the_workspace_test_command_sees_only_the_scrubbed_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = minishop_workspace(tmp_path)
    (ws / "test_env.py").write_text(
        "import os\n\n\ndef test_env():\n"
        "    assert 'BOB_API_KEY' not in os.environ and 'GITHUB_APP_PRIVATE_KEY' not in os.environ\n"
        f"    assert os.getcwd() == {str(ws.resolve())!r}\n")
    monkeypatch.setenv("BOB_API_KEY", FAKE_KEY)
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", FAKE_KEY)
    result = minishop(ws).exec([*MINISHOP.commands["test"], "test_env.py"])
    assert result.ok, result.stdout + result.stderr
    assert FAKE_KEY not in result.stdout + result.stderr
    assert os.environ["BOB_API_KEY"] == FAKE_KEY  # the server's own env is untouched
