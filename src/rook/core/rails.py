"""Rails: the hard limits on a run's route that no agent can override (02_ARCHITECTURE.md §4).

Pure code, no I/O. The Coordinator (Bob) may *suggest* the next step at a branch point; `enforce` only
accepts it when it is in the allowed set, otherwise the deterministic default is used.

- `next` must be in the allowed set for the branch point
- no FIX without an approving answer to the "fix" question (or `--auto`)
- no SHIP without `verify.done{verified: true}` for the latest fix
- only engine events mark a violation as found or a fix as verified: those flags change only through
  `RunState.observe(event)` and have no setters
- at most 3 retries per agent per phase
- a coin budget per run (default 1.5) and an optional daily cap; once spent, no step that needs live Bob
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from rook.core.events import Event, Phase

Branch = Literal["agent_failed", "search_exhausted", "verify_failed", "user_request"]
Step = Literal[
    "continue",       # keep to the default path
    "retry",          # run the failed agent again
    "skip",           # skip an optional phase
    "ask_user",       # ask the user (setup value or a menu)
    "extend_search",  # search once more with a fresh budget
    "diagnose",       # go (back) to DIAGNOSE
    "fix",            # go to FIX
    "verify",         # go to VERIFY
    "ship",           # go to SHIP
    "report",         # finish and report honestly
    "stop",           # stop the run
]
STEPS: tuple[Step, ...] = get_args(Step)

MAX_RETRIES = 3
MAX_VERIFY_ROUNDS = 3
DEFAULT_RUN_BUDGET = 1.5
SKIPPABLE_PHASES: frozenset[str] = frozenset({"DESIGN"})  # the search also runs without scenarios/weights
BOB_STEPS: frozenset[str] = frozenset({"retry", "diagnose", "fix"})  # steps that need a live Bob call
FIX_APPROVALS = frozenset({"yes", "y", "approve", "approved", "fix", "apply"})

# The steps a Coordinator may pick at each branch point, before the per-step rails filter them.
CANDIDATES: dict[Branch, tuple[Step, ...]] = {
    "agent_failed": ("retry", "skip", "ask_user", "report", "stop"),
    "search_exhausted": ("extend_search", "report", "stop"),
    "verify_failed": ("diagnose", "report", "stop"),
    "user_request": ("continue", "extend_search", "diagnose", "fix", "verify", "ship", "report", "stop"),
}
# The deterministic default: the first allowed step in this order ("report" and "stop" are always allowed).
DEFAULT_ORDER: dict[Branch, tuple[Step, ...]] = {
    "agent_failed": ("skip", "ask_user", "stop"),
    "search_exhausted": ("report",),
    "verify_failed": ("diagnose", "report"),
    "user_request": ("continue",),
}


def is_approval(answer: Any) -> bool:
    if answer is True:
        return True
    return isinstance(answer, str) and answer.strip().lower() in FIX_APPROVALS


@dataclass
class RunState:
    """What the rails need to know about a run. Engine facts are private and change only via `observe`."""

    auto: bool = False
    budget: float = DEFAULT_RUN_BUDGET
    daily_cap: float | None = None
    daily_spent: float = 0.0  # coins spent today before this run (hosted server)
    phase: Phase = "PREPARE"
    coins_spent: float = 0.0
    search_extended: bool = False
    retries: dict[str, int] = field(default_factory=dict)  # "<PHASE>:<agent>" -> retries used
    _violation_found: bool = False
    _fix_approved: bool = False
    _fix_applied: bool = False
    _verified: bool = False
    _verify_rounds: int = 0
    _question_kinds: dict[str, str] = field(default_factory=dict)

    @property
    def violation_found(self) -> bool:
        return self._violation_found

    @property
    def fix_approved(self) -> bool:
        return self._fix_approved

    @property
    def fix_applied(self) -> bool:
        return self._fix_applied

    @property
    def verified(self) -> bool:
        return self._verified

    @property
    def verify_rounds(self) -> int:
        return self._verify_rounds

    def observe(self, event: Event) -> None:
        """Update the state from a published event (the only way engine facts change)."""
        data = event.data
        if event.type == "run.phase":
            self.phase = data["phase"]
        elif event.type == "cost.update":
            self.coins_spent = float(data["coins_total"])
        elif event.type == "violation.found":
            self._violation_found = True
        elif event.type == "question.asked":
            self._question_kinds[data["question_id"]] = data["kind"]
        elif event.type == "question.answered":
            if self._question_kinds.get(data["question_id"]) == "fix":
                self._fix_approved = is_approval(data["answer"])
        elif event.type == "fix.ready":
            self._fix_applied = True
            self._verified = False  # a new patch needs a new verification
        elif event.type == "verify.done":
            self._verified = bool(data["verified"])
            self._verify_rounds += 1

    def retries_used(self, agent: str) -> int:
        return self.retries.get(f"{self.phase}:{agent}", 0)

    def record_retry(self, agent: str) -> None:
        key = f"{self.phase}:{agent}"
        self.retries[key] = self.retries.get(key, 0) + 1

    def budget_spent(self) -> bool:
        if self.coins_spent >= self.budget:
            return True
        return self.daily_cap is not None and self.daily_spent + self.coins_spent >= self.daily_cap

    def bob_allowed(self) -> bool:
        """Live Bob calls are refused once the run budget or the daily cap is spent."""
        return not self.budget_spent()

    def summary(self) -> dict[str, Any]:
        """A compact, deterministic view (no timestamps) for the Coordinator prompt."""
        return {
            "phase": self.phase,
            "auto": self.auto,
            "coins_spent": round(self.coins_spent, 4),
            "coin_budget": self.budget,
            "violation_found": self._violation_found,
            "fix_approved": self._fix_approved or self.auto,
            "fix_applied": self._fix_applied,
            "verified": self._verified,
            "verify_rounds": self._verify_rounds,
            "search_extended": self.search_extended,
        }


def check_step(state: RunState, step: str, agent: str | None = None) -> str | None:
    """Return why `step` is not allowed right now, or None if the rails allow it."""
    if step not in STEPS:
        return f"unknown step {step!r}"
    if step in BOB_STEPS and not state.bob_allowed():
        return "the coin budget is spent"
    if step == "retry":
        if agent is None:
            return "retry needs the failed agent"
        if state.retries_used(agent) >= MAX_RETRIES:
            return f"{agent} already retried {MAX_RETRIES} times in {state.phase}"
    elif step == "skip" and state.phase not in SKIPPABLE_PHASES:
        return f"{state.phase} cannot be skipped"
    elif step == "extend_search":
        if state.phase != "SEARCH":
            return "the search can only be extended during SEARCH"
        if state.search_extended:
            return "the search was already extended once"
    elif step == "diagnose":
        if not state.violation_found:
            return "no violation found by the engine"
        if state.verify_rounds >= MAX_VERIFY_ROUNDS:
            return f"verification already failed {MAX_VERIFY_ROUNDS} times"
    elif step == "fix":
        if not state.violation_found:
            return "no violation found by the engine"
        if not (state.fix_approved or state.auto):
            return "the user has not approved a fix"
    elif step == "verify" and not state.fix_applied:
        return "no fix has been applied"
    elif step == "ship" and not state.verified:
        return "the fix is not verified by the engine"
    return None


def allowed_steps(state: RunState, branch: Branch, agent: str | None = None) -> list[Step]:
    return [s for s in CANDIDATES[branch] if check_step(state, s, agent) is None]


def default_step(state: RunState, branch: Branch, agent: str | None = None) -> Step:
    allowed = allowed_steps(state, branch, agent)
    for step in DEFAULT_ORDER[branch]:
        if step in allowed:
            return step
    return "report" if "report" in allowed else "stop"


@dataclass(frozen=True)
class RailVerdict:
    step: Step
    accepted: bool  # True when the proposed step was used
    reason: str  # why the proposal was rejected ("" when accepted)


def enforce(state: RunState, branch: Branch, proposed: str, agent: str | None = None) -> RailVerdict:
    """Accept `proposed` only if the rails allow it at this branch point; otherwise use the default."""
    allowed = allowed_steps(state, branch, agent)
    if proposed in allowed:
        return RailVerdict(step=proposed, accepted=True, reason="")  # type: ignore[arg-type]
    why = check_step(state, proposed, agent) or f"{proposed!r} is not an option at {branch}"
    return RailVerdict(step=default_step(state, branch, agent), accepted=False, reason=why)
