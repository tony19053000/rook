"""The FastAPI server (02 §11): `create_app()` wires the settings, store, runs, auth seams and middleware.

`uvicorn rook.server.app:app` builds the app from the environment on first access (module `__getattr__`),
so importing this module never opens a database.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rook.core.events import EventBus, register_secret
from rook.core.session import mark_interrupted
from rook.github.app import GitHubApp
from rook.sandbox.allowlist import DEFAULT_ALLOWLIST, Allowlist
from rook.server.auth import GuestCookies, RejectAllTokens, TokenVerifier
from rook.server.config import ServerSettings
from rook.server.db import ServerDb
from rook.server.deps import ServerState
from rook.server.github_link import AppGitHub, GitHubLink, NoGitHub
from rook.server.github_runs import DockerProbe
from rook.server.limits import BodySizeLimit, RateLimit
from rook.server.logins import LoginFlows
from rook.server.routes import auth, meta, runs
from rook.server.routes import github as github_routes
from rook.server.runs import ReplayFactory, RunManager, SessionFactory, default_session_factory
from rook.server.supabase import SupabaseOAuth, SupabaseVerifier
from rook.store.repo import Store

API_PREFIX = "/api/v1"
WEBHOOK_PATH = f"{API_PREFIX}/github/webhook"
WEBHOOK_MAX_BYTES = 1024 * 1024  # installation events list the repos, which can be well over 64 KB
log = logging.getLogger(__name__)


def _validation_detail(exc: RequestValidationError) -> str:
    """Where and what, never the offending input (it could hold a secret)."""
    parts = []
    for error in exc.errors()[:5]:
        where = ".".join(str(p) for p in error.get("loc", ()) if p != "body")
        parts.append(f"{where}: {error.get('msg', 'invalid')}" if where else str(error.get("msg", "invalid")))
    return "Invalid request: " + "; ".join(parts)


def _github_app(settings: ServerSettings, db: ServerDb,
                transport: httpx.AsyncBaseTransport | None) -> GitHubLink:
    """The GitHub App when its id and private key are set (03 §6), else `NoGitHub`. Its secrets are registered
    with the redaction filter."""
    if settings.github_webhook_secret is not None:
        register_secret(settings.github_webhook_secret.get_secret_value())
    if settings.github_app_id is None or settings.github_app_private_key is None:
        return NoGitHub()
    secret = settings.github_client_secret.get_secret_value() if settings.github_client_secret else None
    app = GitHubApp(settings.github_app_id, settings.github_app_private_key.get_secret_value(),
                    api_url=settings.github_api_url, web_url=settings.github_web_url,
                    client_id=settings.github_client_id, client_secret=secret, transport=transport)
    return AppGitHub(app, db, slug=settings.github_app_slug, web_url=settings.github_web_url)


def create_app(
    settings: ServerSettings | None = None,
    *,
    verifier: TokenVerifier | None = None,
    github: GitHubLink | None = None,
    session_factory: SessionFactory | None = None,
    replay_factory: ReplayFactory | None = None,
    allowlist: Allowlist | None = None,
    oauth: SupabaseOAuth | None = None,
    github_transport: httpx.AsyncBaseTransport | None = None,
    docker_ready: Callable[[], bool] | None = None,
) -> FastAPI:
    settings = settings or ServerSettings.from_env()
    if allowlist is None:
        allowlist = Allowlist.from_yaml(settings.allowlist_path) if settings.allowlist_path else DEFAULT_ALLOWLIST
    store = Store(settings.db_path)
    bus = EventBus(store)
    manager = RunManager(store, bus, session_factory or default_session_factory(settings, allowlist),
                         max_concurrent=settings.max_concurrent_runs, max_queued=settings.max_queued_runs)
    if verifier is None and settings.supabase_url:
        secret = settings.supabase_jwt_secret.get_secret_value() if settings.supabase_jwt_secret else None
        verifier = SupabaseVerifier(settings.supabase_url, secret)
    if oauth is None and settings.supabase_url and settings.supabase_anon_key and settings.public_url:
        oauth = SupabaseOAuth(settings.supabase_url, settings.supabase_anon_key)
    guest_secret = settings.guest_secret.get_secret_value()
    db = ServerDb(settings.db_path)
    if github is None:
        github = _github_app(settings, db, github_transport)
    state = ServerState(
        settings=settings, store=store, db=db, bus=bus, runs=manager,
        verifier=verifier or RejectAllTokens(), cookies=GuestCookies(guest_secret, secure=settings.cookie_secure),
        github=github, replay_factory=replay_factory, logins=LoginFlows(guest_secret), oauth=oauth,
        docker_ready=docker_ready or DockerProbe(settings.workspaces_root, settings.sandbox_network))

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
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(github_routes.router, prefix=API_PREFIX)

    # Starlette runs the last-added middleware first: CORS, then rate limits, then the body size limit.
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_body_bytes,
                       overrides={WEBHOOK_PATH: max(WEBHOOK_MAX_BYTES, settings.max_body_bytes)})
    app.add_middleware(RateLimit, prefix=API_PREFIX, per_minute=settings.rate_per_minute,
                       runs_per_minute=settings.runs_per_minute, trusted_hops=settings.trusted_proxy_hops,
                       proxy_secret=settings.proxy_secret_value(),
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
