"""ROOK-011: the Test Runner (runs a command in the sandbox, records the exit code and a summary)."""

from collections.abc import Sequence

import pytest

from rook.core.events import Event, EventBus
from rook.engine.testrunner import TestRunner, parse_command, summarize
from rook.sandbox.base import ExecResult, Sandbox, SandboxError


class FakeSandbox(Sandbox):
    """Records exec calls; returns canned results or raises."""

    def __init__(self, result: ExecResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[list[str], float]] = []

    def start(self, plan: object = None) -> str:
        return "http://127.0.0.1:1"

    def stop(self) -> None:
        pass

    def restart(self) -> str:
        return self.start()

    def exec(self, cmd: Sequence[str], timeout: float = 600.0) -> ExecResult:
        self.calls.append((list(cmd), timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def logs(self, tail: int = 200) -> str:
        return ""


async def events_of(bus: EventBus) -> list[Event]:
    await bus.close("r_test")
    return [e async for e in bus.subscribe("r_test")]


def test_parse_command_gives_an_argv_list_never_a_shell_string() -> None:
    assert parse_command("pytest -q 'tests/a b.py'") == ["pytest", "-q", "tests/a b.py"]
    assert parse_command("npm test; rm -rf /") == ["npm", "test;", "rm", "-rf", "/"]  # ';' is just text
    assert parse_command(["python", "-m", "pytest"]) == ["python", "-m", "pytest"]
    for bad in ["", "   ", [], ["pytest", ""]]:
        with pytest.raises(ValueError):
            parse_command(bad)


@pytest.mark.parametrize(
    ("result", "summary"),
    [
        (ExecResult(0, "..\n===== 2 passed in 0.10s =====\n", ""), "exit 0: 2 passed in 0.10s"),
        (ExecResult(1, "F.\n1 failed, 1 passed in 0.2s\n", ""), "exit 1: 1 failed, 1 passed in 0.2s"),
        (ExecResult(1, "", "Tests: 3 failed, 4 total\n"), "exit 1: Tests: 3 failed, 4 total"),
        (ExecResult(2, "", "boom\nlast words\n"), "exit 2: last words"),
        (ExecResult(0, "", ""), "exit 0"),
    ],
)
def test_summarize(result: ExecResult, summary: str) -> None:
    assert summarize(result) == summary


async def test_run_in_sandbox_records_exit_code_and_events() -> None:
    bus = EventBus()
    sandbox = FakeSandbox(ExecResult(1, "F\n=== 1 failed in 0.01s ===\n", ""))
    run = await TestRunner(bus, "r_test").run_in_sandbox(sandbox, "pytest -q", timeout=30)
    assert sandbox.calls == [(["pytest", "-q"], 30)]
    assert (run.exit_code, run.passed, run.summary) == (1, False, "exit 1: 1 failed in 0.01s")
    assert "1 failed" in run.output
    events = await events_of(bus)
    assert [(e.type, e.data["worker"]) for e in events] == [
        ("engine.started", "testrunner"),
        ("engine.finished", "testrunner"),
    ]
    assert events[1].data["ok"] is False and "1 failed" in events[1].data["summary"]


async def test_a_command_that_cannot_run_is_a_failed_run() -> None:
    sandbox = FakeSandbox(SandboxError("command not allowlisted for x: ['rm', '-rf', '/']"))
    run = await TestRunner(None, "r").run_in_sandbox(sandbox, ["rm", "-rf", "/"])
    assert not run.passed and run.exit_code == -1 and "not allowlisted" in run.summary


async def test_passing_run() -> None:
    run = await TestRunner(None, "r").run_in_sandbox(
        FakeSandbox(ExecResult(0, "3 passed in 1s", "")), "pytest"
    )
    assert run.passed and run.summary == "exit 0: 3 passed in 1s"
