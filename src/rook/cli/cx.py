"""`rook replay | verify | explain <cx>`: work with a saved counterexample (`rook/counterexamples/cx_NNN.json`).

- replay: run the exact steps N times against your app and let the Judge decide (0 coins).
- verify: the Verifier's engine checks on your app: the exact replay and a fresh search. The project tests
  and the regression test run inside the sandbox during `rook run`; they are not run on this machine.
- explain: the counterexample in plain words (rule, minimal steps, observed vs expected), 0 coins.

replay and verify send HTTP only to `--base-url`, which must be the user's app on loopback. Values the
model needs (`{{env.NAME}}`) come from `ROOK_ENV_<NAME>`, like the generated regression test.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rook.agents.understand import MODEL_PATH
from rook.cli.runs import CliError
from rook.engine.executor import Executor
from rook.engine.judge import Judge
from rook.engine.replayer import DEFAULT_REPLAYS, Replayer
from rook.engine.testrunner import TestRun
from rook.engine.verifier import Verifier
from rook.export.counterexample import (
    CX_DIR,
    CX_ID,
    Counterexample,
    CxParallel,
    load_counterexample,
    replay_counterexample,
    rule_only_model,
)
from rook.export.tests import ENV_PREFIX, env_names
from rook.model.loader import load_model
from rook.model.schema import RookModel

EXIT_HOLDS, EXIT_BROKEN, EXIT_ERROR = 0, 1, 2
NOT_RUN_HERE = "not run here: it runs inside the sandbox during `rook run`"


def make_executor(model: RookModel, base_url: str, env: Mapping[str, str]) -> Executor:
    """The engine's HTTP client for the user's app (tests swap in an in-process app)."""
    return Executor(model, base_url, env=env)


def load(ref: str, repo: Path, model_path: Path | None = None) -> tuple[RookModel, Counterexample]:
    """`ref` is a cx id (looked up in `<repo>/rook/counterexamples/`) or a path to a cx JSON file."""
    path = Path(ref).expanduser()
    if CX_ID.fullmatch(ref):
        path = repo / CX_DIR / f"{ref}.json"
    elif path.suffix != ".json":
        raise CliError(f"{ref!r} is not a counterexample id (cx_001) or a .json file")
    if not path.is_file():
        raise CliError(f"no counterexample at {path}")
    model_file = model_path or repo / MODEL_PATH
    if not model_file.is_file():
        raise CliError(f"no model at {model_file} (pass --model)")
    try:
        return load_model(model_file), load_counterexample(path)
    except (ValueError, OSError) as exc:
        raise CliError(f"could not load the counterexample: {str(exc).splitlines()[0]}") from exc


def model_env(model: RookModel, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    names = env_names(model)
    missing = [ENV_PREFIX + n for n in names if ENV_PREFIX + n not in env]
    if missing:
        raise CliError(f"set {', '.join(missing)} (values your app's model uses)")
    return {n: env[ENV_PREFIX + n] for n in names}


@dataclass(frozen=True)
class Outcome:
    code: int
    lines: list[str]


async def replay(model: RookModel, cx: Counterexample, base_url: str, env: Mapping[str, str],
                 times: int = DEFAULT_REPLAYS) -> Outcome:
    restricted = rule_only_model(model, cx)
    judge = Judge(restricted)
    async with make_executor(restricted, base_url, env) as ex:
        result = await Replayer(restricted, ex, None, "cli", n=times, seed=cx.seed, judge=judge).replay(
            cx.rule.id, cx.to_trace(restricted))
        probe = await replay_counterexample(ex, model, cx) if result.k == 0 else None
    head = f"Replayed {cx.cx_id} ({len(cx.steps)} steps) {result.n} times on {base_url}"
    if result.k:
        flaky = " (flaky)" if result.flaky else ""
        return Outcome(EXIT_BROKEN, [head, f"✗ rule {cx.rule.id} broken in {result.k}/{result.n} replays{flaky}"])
    if judge.rule_errors or (probe is not None and not probe.holds):
        why = "; ".join(judge.rule_errors.values()) or (probe.message if probe else "")
        return Outcome(EXIT_ERROR, [head, f"! the replay proves nothing: {why}"])
    return Outcome(EXIT_HOLDS, [head, f"✓ rule {cx.rule.id} held in {result.n}/{result.n} replays"])


async def verify(model: RookModel, cx: Counterexample, base_url: str, env: Mapping[str, str], *,
                 sequences: int, seconds: float) -> Outcome:
    async def not_run() -> TestRun:
        return TestRun("regression test", -1, NOT_RUN_HERE, "")

    verifier = Verifier(model, lambda: make_executor(model, base_url, env), None, "cli",
                        budget_sequences=sequences, budget_seconds=seconds)
    result = await verifier.verify(cx, regression_test=not_run, project_tests=None)
    engine = [c for c in result.checks if c.check in ("replay", "fresh_search")]
    lines = [f"Verifying {cx.cx_id} (rule {cx.rule.id}) on {base_url}"]
    lines += [f"{'✓' if c.passed else '✗'} {c.check.replace('_', ' ')}: {c.detail}" for c in engine]
    lines.append(f"· project tests and regression test: {NOT_RUN_HERE}")
    if len(engine) == 2 and all(c.passed for c in engine):
        return Outcome(EXIT_HOLDS, [*lines, "✓ The engine checks passed: the rule holds on this app"])
    return Outcome(EXIT_BROKEN, [*lines, "✗ Not verified"])


def _step(step: Any) -> str:
    if isinstance(step, CxParallel):
        return "at the same time: " + " + ".join(_step(s) for s in step.parallel)
    params = json.dumps(step.params, sort_keys=True, default=str)
    return f"{step.actor} does {step.action} {params}"


def explain(cx: Counterexample) -> list[str]:
    lines = [f"Counterexample {cx.cx_id}", f"Rule {cx.rule.id}: {cx.rule.text}", f"  must hold: {cx.expected}",
             "Minimal steps:"]
    lines += [f"  {i}. {_step(s)}" for i, s in enumerate(cx.steps, 1)]
    lines += [f"The rule broke at step {cx.violated_at_step + 1}.",
              f"Observed: {json.dumps(cx.observed, sort_keys=True, default=str)}",
              f"Reproduced {cx.reproduced} on the real app" + (" (flaky)" if cx.flaky else "") + f", seed {cx.seed}."]
    return lines
