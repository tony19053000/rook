"""Helpers for the ROOK-024 CLI tests: a `build_session` that runs the real Session and engine on minishop
(served in-process from the run's workspace copy) with a scripted Bob, so a CI run costs 0 coins and needs
no Docker."""

from pathlib import Path
from typing import Any

from session_helpers import LocalLauncher, ScriptedClient
from test_pipeline_diagnose import REFUND_CHECK
from test_pipeline_understand import MAPPER_PARTS, MINISHOP_MODEL, SUMMARY

from rook.core.events import EventBus
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec

RULES = {r.id: r.model_dump(mode="json", by_alias=True, exclude_none=True) | {"status": "proposed"}
         for r in MINISHOP_MODEL.rules}
PLAN = {"mode": "command", "build": "pip install fastapi uvicorn", "start": "uvicorn app:app --port 8000",
        "port": 8000, "health_path": "/health", "env_required": [],
        "env_defaults": {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}}  # the fixture's default, not a secret
DOUBLE_REFUND = [{"action": "create_product", "params": {"price": 100, "stock": 5}},
                 {"action": "buy", "params": {"quantity": 1}},
                 {"action": "refund", "params": {"amount": 60}},
                 {"action": "refund", "params": {"amount": 60}}]
CI_FLAGS = ["--ci", "--seed", "1", "--sequences", "1500", "--seconds", "60"]


def approve_all(*ids: str) -> dict[str, Any]:
    return {"verdicts": [{"rule_id": i, "verdict": "approve", "reason": "backed by the code"} for i in ids]}


def script(rule_ids: tuple[str, ...] = ("refund_le_paid",), **overrides: list[Any]) -> dict[str, list[Any]]:
    """Scripted Bob up to the fix question: the lawmaker proposes `rule_ids`, the critic approves them all."""
    base: dict[str, list[Any]] = {
        "scout": [SUMMARY],
        "mechanic": [PLAN],
        "mapper": [MAPPER_PARTS],
        "lawmaker": [{"rules": [RULES[i] for i in rule_ids]}],
        "rule_critic": [approve_all(*rule_ids)],
        "test_designer": [{"scenarios": [{"name": "double refund", "rule_id": "refund_le_paid",
                                          "steps": DOUBLE_REFUND}]}],
        "strategist": [{"weights": {"refund": 2.0}, "focus": ["refund_le_paid"], "reason": "refunds add up"}],
        "detective": [{"file": "app.py", "line": REFUND_CHECK, "explanation": "refund() ignores earlier refunds",
                       "evidence": ["step 4: refunded 120 > paid 100"]}],
        "diag_reviewer": [{"verdict": "approve", "reason": "the cited line ignores earlier refunds"}],
        "coordinator": [{"next": "report", "reason": "nothing else to try"}],
        "guide": [{"answer": "Rook is searching."}],
    }
    base.update(overrides)
    return base


class ScriptedSessions:
    """Replaces `rook.cli.runs.build_session`: every Session it builds gets the scripted Bob and minishop
    (buggy, or fixed with `fixed=True`); keeps the sessions for assertions."""

    def __init__(self, tmp_path: Path, replies: dict[str, list[Any]], *, fixed: bool = False) -> None:
        self.tmp_path = tmp_path
        self.replies = replies
        self.launcher = LocalLauncher(fixed=fixed)
        self.sessions: list[Session] = []

    def __call__(self, repo: RepoSpec, request: str, options: SessionOptions) -> Session:
        def client(bus: EventBus, run_id: str, ws: Path) -> ScriptedClient:
            return ScriptedClient(bus, run_id, self.replies)

        fast = options.model_copy(update={"concurrency": 2, "verify_sequences": 300, "verify_seconds": 30.0})
        session = Session(repo, request, fast, workspaces_root=self.tmp_path / "workspaces",
                          client_factory=client, launcher_factory=self.launcher)
        self.sessions.append(session)
        return session

    @property
    def session(self) -> Session:
        return self.sessions[-1]

    def events(self, event_type: str) -> list[dict[str, Any]]:
        return [e.data for e in self.session.bus._channel(self.session.run_id).history if e.type == event_type]
