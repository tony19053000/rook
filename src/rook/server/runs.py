"""The server's live runs: one Session per run on a shared EventBus + Store, at most N running at once.

A run waits `queued` for a slot (NFR-6), then runs as an asyncio task. Cancelling a queued run lets its
Session finish at once as `cancelled`, without a slot. Whatever happens, the run's stream ends with a
`run.finished` event, so an SSE client never waits forever.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rook.agents.bob import BobClient
from rook.agents.caller import AgentCaller
from rook.agents.understand import Launcher, docker_launcher
from rook.core.events import EventBus, RunFinished, now_ts
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec, Workspace, new_run_id
from rook.github.pr import GitHubShipper
from rook.sandbox.allowlist import Allowlist
from rook.sandbox.docker import Limits
from rook.server.config import ServerSettings
from rook.store.repo import CounterexampleRecord, RunRecord, Store

log = logging.getLogger(__name__)


class RunSession(Protocol):
    """What the server needs from `core.session.Session` (tests pass a fake)."""

    run_id: str

    async def run(self) -> Any: ...

    def answer(self, question_id: str, answer: Any) -> bool: ...

    def chat(self, text: str) -> bool: ...

    def cancel(self) -> None: ...


@dataclass(frozen=True)
class GitHubAccess:
    """A user GitHub run's credentials: the clone token (checked out by the route) and a source of fresh
    tokens for SHIP. Both come from the user's own installation; neither is ever published or logged."""

    clone_token: str = field(repr=False)
    token_source: Callable[[], Awaitable[str]] = field(repr=False)


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    repo: RepoSpec
    request: str
    options: SessionOptions
    user_id: str
    bus: EventBus
    store: Store
    github: GitHubAccess | None = None


SessionFactory = Callable[[RunSpec], RunSession]
ReplayFactory = Callable[[RunSpec, CounterexampleRecord], RunSession]


def default_session_factory(settings: ServerSettings, allowlist: Allowlist) -> SessionFactory:
    """Sessions for the server. Only in replay mode (server config, never a request) do demo apps run from
    the run's workspace copy, where every edit comes from a committed, reviewed edit tape (03 §3).

    A signed-in user's GitHub repo (ROOK-041) always uses live Bob, runs in a DockerSandbox and ships with a
    push + PR (`GitHubShipper`, never the default branch), like `rook run owner/name` on the CLI."""
    run_workspace = settings.bob_mode == "replay"
    limits = Limits(memory=settings.sandbox_memory, cpus=settings.sandbox_cpus)

    def client(bus: EventBus, run_id: str, workspace: Path) -> AgentCaller:
        return BobClient(bus, run_id, mode=settings.bob_mode)

    def live_client(bus: EventBus, run_id: str, workspace: Path) -> AgentCaller:
        return BobClient(bus, run_id, mode="live")

    def launcher(workspace: Workspace, run_id: str) -> Launcher:
        return docker_launcher(workspace.path, run_id, access_network=settings.sandbox_network, limits=limits)

    def make(spec: RunSpec) -> RunSession:
        if spec.repo.kind == "github":
            if spec.github is None:
                raise ValueError("a GitHub run needs its installation token")
            shipper = GitHubShipper(spec.repo.ref, spec.github.token_source, api_url=settings.github_api_url,
                                    github_url=settings.github_web_url)
            return Session(spec.repo, spec.request, spec.options, bus=spec.bus, store=spec.store,
                           run_id=spec.run_id, user_id=spec.user_id, workspaces_root=settings.workspaces_root,
                           client_factory=live_client, launcher_factory=launcher, shipper=shipper,
                           token=spec.github.clone_token, github_url=settings.github_web_url)
        demo = settings.demo(spec.repo.ref) if spec.repo.kind == "demo" else None
        return Session(spec.repo, spec.request, spec.options, bus=spec.bus, store=spec.store, run_id=spec.run_id,
                       user_id=spec.user_id, workspaces_root=settings.workspaces_root, client_factory=client,
                       allowlist=allowlist, run_workspace=run_workspace,
                       featured_rule=demo.featured_rule if demo is not None else None)

    return make


class QueueFull(RuntimeError):
    pass


@dataclass
class LiveRun:
    session: RunSession
    owner: str
    repo: RepoSpec
    request: str
    created_at: str
    started: bool = False
    task: asyncio.Task[None] | None = None
    cancelled: asyncio.Event = field(default_factory=asyncio.Event)


class RunManager:
    def __init__(self, store: Store, bus: EventBus, factory: SessionFactory, *, max_concurrent: int,
                 max_queued: int) -> None:
        self.store = store
        self.bus = bus
        self.factory = factory
        self.max_queued = max_queued
        self._slots = asyncio.Semaphore(max_concurrent)
        self._live: dict[str, LiveRun] = {}

    def live(self, run_id: str) -> LiveRun | None:
        return self._live.get(run_id)

    def live_ids(self) -> frozenset[str]:
        return frozenset(self._live)

    def live_of(self, owner: str) -> list[tuple[str, LiveRun]]:
        return [(run_id, r) for run_id, r in self._live.items() if r.owner == owner]

    def owner_of(self, run_id: str) -> str | None:
        live = self._live.get(run_id)
        if live is not None:
            return live.owner
        record = self.store.get_run(run_id)
        return record.user_id if record is not None else None

    def queued(self) -> int:
        return sum(1 for r in self._live.values() if not r.started)

    def is_full(self) -> bool:
        """No free slot and the waiting queue is at its limit."""
        return self._slots.locked() and self.queued() >= self.max_queued

    def live_github(self) -> int:
        """User GitHub runs that are running or queued."""
        return sum(1 for r in self._live.values() if r.repo.kind == "github")

    def start(self, repo: RepoSpec, request: str, options: SessionOptions, owner: str,
              factory: SessionFactory | None = None, run_id: str | None = None,
              github: GitHubAccess | None = None) -> str:
        """Create the run's Session and schedule it. QueueFull when too many runs are already waiting."""
        if self.is_full():
            raise QueueFull("The server is busy; try again in a few minutes")
        run_id = run_id or new_run_id()
        spec = RunSpec(run_id, repo, request, options, owner, self.bus, self.store, github)
        session = (factory or self.factory)(spec)
        live = LiveRun(session, owner, repo, request, now_ts())
        self._live[run_id] = live
        live.task = asyncio.get_running_loop().create_task(self._drive(run_id, live), name=f"run {run_id}")
        return run_id

    def cancel(self, run_id: str) -> bool:
        live = self._live.get(run_id)
        if live is None:
            return False
        live.cancelled.set()
        live.session.cancel()
        return True

    async def _drive(self, run_id: str, live: LiveRun) -> None:
        slot = await self._wait_for_slot(live)
        try:
            live.started = True
            await live.session.run()
        except Exception:  # a broken session must still end its stream
            log.exception("run %s crashed", run_id)
        finally:
            if slot:
                self._slots.release()
            await self._ensure_finished(run_id, live)
            self._live.pop(run_id, None)

    async def _wait_for_slot(self, live: LiveRun) -> bool:
        """True with a slot held; False when the run was cancelled while it waited."""
        acquire = asyncio.ensure_future(self._slots.acquire())
        cancelled = asyncio.ensure_future(live.cancelled.wait())
        try:
            await asyncio.wait({acquire, cancelled}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            cancelled.cancel()
            if not acquire.done():
                acquire.cancel()
        try:
            await acquire
        except asyncio.CancelledError:
            return False
        if live.cancelled.is_set():  # the slot came as the run was cancelled: give it back
            self._slots.release()
            return False
        return True

    async def _ensure_finished(self, run_id: str, live: LiveRun) -> None:
        if self.bus.is_closed(run_id):
            return
        summary = "The run stopped unexpectedly."
        try:
            await self.bus.publish(run_id, "run.finished", RunFinished(status="failed", summary=summary))
        finally:
            await self.bus.close(run_id)
        if self.store.get_run(run_id) is None:
            self.store.insert_run(RunRecord(id=run_id, user_id=live.owner, repo_kind=live.repo.kind,
                                            repo_ref=live.repo.ref, status="failed", created_at=live.created_at,
                                            finished_at=now_ts()))
        else:
            self.store.update_run(run_id, status="failed", finished_at=now_ts())

    async def shutdown(self) -> None:
        """Cancel every live run and wait for it to clean up (sandboxes, Bob processes)."""
        runs = list(self._live.values())
        for live in runs:
            live.cancelled.set()
            live.session.cancel()
        tasks = [r.task for r in runs if r.task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
