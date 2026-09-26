"""The Test Runner (02_ARCHITECTURE.md section 7.6): runs a test command and records its exit code.

- `run_in_sandbox`: the project's own test command (`RepoSummary.test_command`), run next to the app
  with `Sandbox.exec` (an argv list, never a shell; ProcessSandbox only runs allowlisted commands).
- `run_fallback`: a Rook-generated HTTP-level regression test (`export/tests.py`), which is checked
  against its template and run in an isolated temp dir against the sandbox's base URL.

Blocking work runs in a thread so the event loop keeps going. The pass/fail of a run is its exit code.
"""

import asyncio
import re
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rook.core.events import EngineFinished, EngineStarted, EventBus
from rook.export.tests import DEFAULT_TIMEOUT, run_generated_test
from rook.sandbox.base import ExecResult, Sandbox

OUTPUT_TAIL_LINES = 40
_PYTEST_SUMMARY = re.compile(r"^=+ (.+?) =+$")
_COUNTS = re.compile(r"\b\d+ (passed|failed|errors?|skipped|xfailed|xpassed)\b")


@dataclass(frozen=True)
class TestRun:
    __test__ = False  # not a pytest test class

    label: str
    exit_code: int
    summary: str
    output: str  # the last lines of stdout + stderr

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def parse_command(command: str | Sequence[str]) -> list[str]:
    """A test command as an argv list (a string is split like a shell would, but never run by one)."""
    argv = shlex.split(command) if isinstance(command, str) else list(command)
    if not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError(f"empty or invalid test command: {command!r}")
    return argv


def summarize(result: ExecResult) -> str:
    """`exit N: <pytest-style summary or last output line>`."""
    lines = [line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
    found = ""
    for line in reversed(lines):
        match = _PYTEST_SUMMARY.match(line)
        if match or _COUNTS.search(line):
            found = match.group(1) if match else line
            break
    if not found and lines:
        found = lines[-1]
    if len(found) > 200:
        found = found[:197] + "..."
    return f"exit {result.exit_code}" + (f": {found}" if found else "")


def _tail(result: ExecResult) -> str:
    text = (result.stdout + ("\n" + result.stderr if result.stderr else "")).rstrip()
    return "\n".join(text.splitlines()[-OUTPUT_TAIL_LINES:])


class TestRunner:
    __test__ = False  # not a pytest test class

    def __init__(self, bus: EventBus | None, run_id: str) -> None:
        self.bus = bus
        self.run_id = run_id

    async def run_in_sandbox(
        self,
        sandbox: Sandbox,
        command: str | Sequence[str],
        *,
        label: str = "project tests",
        timeout: float = 600.0,
    ) -> TestRun:
        argv = parse_command(command)
        return await self._run(label, lambda: sandbox.exec(argv, timeout=timeout))

    async def run_fallback(
        self,
        test_file: Path,
        base_url: str,
        env: Mapping[str, str] | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> TestRun:
        label = f"regression test {test_file.name}"
        return await self._run(label, lambda: run_generated_test(test_file, base_url, env, timeout=timeout))

    async def _run(self, label: str, call: Callable[[], ExecResult]) -> TestRun:
        await self._publish("engine.started", EngineStarted(worker="testrunner", label=label))
        try:
            result = await asyncio.to_thread(call)
        except asyncio.CancelledError:
            await self._publish(
                "engine.finished", EngineFinished(worker="testrunner", ok=False, summary="cancelled")
            )
            raise
        except Exception as exc:  # noqa: BLE001 - a command that cannot run is a failed test run
            result = ExecResult(-1, "", f"could not run: {type(exc).__name__}: {exc}")
        run = TestRun(label, result.exit_code, summarize(result), _tail(result))
        await self._publish(
            "engine.finished",
            EngineFinished(worker="testrunner", ok=run.passed, summary=f"{label}: {run.summary}"),
        )
        return run

    async def _publish(self, event_type: str, data: Any) -> None:
        if self.bus is not None:
            await self.bus.publish(self.run_id, event_type, data)
