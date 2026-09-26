"""The FastAPI server (02 §11): `create_app()` wires the settings, store, runs, auth seams and middleware.

`uvicorn rook.server.app:app` builds the app from the environment on first access (module `__getattr__`),
so importing this module never opens a database.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rook.core.events import EventBus
from rook.core.session import mark_interrupted
from rook.sandbox.allowlist import DEFAULT_ALLOWLIST, Allowlist
from rook.server.auth import GuestCookies, RejectAllTokens, TokenVerifier
from rook.server.config import ServerSettings
from rook.server.db import ServerDb
from rook.server.deps import ServerState
from rook.server.github_link import GitHubLink, NoGitHub
from rook.server.limits import BodySizeLimit, RateLimit
from rook.server.routes import meta, runs
from rook.server.runs import ReplayFactory, RunManager, SessionFactory, default_session_factory
from rook.store.repo import Store

API_PREFIX = "/api/v1"
log = logging.getLogger(__name__)


def _validation_detail(exc: RequestValidationError) -> str:
    """Where and what, never the offending input (it could hold a secret)."""
    parts = []
    for error in exc.errors()[:5]:
        where = ".".join(str(p) for p in error.get("loc", ()) if p != "body")
        parts.append(f"{where}: {error.get('msg', 'invalid')}" if where else str(error.get("msg", "invalid")))
    return "Invalid request: " + "; ".join(parts)


def create_app(
    settings: ServerSettings | None = None,
    *,
    verifier: TokenVerifier | None = None,
    github: GitHubLink | None = None,
    session_factory: SessionFactory | None = None,
    replay_factory: ReplayFactory | None = None,
    allowlist: Allowlist | None = None,
) -> FastAPI:
    settings = settings or ServerSettings.from_env()
    if allowlist is None:
        allowlist = Allowlist.from_yaml(settings.allowlist_path) if settings.allowlist_path else DEFAULT_ALLOWLIST
    store = Store(settings.db_path)
    bus = EventBus(store)
    manager = RunManager(store, bus, session_factory or default_session_factory(settings, allowlist),
                         max_concurrent=settings.max_concurrent_runs, max_queued=settings.max_queued_runs)
    state = ServerState(
        settings=settings, store=store, db=ServerDb(settings.db_path), bus=bus, runs=manager,
        verifier=verifier or RejectAllTokens(), cookies=GuestCookies(settings.guest_secret.get_secret_value(),
                                                                     secure=settings.cookie_secure),
        github=github or NoGitHub(), replay_factory=replay_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        interrupted = mark_interrupted(store, manager.live_ids())
        if interrupted:
            log.warning("marked %d interrupted run(s) as failed", len(interrupted))
        try:
            yield
        finally:
            await manager.shutdown()
            state.db.close()
            store.close()

    app = FastAPI(title="Rook", version=settings.version, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.rook = state

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": _validation_detail(exc)}, status_code=400)

    app.include_router(meta.router, prefix=API_PREFIX)
    app.include_router(runs.router, prefix=API_PREFIX)

    # Starlette runs the last-added middleware first: CORS, then rate limits, then the body size limit.
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_body_bytes)
    app.add_middleware(RateLimit, prefix=API_PREFIX, per_minute=settings.rate_per_minute,
                       runs_per_minute=settings.runs_per_minute, trusted_hops=settings.trusted_proxy_hops,
                       exempt=frozenset({f"{API_PREFIX}/health"}))
    app.add_middleware(CORSMiddleware, allow_origins=settings.web_origins, allow_credentials=True,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Accept"],
                       max_age=600)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
