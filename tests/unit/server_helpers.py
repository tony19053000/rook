"""Helpers for the ROOK-029 server tests: fake Sessions on the server's bus, an app factory, callers, and
a raw ASGI call for live SSE (httpx's ASGITransport waits for the whole body, so it can't read a live tail)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from rook.core.events import now_ts
from rook.server.app import create_app
from rook.server.auth import GUEST_COOKIE, AuthUser
from rook.server.config import DemoRepo, ServerSettings
from rook.server.deps import ServerState
from rook.server.runs import RunSession, RunSpec
from rook.store.repo import RunRecord

REPO_ROOT = Path(__file__).parents[2]
RECORDED_RUN = REPO_ROOT / "web" / "lib" / "fixtures" / "minishop-run.json"
DEMO = DemoRepo(ref="rook-demo/shop-app", commit="a" * 40, name="shop-app", language="TypeScript")
BASE = "https://testserver"
USERS = {"token-alice": AuthUser(id="u_alice", email="alice@example.com"),
         "token-bob": AuthUser(id="u_bob", email="bob@example.com")}
ALICE = {"Authorization": "Bearer token-alice"}
BOB = {"Authorization": "Bearer token-bob"}


class FakeVerifier:
    """Stands in for ROOK-030's Supabase JWT check."""

    def verify(self, token: str) -> AuthUser | None:
        return USERS.get(token)


class _Base:
    def __init__(self, spec: RunSpec) -> None:
        self.spec = spec
        self.run_id = spec.run_id
        self.cancel_calls = 0
        self.finished = False

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        await self.spec.bus.publish(self.run_id, event_type, data)

    async def start(self) -> None:
        s = self.spec
        s.store.insert_run(RunRecord(id=self.run_id, user_id=s.user_id, repo_kind=s.repo.kind, repo_ref=s.repo.ref,
                                     status="running", created_at=now_ts()))
        await self.publish("run.created", {"repo": {"kind": s.repo.kind, "ref": s.repo.ref, "name": s.repo.name},
                                           "request": s.request,
                                           "options": {"auto": s.options.auto, "budget": s.options.budget}})

    async def finish(self, status: str, summary: str) -> None:
        self.finished = True
        await self.publish("run.finished", {"status": status, "summary": summary})
        await self.spec.bus.close(self.run_id)
        self.spec.store.update_run(self.run_id, status=status, finished_at=now_ts())


class QuestionSession(_Base):
    """run.created, one `fix` question, then waits: an answer finishes it `done`, cancel `cancelled`."""

    def __init__(self, spec: RunSpec) -> None:
        super().__init__(spec)
        self.future: asyncio.Future[Any] | None = None
        self.asked = asyncio.Event()
        self.chats: list[str] = []

    async def run(self) -> None:
        await self.start()
        self.future = asyncio.get_running_loop().create_future()
        if self.cancel_calls:
            self.future.cancel()
        await self.publish("question.asked", {"question_id": "q_fix", "kind": "fix", "text": "Apply the fix?",
                                              "options": [{"id": "yes", "label": "Yes"},
                                                          {"id": "no", "label": "No"}], "payload": None})
        self.asked.set()
        try:
            answer = await self.future
        except asyncio.CancelledError:
            await self.finish("cancelled", "The run was cancelled.")
            return
        await self.publish("question.answered", {"question_id": "q_fix", "answer": answer, "by": "user"})
        await self.finish("done", "Answered")

    def answer(self, question_id: str, answer: Any) -> bool:
        future = self.future
        if question_id != "q_fix" or future is None or future.done() or not isinstance(answer, bool):
            return False
        future.set_result(answer)
        return True

    def chat(self, text: str) -> bool:
        if self.finished:
            return False
        self.chats.append(text)
        asyncio.get_running_loop().create_task(self.publish("chat.message", {"role": "user", "text": text}))
        return True

    def cancel(self) -> None:
        self.cancel_calls += 1
        if self.future is not None and not self.future.done():
            self.future.cancel()


class RecordedSession(_Base):
    """Replays the recorded minishop run (the web client's fixture) through the server's bus and store."""

    async def run(self) -> None:
        s = self.spec
        s.store.insert_run(RunRecord(id=self.run_id, user_id=s.user_id, repo_kind=s.repo.kind, repo_ref=s.repo.ref,
                                     status="running", created_at=now_ts()))
        events = json.loads(RECORDED_RUN.read_text(encoding="utf-8"))
        for event in events:
            if event["type"] == "counterexample.saved":
                data = event["data"]
                s.store.save_counterexample(f"{self.run_id}_{data['cx_id']}", self.run_id, data["rule_id"],
                                            {"cx_id": data["cx_id"], "rule": {"id": data["rule_id"],
                                                                              "text": data["rule_text"]},
                                             "steps": data["steps"], "reproduced": data["reproduced"]},
                                            "verified")
            if event["type"] == "run.finished":
                self.finished = True
                await self.publish("run.finished", event["data"])
                await s.bus.close(self.run_id)
                s.store.update_run(self.run_id, status=event["data"]["status"], finished_at=now_ts(), coins=0.0)
                return
            await self.publish(event["type"], event["data"])

    def answer(self, question_id: str, answer: Any) -> bool:
        return False

    def chat(self, text: str) -> bool:
        return False

    def cancel(self) -> None:
        self.cancel_calls += 1


class CrashingSession(_Base):
    async def run(self) -> None:
        await self.start()
        raise RuntimeError("boom")

    def answer(self, question_id: str, answer: Any) -> bool:
        return False

    def chat(self, text: str) -> bool:
        return False

    def cancel(self) -> None:
        self.cancel_calls += 1


class Factory:
    """A SessionFactory that builds `kind` sessions and remembers them."""

    def __init__(self, kind: type[_Base] = QuestionSession) -> None:
        self.kind = kind
        self.sessions: dict[str, Any] = {}

    def __call__(self, spec: RunSpec) -> RunSession:
        session = self.kind(spec)
        self.sessions[spec.run_id] = session
        return session  # type: ignore[return-value]


def make_app(tmp_path: Path, factory: Any = None, *, github: Any = None, replay_factory: Any = None,
             github_transport: Any = None, **settings: Any) -> FastAPI:
    values: dict[str, Any] = {"db_path": tmp_path / "server.db", "workspaces_root": tmp_path / "ws",
                              "demo_repos": [DEMO], "web_origins": ["https://rook.example.app"],
                              "guest_secret": "s" * 40, "bob_mode": "replay", **settings}
    return create_app(ServerSettings.model_validate(values), verifier=FakeVerifier(),
                      session_factory=factory or Factory(), github=github, replay_factory=replay_factory,
                      github_transport=github_transport)


def state_of(app: FastAPI) -> ServerState:
    state: ServerState = app.state.rook
    return state


@contextlib.asynccontextmanager
async def client_for(app: FastAPI, ip: str = "10.0.0.1") -> AsyncIterator[httpx.AsyncClient]:
    """An async client on the app, with the app's lifespan running."""
    async with app.router.lifespan_context(app), second_client(app, ip) as client:
        yield client


@contextlib.asynccontextmanager
async def second_client(app: FastAPI, ip: str) -> AsyncIterator[httpx.AsyncClient]:
    """Another client (from another IP) on an app whose lifespan is already running."""
    transport = httpx.ASGITransport(app=app, client=(ip, 5555))
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
        yield client


def guest_headers(app: FastAPI) -> tuple[str, dict[str, str]]:
    """A new guest id and the Cookie header that proves it."""
    guest_id, value = state_of(app).cookies.issue()
    return guest_id, {"Cookie": f"{GUEST_COOKIE}={value}"}


NEW_RUN = {"repo": {"kind": "demo", "ref": DEMO.ref}, "request": "find a refund bug", "options": {"auto": False}}


async def create_run(client: httpx.AsyncClient, headers: dict[str, str], body: dict[str, Any] | None = None) -> str:
    response = await client.post("/api/v1/runs", json=body or NEW_RUN, headers=headers)
    assert response.status_code == 200, response.text
    run_id: str = response.json()["run_id"]
    return run_id


async def wait_for(condition: Any, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


def parse_sse(text: str) -> list[dict[str, Any]]:
    """The envelopes of every `data:` line, checking each message's `id:` equals its seq."""
    out = []
    for block in text.split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        if not lines:
            continue
        fields = dict(line.split(": ", 1) for line in lines)
        envelope = json.loads(fields["data"])
        assert fields["id"] == str(envelope["seq"])
        out.append(envelope)
    return out


class RawStream:
    """GET an SSE route with a raw ASGI call and read the body as it is sent."""

    def __init__(self, app: FastAPI, path: str, query: str, headers: dict[str, str]) -> None:
        self.status: int | None = None
        self.headers: dict[str, str] = {}
        self.text = ""
        self._chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._disconnect = asyncio.Event()
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                 "scheme": "https", "path": path, "raw_path": path.encode(), "query_string": query.encode(),
                 "root_path": "", "client": ("10.0.0.9", 4444), "server": ("testserver", 443),
                 "headers": [(b"host", b"testserver"),
                             *[(k.lower().encode(), v.encode()) for k, v in headers.items()]]}
        self._task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> dict[str, Any]:
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {k.decode(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            await self._chunks.put(message.get("body", b""))
            if not message.get("more_body", False):
                await self._chunks.put(None)

    async def read_until(self, needle: str, timeout: float = 5.0) -> str:
        async with asyncio.timeout(timeout):
            while needle not in self.text:
                chunk = await self._chunks.get()
                if chunk is None:
                    break
                self.text += chunk.decode()
        return self.text

    async def close(self) -> None:
        self._disconnect.set()
        async with asyncio.timeout(5):
            with contextlib.suppress(Exception):
                await self._task
