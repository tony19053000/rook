"""Helpers for the ROOK-023 Session tests: minishop served in-process from the run's workspace copy,
a scripted fake Bob that uses the session's bus, and a scripted "user" that answers questions."""

import asyncio
import importlib.util
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
from pydantic import BaseModel

from rook.agents.bob import AgentResult
from rook.agents.schemas import SandboxPlan
from rook.agents.understand import Launcher, StartedApp
from rook.core.events import CostUpdate, Event, EventBus, RepoSummary
from rook.core.session import Session
from rook.core.workspace import Workspace
from rook.engine.inprocess import InProcessTransport
from rook.sandbox.base import ExecResult, Sandbox

FIXTURES = Path(__file__).parents[1] / "fixtures"
MINISHOP_DIR = FIXTURES / "minishop"
BASE = "http://minishop.test"
PYTEST = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "asyncio_mode=auto"]


def minishop_source(tmp_path: Path) -> Path:
    """A user's minishop folder (without the hand-written rook.yaml), as the pipeline tests used it."""
    src = tmp_path / "minishop"
    shutil.copytree(MINISHOP_DIR, src, ignore=shutil.ignore_patterns("__pycache__", "rook.yaml", ".pytest_cache"))
    return src


def tree(root: Path) -> dict[str, bytes]:
    """Every file under `root` (including .git), for "untouched" checks."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class SwappableTransport(httpx.AsyncBaseTransport):
    """An in-process transport whose app can be replaced (a restart loads the patched code)."""

    def __init__(self, app: Any) -> None:
        self.inner = InProcessTransport(app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await self.inner.handle_async_request(request)


class LocalApp(Sandbox):
    """minishop from the workspace's own app.py, in-process. `restart` reloads the (patched) code;
    `exec` runs commands in the workspace with a minimal env (never the host's)."""

    def __init__(self, ws: Path, env: Mapping[str, str], fixed: bool | None = None) -> None:
        self.ws, self.env, self.fixed = ws, dict(env), fixed
        self.stopped = 0
        self.restarts = 0
        self.transport = SwappableTransport(self._load())

    def _load(self) -> Any:
        spec = importlib.util.spec_from_file_location(f"ws_app_{uuid.uuid4().hex}", self.ws / "app.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, self.env):
            spec.loader.exec_module(module)
            return module.create_app(self.fixed)

    def start(self, plan: Any = None) -> str:
        return BASE

    def stop(self) -> None:
        self.stopped += 1

    def restart(self) -> str:
        self.restarts += 1
        self.transport.inner = InProcessTransport(self._load())
        return BASE

    def exec(self, cmd: Sequence[str], timeout: float = 600.0) -> ExecResult:
        argv = [*PYTEST, *cmd[1:]] if cmd[0] == "pytest" else list(cmd)
        env = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": str(self.ws.parent),
               "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.run(argv, cwd=self.ws, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, check=False)
        return ExecResult(proc.returncode, proc.stdout, proc.stderr)

    def logs(self, tail: int = 200) -> str:
        return ""


class LocalLauncher:
    """A LauncherFactory: every launch serves the workspace's minishop in-process."""

    def __init__(self, fixed: bool | None = None) -> None:
        self.fixed = fixed
        self.apps: list[LocalApp] = []

    def __call__(self, workspace: Workspace, run_id: str) -> Launcher:
        def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
            app = LocalApp(workspace.path, {**plan.env_defaults, **values}, self.fixed)
            self.apps.append(app)
            return StartedApp(sandbox=app, base_url=BASE, transport=app.transport)

        return launch


Reply = dict[str, Any] | Exception | Callable[[Path], dict[str, Any]]


class ScriptedClient:
    """A fake Bob on the session's bus: scripted replies per agent id (a callable reply may edit files).
    `cost` coins are charged per call and published as `cost.update`, like BobClient."""

    def __init__(self, bus: EventBus, run_id: str, replies: dict[str, list[Reply]], *, cost: float = 0.0,
                 delay: float = 0.0) -> None:
        self.bus, self.run_id = bus, run_id
        self.replies = {k: list(v) for k, v in replies.items()}
        self.cost, self.delay = cost, delay
        self.total = 0.0
        self.calls: list[tuple[str, str]] = []

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        self.calls.append((agent_id, prompt))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.cost:
            self.total += self.cost
            await self.bus.publish(self.run_id, "cost.update", CostUpdate(coins_total=round(self.total, 6)))
        queue = self.replies.get(agent_id) or []
        if not queue:
            raise LookupError(f"no scripted reply for {agent_id}")
        reply = queue.pop(0) if len(queue) > 1 else queue[0]  # the last reply repeats
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(Path(workspace))
        return AgentResult(output=output_model.model_validate(reply), text="", cost=self.cost, recorded=False,
                           call_id=f"c_{len(self.calls)}")

    def agents(self) -> list[str]:
        return [a for a, _ in self.calls]


Policy = Callable[[dict[str, Any]], Any]


def answer_questions(session: Session, policy: Policy) -> asyncio.Task[list[dict[str, Any]]]:
    """A scripted user: answers each `question.asked` (except setup values) with `policy(data)`."""

    async def follow() -> list[dict[str, Any]]:
        asked = []
        async for event in session.events():
            if event.type == "question.asked" and event.data["kind"] != "setup_value":
                asked.append(event.data)
                if not session.answer(event.data["question_id"], policy(event.data)):
                    session.cancel()  # an unexpected question: end the test run instead of hanging
        return asked

    return asyncio.create_task(follow())


def say_yes(data: dict[str, Any]) -> Any:
    return "all" if data["kind"] == "approve_rules" else "yes"


def history(session: Session) -> list[Event]:
    return list(session.bus._channel(session.run_id).history)


def phases(session: Session) -> list[str]:
    return [e.data["phase"] for e in history(session) if e.type == "run.phase"]
