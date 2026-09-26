"""The seam between the TUI and whatever runs the work.

`SessionBackend` (session_backend.py) runs a Session in a worker thread and hands events back with
`app.call_from_thread(app.show_event, event)`. `OfflineBackend` only explains that nothing is connected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

from rook.core.events import Event, now_ts, validate_data

if TYPE_CHECKING:
    from rook.cli.tui.app import RookApp

LOCAL_RUN_ID = "local"


def make_event(seq: int, event_type: str, data: BaseModel | dict[str, Any], run_id: str = LOCAL_RUN_ID) -> Event:
    """A validated, redacted event (for local notices and tests)."""
    # model_validate (not the constructor) because `type` is a runtime string; pydantic still checks it.
    return Event.model_validate(
        {"seq": seq, "ts": now_ts(), "run_id": run_id, "type": event_type, "data": validate_data(event_type, data)}
    )


class Backend(Protocol):
    @property
    def running(self) -> bool:
        """Whether a run is active (plain text then goes to the Guide, Esc interrupts)."""
        ...

    def bind(self, app: RookApp) -> None: ...

    def submit(self, text: str) -> None:
        """Plain text: to the Coordinator when idle, to the Guide during a run."""
        ...

    def command(self, name: str, arg: str) -> None:
        """A validated slash command the TUI doesn't handle itself."""
        ...

    def answer(self, question_id: str, answer: Any) -> None:
        """The answer's shape depends on the question: approve_rules takes "all" | "none" | [rule ids]."""
        ...

    def interrupt(self) -> None: ...


class OfflineBackend:
    def __init__(self) -> None:
        self._app: RookApp | None = None
        self._seq = 0

    @property
    def running(self) -> bool:
        return False

    def bind(self, app: RookApp) -> None:
        self._app = app

    def _notice(self, text: str) -> None:
        if self._app is None:
            return
        self._seq += 1
        self._app.show_event(make_event(self._seq, "log", {"level": "info", "text": text}))

    def submit(self, text: str) -> None:
        self._notice("Runs aren't connected in this build yet.")

    def command(self, name: str, arg: str) -> None:
        self._notice(f"/{name} isn't connected in this build yet.")

    def answer(self, question_id: str, answer: Any) -> None:
        self._notice("There is no run to answer.")

    def interrupt(self) -> None:
        self._notice("There is no run to interrupt.")
