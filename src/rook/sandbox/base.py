"""The `Sandbox` interface (02 section 8): start the target app, give its base URL, stop it.

Every sandbox is a context manager: leaving the `with` block (normally or on an exception) stops it.
"""

import socket
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Self

from rook.agents.schemas import SandboxPlan

HEALTH_TIMEOUT = 60.0


class SandboxError(RuntimeError):
    """The sandbox could not start, stay healthy or run a command."""


@dataclass(frozen=True, slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


class Sandbox(ABC):
    @abstractmethod
    def start(self, plan: SandboxPlan | None = None) -> str:
        """Start the app, wait until its health check returns 200 and return its base URL."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the app and remove everything the run created. Safe to call more than once."""

    @abstractmethod
    def restart(self) -> str:
        """Stop and start again with fresh state (a new temp DB). Returns the base URL."""

    @abstractmethod
    def exec(self, cmd: Sequence[str], timeout: float = 600.0) -> ExecResult:
        """Run a command (an argv list, never a shell string) next to the app."""

    @abstractmethod
    def logs(self, tail: int = 200) -> str:
        """The last `tail` lines of the app's output."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.stop()


def free_port(host: str = "127.0.0.1") -> int:
    """A port that is free right now on `host` (the OS picks it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])
