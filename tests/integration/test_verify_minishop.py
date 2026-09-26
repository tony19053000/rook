"""ROOK-011 acceptance over real HTTP: minishop runs as a real uvicorn subprocess (ProcessSandbox).

- The generated fallback regression test is written to disk and run with pytest in a subprocess
  against the running app: it fails on buggy minishop and passes with MINISHOP_FIXED=1.
- The full Verifier (project tests via `Sandbox.exec`, the generated regression test, replay and a
  fresh search) fails on buggy minishop and passes all 4 checks on the fixed one.
No Docker, no Bob: part of the default suite.
"""

import functools
import sys
from pathlib import Path

import pytest

from rook.core.events import EventBus
from rook.engine.executor import Executor
from rook.engine.testrunner import TestRunner
from rook.engine.verifier import Verifier
from rook.export.counterexample import Counterexample, CxStep, model_hash, save_counterexample
from rook.export.tests import run_generated_test, write_fallback_test
from rook.model.loader import load_model
from rook.sandbox import Allowlist, AllowlistEntry, ProcessSandbox

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX-only")

MINISHOP_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
SHA = "0" * 40
ENV = {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}  # the fixture's built-in default, not a secret
PROJECT_TESTS = ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_minishop_app.py"]
MODEL = load_model(MINISHOP_DIR / "rook.yaml")


def sandbox(*, fixed: bool) -> ProcessSandbox:
    entry = AllowlistEntry(
        repo="rook-fixtures/minishop",
        commit=SHA,
        app_dir=MINISHOP_DIR,
        start=["{python}", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "{port}"],
        db_env="MINISHOP_DB",
        env={**ENV, **({"MINISHOP_FIXED": "1"} if fixed else {})},
        commands={"test": PROJECT_TESTS},
    )
    return ProcessSandbox("rook-fixtures/minishop", SHA, allowlist=Allowlist([entry]))


def refund_cx() -> Counterexample:
    """The shrunk refund counterexample (buy, refund, refund + product setup), as the engine saves it."""
    return Counterexample(
        cx_id="cx_001",
        rule={
            "id": "refund_le_paid",
            "text": 'Total refunds never exceed the amount paid """; import os #',
            "kind": "state",
            "scope": "order",
            "check": "order.refunded <= order.paid",
        },
        steps=[
            CxStep(action="create_product", actor="admin", params={"price": 1, "stock": 1}),
            CxStep(action="buy", actor="customer", params={"quantity": 1}, refs={"product_id": 0}),
            CxStep(action="refund", actor="customer", params={"amount": 1}, refs={"order_id": 0}),
            CxStep(action="refund", actor="customer", params={"amount": 1}, refs={"order_id": 0}),
        ],
        violated_at_step=3,
        observed={"paid": 1, "refunded": 2, "status": "paid\n'''\"; import os", "shipped": False},
        expected="order.refunded <= order.paid",
        reproduced="10/10",
        flaky=False,
        seed=1,
        model_hash=model_hash(MODEL),
    )


@pytest.fixture(scope="module")
def generated_test(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("target")
    cx = refund_cx()
    save_counterexample(root, cx)
    return write_fallback_test(root, cx, MODEL)


@pytest.mark.parametrize(("fixed", "exit_code"), [(False, 1), (True, 0)])
def test_generated_test_fails_on_buggy_and_passes_on_fixed(
    generated_test: Path, fixed: bool, exit_code: int
) -> None:
    with sandbox(fixed=fixed) as box:
        base_url = box.start()
        result = run_generated_test(generated_test, base_url, ENV, timeout=120)
    output = result.stdout + result.stderr
    assert result.exit_code == exit_code, output
    if fixed:
        assert "1 passed" in output
    else:
        assert "1 failed" in output and "broken again at step 4" in output


async def test_verifier_over_real_http(generated_test: Path) -> None:
    cx = refund_cx()
    runs = {}
    for fixed in (False, True):
        bus = EventBus()
        with sandbox(fixed=fixed) as box:
            base_url = box.start()
            tests = TestRunner(bus, "r_test")
            async with Executor(MODEL, base_url, env=ENV) as ex:
                verifier = Verifier(
                    MODEL, ex, bus, "r_test", seed=11, budget_sequences=300, budget_seconds=60, concurrency=8
                )
                runs[fixed] = await verifier.verify(
                    cx,
                    regression_test=functools.partial(tests.run_fallback, generated_test, base_url, ENV),
                    project_tests=functools.partial(tests.run_in_sandbox, box, PROJECT_TESTS),
                )

    buggy, fixed_result = runs[False], runs[True]
    assert not buggy.verified
    assert [c.passed for c in buggy.checks][:3] == [False, True, False]
    assert fixed_result.verified, fixed_result.checks
    replay, project, regression, search = fixed_result.checks
    assert replay.detail == "rule refund_le_paid held in 10/10 replays"
    assert project.passed and "passed" in project.detail
    assert regression.passed and "1 passed" in regression.detail
    assert search.passed and search.detail.startswith("no violation of 4 rules in 300 sequences")
