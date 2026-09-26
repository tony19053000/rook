"""ROOK-011: the Verifier, in-process against minishop (buggy vs MINISHOP_FIXED).

The regression check here replays the counterexample in-process; the real generated test run as a
pytest subprocess against a real minishop is in tests/integration/test_verify_minishop.py.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from test_export import found_cx
from test_shrinker import MODEL, REFUND, executor, only_rules

from rook.core.events import Event, EventBus
from rook.engine.executor import Executor
from rook.engine.inprocess import InProcessTransport
from rook.engine.runner import Runner
from rook.engine.testrunner import TestRun
from rook.engine.verifier import Verifier, VerifyResult, _CountingJudge
from rook.export.counterexample import Counterexample, replay_counterexample

SMALL = {"budget_sequences": 1_500, "budget_seconds": 120.0, "concurrency": 4}


def in_process_regression(cx: Counterexample, *, fixed: bool) -> Callable[[], Awaitable[TestRun]]:
    async def run() -> TestRun:
        async with executor(MODEL, fixed=fixed) as ex:
            outcome = await replay_counterexample(ex, MODEL, cx)
        return TestRun("regression", 0 if outcome.holds else 1, outcome.message, "")

    return run


def canned(exit_code: int, summary: str) -> Callable[[], Awaitable[TestRun]]:
    async def run() -> TestRun:
        return TestRun("project tests", exit_code, summary, "")

    return run


async def verify(
    cx: Counterexample,
    *,
    fixed: bool,
    bus: EventBus | None = None,
    project_exit: int | None = 0,
    **kwargs: object,
) -> VerifyResult:
    project = None if project_exit is None else canned(project_exit, f"exit {project_exit}")
    options = {**SMALL, **kwargs}
    async with executor(MODEL, fixed=fixed) as ex:
        verifier = Verifier(MODEL, ex, bus, "r_test", seed=7, **options)  # type: ignore[arg-type]
        return await verifier.verify(
            cx, regression_test=in_process_regression(cx, fixed=fixed), project_tests=project
        )


async def events_of(bus: EventBus) -> list[Event]:
    await bus.close("r_test")
    return [e async for e in bus.subscribe("r_test")]


@pytest.fixture(scope="module")
async def cx() -> Counterexample:
    return await found_cx(1)


async def test_buggy_minishop_is_not_verified(cx: Counterexample) -> None:
    bus = EventBus()
    result = await verify(cx, fixed=False, bus=bus)
    assert not result.verified
    by_check = {c.check: c for c in result.checks}
    assert list(by_check) == ["replay", "project_tests", "regression_test", "fresh_search"]
    assert not by_check["replay"].passed and "10/10" in by_check["replay"].detail
    assert by_check["project_tests"].passed  # minishop's own happy-path tests pass on the buggy app
    assert not by_check["regression_test"].passed
    assert not by_check["fresh_search"].passed and "new violation" in by_check["fresh_search"].detail

    events = await events_of(bus)
    steps = [(e.data["check"], e.data["status"]) for e in events if e.type == "verify.step"]
    assert steps == [
        ("replay", "running"),
        ("replay", "failed"),
        ("project_tests", "running"),
        ("project_tests", "passed"),
        ("regression_test", "running"),
        ("regression_test", "failed"),
        ("fresh_search", "running"),
        ("fresh_search", "failed"),
    ]
    (done,) = [e for e in events if e.type == "verify.done"]
    assert done.data == {"cx_id": "cx_001", "verified": False, "summary": result.summary}
    assert "failed: replay, regression_test, fresh_search" in result.summary
    workers = [(e.type, e.data["worker"]) for e in events if e.type.startswith("engine.")]
    assert workers[0] == ("engine.started", "verifier") and workers[-1] == ("engine.finished", "verifier")


async def test_fixed_minishop_passes_all_four_checks(cx: Counterexample) -> None:
    bus = EventBus()
    result = await verify(cx, fixed=True, bus=bus)
    assert result.verified, result.checks
    assert [c.passed for c in result.checks] == [True] * 4
    replay, _, _, search = result.checks
    assert replay.detail == "rule refund_le_paid held in 10/10 replays"
    assert search.detail.startswith("no violation of 4 rules in 1500 sequences")
    events = await events_of(bus)
    assert [e.data["status"] for e in events if e.type == "verify.step"] == ["running", "passed"] * 4
    (done,) = [e for e in events if e.type == "verify.done"]
    assert done.data["verified"] is True and done.data["summary"] == "4/4 checks passed"


async def test_any_failing_check_blocks_verification(cx: Counterexample) -> None:
    result = await verify(cx, fixed=True, project_exit=1)
    assert not result.verified
    assert [c.passed for c in result.checks] == [True, False, True, True]


async def test_no_project_test_command_is_reported(cx: Counterexample) -> None:
    result = await verify(cx, fixed=True, project_exit=None, budget_sequences=200)
    assert result.verified
    assert result.checks[1].detail == "skipped: the project has no test command"


async def test_a_replay_that_cannot_run_does_not_pass(cx: Counterexample) -> None:
    """Fixed app, but the admin login fails: nothing is exercised, so nothing is verified."""
    async with executor(MODEL, fixed=True) as ex:
        ex.env["MINISHOP_ADMIN_PASSWORD"] = "wrong"
        result = await Verifier(MODEL, ex, None, "r", seed=3, **SMALL).verify(  # type: ignore[arg-type]
            cx, regression_test=canned(0, "ok"), project_tests=canned(0, "ok")
        )
    assert not result.verified
    replay = result.checks[0]
    assert not replay.passed and "did not fully run" in replay.detail


async def test_a_crashing_check_fails_without_stopping_the_others(cx: Counterexample) -> None:
    async def boom() -> TestRun:
        raise RuntimeError("sandbox went away")

    async with executor(MODEL, fixed=True) as ex:
        result = await Verifier(MODEL, ex, None, "r", seed=3, **SMALL).verify(  # type: ignore[arg-type]
            cx, regression_test=boom
        )
    assert [c.passed for c in result.checks] == [True, True, False, True]
    assert result.checks[2].detail == "error: RuntimeError: sandbox went away"


async def always_500(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 500, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_a_fresh_search_that_exercises_nothing_fails(cx: Counterexample) -> None:
    """Every request gets a 500: nothing is captured, so no state rule is ever evaluated."""
    ex = Executor(REFUND, "http://broken.test", transport=InProcessTransport(always_500))
    async with ex:
        verifier = Verifier(REFUND, ex, None, "r", seed=3, budget_sequences=50, concurrency=2)
        result = await verifier.verify(cx, regression_test=canned(0, "ok"))
    search = result.checks[3]
    assert not search.passed
    assert (
        search.detail == "fresh search could not exercise the app: no step got a successful (<400) response"
    )


async def auth_only(scope: Any, receive: Any, send: Any) -> None:
    """Actor setup (/auth/*) works; every action gets a 403."""
    if scope["path"].startswith("/auth/"):
        headers = [(b"content-type", b"application/json")]
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": b'{"token": "t"}'})
        return
    await send({"type": "http.response.start", "status": 403, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_a_fresh_search_with_only_error_responses_fails_even_if_rules_ran(cx: Counterexample) -> None:
    """Every action gets a 403: the response rule is evaluated (and holds), but no step of the search
    got a single successful response, so it proves nothing about the app."""
    model = only_rules("admin_export_forbidden")
    ex = Executor(model, "http://broken.test", transport=InProcessTransport(auth_only))
    async with ex:
        verifier = Verifier(model, ex, None, "r", seed=3, budget_sequences=200, concurrency=2)
        search = await verifier._fresh_search(ex)
        judge = _CountingJudge(model)
        await Runner(model, ex, None, "r", seed=3, budget_sequences=200, concurrency=2, judge=judge).run()
    assert judge.checks > 0 and judge.ok_responses == 0  # the rule did run, on 403s only
    assert search == (
        False,
        "fresh search could not exercise the app: no step got a successful (<400) response",
    )
