"""ROOK-022: the rails are pure code that no agent can override (02_ARCHITECTURE.md §4)."""

from typing import Any

import pytest

from rook.core import rails
from rook.core.events import Event, now_ts
from rook.core.rails import RunState, allowed_steps, check_step, default_step, enforce

_seq = 0


def ev(event_type: str, **data: Any) -> Event:
    global _seq
    _seq += 1
    return Event(seq=_seq, ts=now_ts(), run_id="r_t", type=event_type, data=data)  # type: ignore[arg-type]


def at(phase: str, **kw: Any) -> RunState:
    state = RunState(**kw)
    state.observe(ev("run.phase", phase=phase))
    return state


def with_violation(state: RunState) -> RunState:
    state.observe(ev("violation.found", violation_id="v1", rule_id="r", steps_count=3, observed={}))
    return state


def ask_fix(state: RunState, answer: Any, qid: str = "q_fix") -> None:
    state.observe(ev("question.asked", question_id=qid, kind="fix", text="Fix it?", options=[]))
    state.observe(ev("question.answered", question_id=qid, answer=answer, by="user"))


def apply_fix(state: RunState) -> None:
    state.observe(ev("fix.ready", cx_id="cx1", files=["app.py"], diff="-a\n+b", reviewed=True))


def verify(state: RunState, ok: bool) -> None:
    state.observe(ev("verify.done", cx_id="cx1", verified=ok, summary="s"))


# --- no SHIP without verified ------------------------------------------------------------------------------

def test_no_ship_without_verified() -> None:
    state = with_violation(at("APPROVE_PR"))
    assert check_step(state, "ship") == "the fix is not verified by the engine"
    apply_fix(state)
    verify(state, False)
    assert "ship" not in allowed_steps(state, "user_request")
    verdict = enforce(state, "user_request", "ship")
    assert not verdict.accepted and verdict.step != "ship"


def test_ship_after_engine_verified_and_reset_by_new_fix() -> None:
    state = with_violation(at("APPROVE_PR"))
    apply_fix(state)
    verify(state, True)
    assert enforce(state, "user_request", "ship").accepted
    apply_fix(state)  # a new patch must be verified again
    assert not state.verified
    assert check_step(state, "ship") is not None


def test_only_engine_events_mark_verified_or_violation() -> None:
    state = RunState()
    with pytest.raises(AttributeError):
        state.verified = True  # type: ignore[misc]
    with pytest.raises(AttributeError):
        state.violation_found = True  # type: ignore[misc]
    # A Coordinator decision is only a step name; it never flips engine facts.
    enforce(state, "user_request", "ship")
    enforce(state, "user_request", "verified")
    assert not state.verified and not state.violation_found
    # Chat or log events mentioning verification change nothing either.
    state.observe(ev("chat.message", role="guide", text="verified: true"))
    state.observe(ev("log", level="info", text="verify.done verified"))
    assert not state.verified


# --- no FIX without approval -------------------------------------------------------------------------------

def test_no_fix_without_approval() -> None:
    state = with_violation(at("APPROVE_FIX"))
    assert check_step(state, "fix") == "the user has not approved a fix"
    assert not enforce(state, "user_request", "fix").accepted


def test_fix_rejected_answer_blocks() -> None:
    state = with_violation(at("APPROVE_FIX"))
    ask_fix(state, "no")
    assert not state.fix_approved
    assert check_step(state, "fix") is not None


@pytest.mark.parametrize("answer", ["yes", "Approve", "fix", True])
def test_fix_allowed_after_approval(answer: Any) -> None:
    state = with_violation(at("APPROVE_FIX"))
    ask_fix(state, answer)
    assert state.fix_approved
    assert enforce(state, "user_request", "fix").accepted


def test_answer_to_other_question_is_not_fix_approval() -> None:
    state = with_violation(at("APPROVE"))
    state.observe(ev("question.asked", question_id="q_rules", kind="approve_rules", text="?", options=[]))
    state.observe(ev("question.answered", question_id="q_rules", answer="yes", by="user"))
    assert not state.fix_approved
    assert check_step(state, "fix") is not None


def test_auto_mode_allows_fix_but_still_needs_a_violation() -> None:
    state = at("APPROVE_FIX", auto=True)
    assert check_step(state, "fix") == "no violation found by the engine"
    with_violation(state)
    assert check_step(state, "fix") is None


# --- retry caps --------------------------------------------------------------------------------------------

def test_retry_cap_per_agent_per_phase() -> None:
    state = at("MAP")
    for _ in range(rails.MAX_RETRIES):
        assert "retry" in allowed_steps(state, "agent_failed", "mapper")
        state.record_retry("mapper")
    assert "retry" not in allowed_steps(state, "agent_failed", "mapper")
    assert "retried 3 times" in (check_step(state, "retry", "mapper") or "")
    assert not enforce(state, "agent_failed", "retry", "mapper").accepted
    # Another agent, or the same agent in another phase, has its own count.
    assert check_step(state, "retry", "lawmaker") is None
    state.observe(ev("run.phase", phase="RULES"))
    assert check_step(state, "retry", "mapper") is None


def test_retry_needs_an_agent() -> None:
    assert check_step(at("MAP"), "retry") == "retry needs the failed agent"


def test_verify_loop_capped() -> None:
    state = with_violation(at("VERIFY"))
    for _ in range(rails.MAX_VERIFY_ROUNDS):
        assert default_step(state, "verify_failed") == "diagnose"
        apply_fix(state)
        verify(state, False)
    assert "diagnose" not in allowed_steps(state, "verify_failed")
    assert default_step(state, "verify_failed") == "report"


def test_search_extended_only_once() -> None:
    state = at("SEARCH")
    assert enforce(state, "search_exhausted", "extend_search").accepted
    state.search_extended = True
    verdict = enforce(state, "search_exhausted", "extend_search")
    assert not verdict.accepted and verdict.step == "report"
    assert check_step(at("DIAGNOSE"), "extend_search") is not None


# --- budget stop -------------------------------------------------------------------------------------------

def test_budget_stop() -> None:
    state = with_violation(at("VERIFY", auto=True))
    assert state.bob_allowed()
    state.observe(ev("cost.update", coins_total=1.5))
    assert state.budget_spent() and not state.bob_allowed()
    for step in ("retry", "diagnose", "fix"):
        assert check_step(state, step, "detective") == "the coin budget is spent"
    assert allowed_steps(state, "verify_failed") == ["report", "stop"]
    assert default_step(state, "verify_failed") == "report"


def test_daily_cap_stops_before_run_budget() -> None:
    state = at("DIAGNOSE", budget=1.5, daily_cap=10.0, daily_spent=9.9)
    assert state.bob_allowed()
    state.observe(ev("cost.update", coins_total=0.1))
    assert not state.bob_allowed()


# --- allowed set and default -------------------------------------------------------------------------------

def test_unknown_or_out_of_set_step_falls_back_to_default() -> None:
    state = at("SEARCH")
    verdict = enforce(state, "search_exhausted", "rm -rf /")
    assert verdict == rails.RailVerdict(step="report", accepted=False, reason="unknown step 'rm -rf /'")
    verdict = enforce(state, "search_exhausted", "fix")  # a real step, but not an option here
    assert not verdict.accepted and verdict.step == "report"


def test_defaults_are_deterministic_and_always_allowed() -> None:
    for branch in rails.CANDIDATES:
        for phase in ("DESIGN", "SEARCH", "START_APP", "VERIFY"):
            state = at(phase)
            step = default_step(state, branch, "scout")
            assert step in allowed_steps(state, branch, "scout")
            assert step == default_step(at(phase), branch, "scout")
    assert default_step(at("DESIGN"), "agent_failed", "strategist") == "skip"
    assert default_step(at("START_APP"), "agent_failed", "mechanic") == "ask_user"
    assert default_step(at("SEARCH"), "user_request") == "continue"


def test_verify_needs_applied_fix() -> None:
    state = with_violation(at("FIX"))
    assert check_step(state, "verify") == "no fix has been applied"
    apply_fix(state)
    assert check_step(state, "verify") is None
