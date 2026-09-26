"""BobClient + recorder tests. A fake `bob` script replays canned NDJSON, so no Bobcoins are spent."""

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from rook.agents.bob import (
    CHILD_ENV_ALLOWLIST,
    NODE24_BIN,
    AgentOutputError,
    BobClient,
    BobError,
    BobTimeout,
    build_argv,
    extract_json,
    resolve_bin,
    tool_detail,
)
from rook.agents.recorder import Recorder, RecordingMissing, recording_key, replay_lines
from rook.core.events import REDACTED, Event, EventBus, clear_secrets

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bob"
RUN = "r_test"
# Assembled at runtime so no secret-looking literal sits in the repo.
FAKE_KEY = "fake" + "-bob-key-" + "Q7x2Lm9P"


class Out(BaseModel):
    ok: bool
    note: str = ""


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for var in ("ROOK_BOB_MODE", "ROOK_BOB_RECORD", "ROOK_BOB_BIN"):
        monkeypatch.delenv(var, raising=False)
    clear_secrets()
    yield
    clear_secrets()


@pytest.fixture
def fake_bob(tmp_path: Path) -> Path:
    exe = tmp_path / "bin" / "bob"
    exe.parent.mkdir()
    exe.write_text(
        f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FIXTURES / 'fake_bob.py')!r}, run_name='__main__')\n"
    )
    exe.chmod(0o755)
    return exe


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "app").mkdir(parents=True)
    return ws


def make_client(
    tmp_path: Path, fake_bob: Path, scenario: str, *, mode: str = "live", timeout: float = 20, **kw: Any
) -> tuple[BobClient, EventBus]:
    bus = EventBus()
    env = {
        "BOB_API_KEY": FAKE_KEY,
        "FAKE_BOB_SCENARIO": scenario,
        "FAKE_BOB_STATE": str(tmp_path / "count"),
        "FAKE_BOB_ARGV_LOG": str(tmp_path / "argv.jsonl"),
        "FAKE_BOB_CHILD_PID": str(tmp_path / "child.pid"),
    }
    client = BobClient(bus, RUN, bin=fake_bob, env=env, mode=mode, recordings_dir=tmp_path / "rec",
                       timeout=timeout, replay_speed=1000, replay_max_gap=0.01, **kw)  # type: ignore[arg-type]
    return client, bus


async def events(bus: EventBus) -> list[Event]:
    await bus.close(RUN)
    return [e async for e in bus.subscribe(RUN)]


def argv_log(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (tmp_path / "argv.jsonl").read_text().splitlines()]


# --- parsing and event sequence ------------------------------------------------------------------


async def test_parses_stream_and_emits_event_sequence(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "ok")
    result = await client.call("scout", "rook-scout", "Summarize the repo.", workspace, Out)

    assert result.output == Out(ok=True, note="refunds")
    assert "Found the refund handler" in result.text
    assert result.cost == pytest.approx(0.023638)
    assert result.recorded is False
    assert client.total_cost == pytest.approx(0.023638)

    evs = await events(bus)
    assert [e.type for e in evs] == [
        "agent.started", "agent.progress", "agent.progress", "agent.progress", "agent.progress",
        "agent.progress", "cost.update", "agent.finished",
    ]
    assert all(e.data["call_id"] == result.call_id for e in evs if e.type.startswith("agent."))
    assert evs[0].data == {"agent": "scout", "call_id": result.call_id, "detail": "starting"}
    assert [e.data["detail"] for e in evs if e.type == "agent.progress"] == [
        "reading app/refunds.py", "listing app", "searching for def refund in .", "editing app/orders.py",
        "using codebase_search",
    ]
    assert evs[-2].data == {"coins_total": pytest.approx(0.023638)}
    fin = evs[-1].data
    assert fin["ok"] is True and fin["recorded"] is False
    assert fin["cost"] == pytest.approx(0.023638)
    assert fin["summary"] == "Found the refund handler in app/refunds.py."


async def test_argv_env_and_max_cost(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, _ = make_client(tmp_path, fake_bob, "ok")
    await client.call("scout", "rook-scout", "hello", workspace, Out, max_turns=5, max_cost=0.5)
    (entry,) = argv_log(tmp_path)
    assert entry["argv"] == ["run", "--mode", "rook-scout", "--format", "stream-json", "--workspace",
                             str(workspace.resolve()), "--max-turns", "5", "--disable-mcp", "--trust",
                             "--accept-license", "--max-cost", "0.5", "hello"]
    assert entry["has_key"] is True
    assert entry["cwd"] == str(workspace.resolve())  # --trust trusts the cwd, so it must be the workspace
    assert str(NODE24_BIN) in entry["path"].split(os.pathsep)


async def test_child_env_is_allowlisted(
    tmp_path: Path, fake_bob: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "fake-supabase-secret")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fake-app-key")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "fake-webhook")
    monkeypatch.setenv("HOME", str(tmp_path))
    client, _ = make_client(tmp_path, fake_bob, "ok")
    await client.call("scout", "rook-scout", "p", workspace, Out)
    (entry,) = argv_log(tmp_path)
    keys = set(entry["env_keys"])
    assert not keys & {"SUPABASE_JWT_SECRET", "GITHUB_APP_PRIVATE_KEY", "GITHUB_WEBHOOK_SECRET"}
    assert {"PATH", "HOME", "BOB_API_KEY"} <= keys
    assert keys <= set(CHILD_ENV_ALLOWLIST) | set(client.env), keys - set(CHILD_ENV_ALLOWLIST)


def test_build_argv_prompt_last_without_max_cost() -> None:
    argv = build_argv("bob", "rook-x", "p", "/ws", 8, None)
    assert argv[-1] == "p" and "--max-cost" not in argv and "--disable-mcp" in argv


def test_resolve_bin_order(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_bin("/x/bob") == "/x/bob"
    monkeypatch.setenv("ROOK_BOB_BIN", "/env/bob")
    assert resolve_bin() == "/env/bob"


def test_tool_detail_paths_outside_workspace_stay_absolute() -> None:
    assert tool_detail("read_file", {"path": "/elsewhere/a.py"}, "/ws") == "reading /elsewhere/a.py"
    assert tool_detail("write_to_file", {"path": "/ws/src/a.py"}, "/ws") == "editing src/a.py"
    assert tool_detail("read_file", {"path": "rel/a.py"}, "/ws") == "reading rel/a.py"


# --- JSON extraction -----------------------------------------------------------------------------


def test_extract_json_fenced_bare_and_multiple() -> None:
    assert extract_json('text\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```\nlater\n```json\n{"a": 2}\n```\n') == {"a": 2}
    assert extract_json('```\n{"a": 3}\n```') == {"a": 3}
    assert extract_json('see {bad} and {"a": {"b": 4}} end') == {"a": {"b": 4}}
    assert extract_json('{"a": 1} then {"a": 5}') == {"a": 5}
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(ValueError):
        extract_json("```json\n{broken\n```")


async def test_multiple_blocks_uses_last(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, _ = make_client(tmp_path, fake_bob, "multi")
    result = await client.call("scout", "rook-scout", "p", workspace, Out)
    assert result.output == Out(ok=True, note="final")


async def test_bare_json_object(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, _ = make_client(tmp_path, fake_bob, "bare")
    result = await client.call("scout", "rook-scout", "p", workspace, Out)
    assert result.output == Out(ok=True, note="bare")


# --- retries -------------------------------------------------------------------------------------


async def test_retry_on_invalid_output_then_success(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "invalid,ok")
    result = await client.call("scout", "rook-scout", "Summarize the repo.", workspace, Out)
    assert result.output.ok is True
    assert result.cost == pytest.approx(0.033638)

    calls = argv_log(tmp_path)
    assert len(calls) == 2
    retry_prompt = calls[1]["argv"][-1]
    assert retry_prompt.startswith("Summarize the repo.")
    assert "ok\n  Field required" in retry_prompt  # the exact pydantic error is fed back

    evs = await events(bus)
    assert [e.type for e in evs].count("agent.started") == 1
    assert [e.type for e in evs].count("agent.finished") == 1
    assert [e.data["coins_total"] for e in evs if e.type == "cost.update"] == [
        pytest.approx(0.01), pytest.approx(0.033638)]
    assert any(e.data.get("detail", "").endswith("retrying") for e in evs)


async def test_agent_output_error_after_three_attempts(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "invalid")
    with pytest.raises(AgentOutputError):
        await client.call("scout", "rook-scout", "p", workspace, Out)
    assert len(argv_log(tmp_path)) == 3
    fin = (await events(bus))[-1]
    assert fin.type == "agent.finished" and fin.data["ok"] is False
    assert len(fin.data["summary"]) <= 120


async def test_non_success_status_raises_bob_error(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "error")
    with pytest.raises(BobError, match="'error'"):
        await client.call("scout", "rook-scout", "p", workspace, Out)
    assert len(argv_log(tmp_path)) == 1  # a bob failure is not retried
    assert client.total_cost == pytest.approx(0.005)
    assert (await events(bus))[-1].data["ok"] is False


# --- process handling ----------------------------------------------------------------------------


async def test_timeout_kills_process_group(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "sleep", timeout=1.5)
    started = time.monotonic()
    with pytest.raises(BobTimeout):
        await client.call("scout", "rook-scout", "p", workspace, Out)
    assert time.monotonic() - started < 10
    child_pid = int((tmp_path / "child.pid").read_text())
    for _ in range(50):  # the grandchild `sleep` must die with the group
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("child process survived the timeout")
    fin = (await events(bus))[-1]
    assert fin.type == "agent.finished" and fin.data["ok"] is False and "timed out" in fin.data["summary"]


async def test_stdin_is_devnull(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    # The fake reports status "stdin_not_devnull" unless stdin is a character device that reads ''.
    client, _ = make_client(tmp_path, fake_bob, "ok")
    assert (await client.call("scout", "rook-scout", "p", workspace, Out)).output.ok


def test_fake_bob_detects_open_stdin(fake_bob: Path, workspace: Path) -> None:
    proc = subprocess.run([str(fake_bob), "run", "--workspace", str(workspace)], input="", capture_output=True,
                          text=True, timeout=20, check=False)
    assert '"stdin_not_devnull"' in proc.stdout


# --- secrets -------------------------------------------------------------------------------------


async def test_key_never_in_argv_and_redacted_from_events(
    tmp_path: Path, fake_bob: Path, workspace: Path
) -> None:
    client, bus = make_client(tmp_path, fake_bob, "leak")
    result = await client.call("scout", "rook-scout", "p", workspace, Out)
    assert result.output.note == "leak"
    for entry in argv_log(tmp_path):
        assert all(FAKE_KEY not in arg for arg in entry["argv"])
    evs = await events(bus)
    dumped = json.dumps([e.model_dump() for e in evs])
    assert FAKE_KEY not in dumped
    assert f"reading {REDACTED}.txt" in dumped


async def test_recording_never_stores_key(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, _ = make_client(tmp_path, fake_bob, "leak", mode="record")
    await client.call("scout", "rook-scout", "p", workspace, Out)
    (rec,) = (tmp_path / "rec").glob("*.ndjson")
    assert FAKE_KEY not in rec.read_text()


# --- recorder ------------------------------------------------------------------------------------


def test_recording_key_is_stable_and_separated() -> None:
    assert recording_key("a", "b") == recording_key("a", "b")
    assert recording_key("ab", "c") != recording_key("a", "bc")
    assert len(recording_key("a", "b")) == 64


async def test_replay_lines_caps_gaps() -> None:
    entries = [(0.0, "a"), (30.0, "b"), (30.3, "c")]
    started = time.monotonic()
    assert [x async for x in replay_lines(entries, speed=3.0, max_gap=0.2)] == ["a", "b", "c"]
    assert 0.2 <= time.monotonic() - started < 1.0  # 30 s gap -> capped at 0.2, then 0.1 s


async def test_record_then_replay_round_trip(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    rec_client, rec_bus = make_client(tmp_path, fake_bob, "invalid,ok", mode="record")
    live = await rec_client.call("scout", "rook-scout", "Summarize the repo.", workspace, Out)
    assert len(list((tmp_path / "rec").glob("*.ndjson"))) == 2  # one per attempt (the retry prompt differs)

    rep_client, rep_bus = make_client(tmp_path, fake_bob, "error", mode="replay")
    replayed = await rep_client.call("scout", "rook-scout", "Summarize the repo.", workspace, Out)
    assert len(argv_log(tmp_path)) == 2  # replay never ran bob

    assert replayed.output == live.output and replayed.text == live.text
    assert replayed.recorded is True and replayed.cost == pytest.approx(live.cost)
    assert rep_client.total_cost == 0.0  # replays are free against the budget

    def shape(evs: list[Event]) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for e in evs:
            data = {k: v for k, v in e.data.items() if k not in ("call_id", "recorded", "coins_total")}
            out.append((e.type, data))
        return out

    live_evs, rep_evs = await events(rec_bus), await events(rep_bus)
    assert shape(rep_evs) == shape(live_evs)
    assert rep_evs[-1].data["recorded"] is True and live_evs[-1].data["recorded"] is False
    assert rep_evs[-1].data["cost"] == pytest.approx(0.033638)
    assert all(e.data["coins_total"] == 0 for e in rep_evs if e.type == "cost.update")


async def test_replay_missing_recording(tmp_path: Path, fake_bob: Path, workspace: Path) -> None:
    client, bus = make_client(tmp_path, fake_bob, "ok", mode="replay")
    with pytest.raises(RecordingMissing):
        await client.call("scout", "rook-scout", "never recorded", workspace, Out)
    assert (await events(bus))[-1].data["ok"] is False


async def test_live_records_only_with_env_flag(
    tmp_path: Path, fake_bob: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = make_client(tmp_path, fake_bob, "ok")
    await client.call("scout", "rook-scout", "p", workspace, Out)
    assert not (tmp_path / "rec").exists()

    monkeypatch.setenv("ROOK_BOB_RECORD", "1")
    client, _ = make_client(tmp_path, fake_bob, "ok")
    await client.call("scout", "rook-scout", "p", workspace, Out)
    assert Recorder(tmp_path / "rec").path(recording_key("rook-scout", "p")).is_file()


def test_mode_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROOK_BOB_MODE", "replay")
    assert BobClient(EventBus(), RUN, bin="bob", recordings_dir=tmp_path).mode == "replay"
    monkeypatch.setenv("ROOK_BOB_MODE", "nope")
    with pytest.raises(ValueError):
        BobClient(EventBus(), RUN, bin="bob")


# --- live smoke test (costs ~0.02 coins; excluded by default) --------------------------------------

SMOKE_MODES = {"customModes": [{
    "slug": "rook-smoke",
    "name": "Rook smoke test",
    "roleDefinition": "You are a test agent. You answer tersely.",
    "customInstructions": 'Reply with exactly one fenced json block containing {"ok": true} and nothing else.',
    "groups": ["read"],
}]}


@pytest.mark.bob
async def test_live_bob_smoke(tmp_path: Path) -> None:
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY not set (source ~/.bob-key.env)")
    ws = tmp_path / "ws"
    (ws / ".bob").mkdir(parents=True)
    (ws / ".bob" / "custom_modes.yaml").write_text(yaml.safe_dump(SMOKE_MODES))
    bus = EventBus()
    client = BobClient(bus, RUN, mode="live", recordings_dir=tmp_path / "rec", timeout=180)
    result = await client.call("smoke", "rook-smoke", 'Reply with ```json\n{"ok": true}\n```', ws, Out,
                               max_turns=2)
    assert result.output.ok is True
    assert result.cost > 0
    evs = await events(bus)
    assert evs[0].type == "agent.started" and evs[-1].type == "agent.finished"
    assert os.environ["BOB_API_KEY"] not in json.dumps([e.model_dump() for e in evs])
