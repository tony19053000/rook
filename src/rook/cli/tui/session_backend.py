"""The real TUI backend: runs a Session in a worker thread (its own asyncio loop) and shows its events.

- events → posted to the app's event loop in order (02_ARCHITECTURE.md section 12). Like
  `app.call_from_thread`, but it never blocks the run: a run that is still stopping after the shell has quit
  must not wait on an app loop that is gone.
- answers → `Session.answer` (thread-safe); a refused answer is shown, never retried silently
- plain text → `Session.chat` (the Guide) during a run; when idle it starts a run on the current repo
- Esc (confirmed) → `Session.cancel`; `close()` cancels a live run and waits for its thread when the app quits
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rook.cli.runs import CliError, build_session, parse_repo
from rook.cli.tui.backend import make_event
from rook.core.events import Event
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec

if TYPE_CHECKING:
    from rook.cli.tui.app import RookApp

SessionFactory = Callable[[RepoSpec, str, SessionOptions], Session]
DEFAULT_REQUEST = "find bugs in my app"
CLOSE_WAIT = 30.0  # seconds `close()` waits for a cancelled run to stop its sandboxes


class SessionBackend:
    def __init__(
        self,
        repo: str | None = None,
        *,
        options: SessionOptions | None = None,
        factory: SessionFactory | None = None,
        start_request: str | None = None,
        cwd: Path | None = None,
    ) -> None:
        """`repo` is the default repo for plain requests (default: the current folder). With
        `start_request`, a run on `repo` starts as soon as the app is ready (`rook run` without --ci)."""
        self.repo = repo
        self.options = options or SessionOptions()
        self.factory: SessionFactory = factory or build_session
        self.cwd = cwd
        self.session: Session | None = None
        self._thread: threading.Thread | None = None
        self._app: RookApp | None = None
        self._app_loop: asyncio.AbstractEventLoop | None = None
        self._start_request = start_request
        self._notices = 0

    # --- Backend protocol ---

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def bind(self, app: RookApp) -> None:
        """Called by the app on mount, on its own loop."""
        self._app = app
        self._app_loop = asyncio.get_running_loop()
        if self._start_request is not None:
            request, self._start_request = self._start_request, None
            self._when_ready(lambda: self.start(self.repo, request))

    def submit(self, text: str) -> None:
        if self.running and self.session is not None:
            if not self.session.chat(text):
                self._notice("The Guide can't answer right now.")
            return
        self.start(self.repo, text)

    def command(self, name: str, arg: str) -> None:
        match name:
            case "run":
                if self.running:
                    self._notice("A run is already going. Press Esc twice to interrupt it first.")
                else:
                    self.start(arg or self.repo, DEFAULT_REQUEST)
            case "auto":
                self.options = self.options.model_copy(update={"auto": arg == "on"})
                if self.running:
                    self._notice("Auto-approve applies from the next run.")
            case "repo":
                self._notice("Start a run on another repo with /run <folder or owner/name>.")
            case "replay" | "explain" | "verify":
                self._notice(f"In a shell: rook {name} {arg} (see rook {name} --help).")
            case _:
                self._notice(f"/{name} isn't connected in this build yet.")

    def answer(self, question_id: str, answer: Any) -> None:
        session = self.session
        if session is None or not self.running:
            self._notice("There is no run to answer.")
        elif not session.answer(question_id, answer):
            self._notice("That answer wasn't accepted (the question is closed, or the answer doesn't fit it).")

    def interrupt(self) -> None:
        if self.session is not None and self.running:
            self.session.cancel()

    # --- runs ---

    def start(self, repo_ref: str | None, request: str) -> bool:
        """Start a run in a worker thread; False (with a notice) if it can't start."""
        if self.running:
            self._notice("A run is already going.")
            return False
        try:
            repo = parse_repo(repo_ref or ".", self.cwd)
            session = self.factory(repo, request, self.options)
        except (CliError, ValueError) as exc:
            self._notice(str(exc).splitlines()[0])
            return False
        self.session = session
        self._thread = threading.Thread(target=self._thread_main, args=(session,), name="rook-run", daemon=True)
        self._thread.start()
        return True

    def close(self, timeout: float = CLOSE_WAIT) -> None:
        """Cancel a live run and wait for it to clean up (the app is quitting)."""
        if self.session is not None and self.running:
            self.session.cancel()
        if self._thread is not None:
            self._thread.join(timeout)

    def _thread_main(self, session: Session) -> None:
        asyncio.run(self._drive(session))

    async def _drive(self, session: Session) -> None:
        async def follow() -> None:
            async for event in session.events():
                self._show(event)

        follower = asyncio.create_task(follow())
        try:
            await session.run()
        except Exception as exc:  # noqa: BLE001 - shown to the user; the Session already cleaned up
            self._notice(f"The run stopped: {type(exc).__name__}")
        finally:
            await asyncio.wait([follower], timeout=5.0)
            follower.cancel()

    # --- app side ---

    def _show(self, event: Event) -> None:
        """From the run's thread: show `event` on the app's loop, without waiting for it."""
        loop = self._app_loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._show_now, event)
        except RuntimeError:  # the app's loop is closed: the shell has quit
            pass

    def _show_now(self, event: Event) -> None:
        app = self._app
        if app is not None and app.is_running:
            app.show_event(event)

    def _when_ready(self, fn: Callable[[], Any]) -> None:
        """Run `fn` once the app has booted (logo and first-run steps first, then the run)."""
        app = self._app
        assert app is not None

        def check() -> None:
            if app.ready:
                timer.stop()
                fn()

        timer = app.set_interval(0.05, check)

    def _notice(self, text: str) -> None:
        app = self._app
        if app is None:
            return
        self._notices += 1
        event = make_event(self._notices, "log", {"level": "info", "text": text})
        if threading.current_thread() is self._thread:  # from the run's thread: post it to the app
            self._show(event)
        else:
            app.show_event(event)
