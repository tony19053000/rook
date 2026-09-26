"""Pilot helpers and real-schema sample events for the ROOK-027 prompt and card tests.

The payloads mirror what the producers publish: agents/rules.py (rules.proposed / rules.reviewed),
core/session.py (approve_rules, fix, pr and menu questions), agents/understand.py (setup_value) and
export/counterexample.py (counterexample.saved).
"""

from __future__ import annotations

from typing import Any

from textual.pilot import Pilot

from rook.cli.tui.app import RookApp
from rook.cli.tui.auth import AuthState, StubAuth
from rook.cli.tui.backend import make_event
from rook.cli.tui.widgets.prompts import register
from rook.core.events import Event

SIZE = (80, 40)


class FakeBackend:
    def __init__(self) -> None:
        self.running = True
        self.calls: list[tuple[Any, ...]] = []

    def bind(self, app: RookApp) -> None:
        self.app = app

    def submit(self, text: str) -> None:
        self.calls.append(("submit", text))

    def command(self, name: str, arg: str) -> None:
        self.calls.append(("command", name, arg))

    def answer(self, question_id: str, answer: Any) -> None:
        self.calls.append(("answer", question_id, answer))

    def interrupt(self) -> None:
        self.calls.append(("interrupt",))


def make_app(backend: FakeBackend | None = None) -> RookApp:
    app = RookApp(backend=backend or FakeBackend(), auth=StubAuth(AuthState(user="aayush", github_repos=1)),
                  motion=False)
    register(app)
    return app


async def booted(pilot: Pilot[Any], app: RookApp) -> None:
    for _ in range(200):
        if app.ready:
            await pilot.pause()
            return
        await pilot.pause(0.02)
    raise AssertionError("the app never finished booting")


class Events:
    """Numbered events for one run, validated against the real schema by `make_event`."""

    def __init__(self) -> None:
        self.seq = 0

    def __call__(self, event_type: str, data: dict[str, Any]) -> Event:
        self.seq += 1
        return make_event(self.seq, event_type, data, run_id="r1")


RULES: list[dict[str, Any]] = [
    {"id": "refund_le_paid", "text": "Refunds never exceed the amount paid", "kind": "state",
     "scope": "order", "check": "order.refunded <= order.paid",
     "evidence": ["src/refunds.js:40", "README"], "status": "proposed"},
    {"id": "total_positive", "text": "An order total is never negative", "kind": "response",
     "scope": "global", "when": {"action": "create_order"}, "check": "response.json.total >= 0",
     "evidence": ["src/orders.js:12"], "status": "proposed"},
    {"id": "stock_nonneg", "text": "Stock never goes below zero", "kind": "state", "scope": "global",
     "check": "state.stock >= 0", "evidence": ["src/stock.js:8"], "status": "proposed"},
]

VERDICTS: list[dict[str, Any]] = [
    {"rule_id": "stock_nonneg", "verdict": "reject", "reason": "stock is not exposed by any action",
     "by": "engine"},
    {"rule_id": "refund_le_paid", "verdict": "approve", "reason": "a real money invariant", "by": "critic"},
    {"rule_id": "total_positive", "verdict": "approve", "reason": "a response contract", "by": "critic",
     "already_broken": True},
]

APPROVE_PAYLOAD: dict[str, Any] = {"rules": [
    {"id": "refund_le_paid", "text": "Refunds never exceed the amount paid", "kind": "state",
     "check": "order.refunded <= order.paid", "accepted": True, "reason": "critic: a real money invariant",
     "critic": "approve", "already_broken": False},
    {"id": "total_positive", "text": "An order total is never negative", "kind": "response",
     "check": "response.json.total >= 0", "accepted": True,
     "reason": "critic: a response contract; engine: the first create_order broke it",
     "critic": "approve", "already_broken": True},
    {"id": "stock_nonneg", "text": "Stock never goes below zero", "kind": "state", "check": "state.stock >= 0",
     "accepted": False, "reason": "engine: stock is not exposed by any action", "critic": None,
     "already_broken": False},
]}


def approve_rules_question(question_id: str = "q_rules") -> dict[str, Any]:
    return {"question_id": question_id, "kind": "approve_rules", "text": "Approve 2 rules?",
            "options": [{"id": "all", "label": "Approve 2 rules"}, {"id": "none", "label": "Reject all"}],
            "payload": APPROVE_PAYLOAD}


def fix_question(question_id: str = "q_fix") -> dict[str, Any]:
    return {"question_id": question_id, "kind": "fix", "text": "Fix cx_001 in src/refunds.js:42?",
            "options": [{"id": "yes", "label": "Fix it"}, {"id": "no", "label": "Not now"}],
            "payload": {"cx_id": "cx_001", "file": "src/refunds.js", "line": 42,
                        "explanation": "each refund is checked alone", "reviewed": True}}


def pr_question(question_id: str = "q_pr") -> dict[str, Any]:
    return {"question_id": question_id, "kind": "pr",
            "text": "Ship the verified fix for cx_001 to a new branch (never the default branch)?",
            "options": [{"id": "yes", "label": "Ship it"}, {"id": "no", "label": "Not now"}],
            "payload": {"cx_id": "cx_001", "files": ["src/refunds.js"], "diff": "-a\n+b\n"}}


def menu_question(question_id: str = "q_menu") -> dict[str, Any]:
    return {"question_id": question_id, "kind": "menu",
            "text": "The search budget ran out with no violation. What next?",
            "options": [{"id": "extend", "label": "Search longer"}, {"id": "report", "label": "Write the report"},
                        {"id": "stop", "label": "Stop"}],
            "payload": {"branch": "search_exhausted", "agent": None}}


def setup_question(question_id: str = "q_setup", secret: bool = True) -> dict[str, Any]:
    return {"question_id": question_id, "kind": "setup_value",
            "text": "Your app needs PAYMENT_API_KEY. Enter a value for the sandbox (it is never logged).",
            "options": [], "payload": {"name": "PAYMENT_API_KEY", "secret": secret}}


STEPS: list[dict[str, Any]] = [
    {"action": "create_order", "actor": "alice", "params": {"amount": 100}, "refs": {}},
    {"action": "refund", "actor": "alice", "params": {"amount": 60}, "refs": {"order": 0}},
    {"parallel": [
        {"action": "refund", "actor": "alice", "params": {"amount": 50}, "refs": {"order": 0}},
        {"action": "refund", "actor": "bob", "params": {"amount": 10}, "refs": {"order": 0}},
    ]},
]

CX: dict[str, Any] = {"cx_id": "cx_001", "rule_id": "refund_le_paid", "rule_text": "Refunds never exceed the amount paid",
      "steps": STEPS, "observed": {"paid": 100, "refunded": 110}, "expected": "order.refunded <= order.paid",
      "reproduced": "10/10", "flaky": False, "test_path": None}

DIFF = """diff --git a/src/refunds.js b/src/refunds.js
--- a/src/refunds.js
+++ b/src/refunds.js
@@ -40,3 +40,4 @@ function refund(order, amount) {
-  if (amount > order.paid) throw new Error("too much");
+  if (order.refunded + amount > order.paid) throw new Error("too much");
   order.refunded += amount;
"""
