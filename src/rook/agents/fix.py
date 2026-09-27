"""The regression test, FIX and VERIFY phases: Surgeon -> path guard -> Fix Reviewer -> Verifier.

Bob proposes and code decides (CLAUDE.md rules 1, 4 and 5):

1. Regression test (02 sections 5.3 and 7.8). A test-only Surgeon call may create exactly one new file,
   the native regression test (its path is chosen by Rook). The path guard reverts anything else. The
   engine runs the test next to the app (`TestHarness.run_native`), and it must FAIL on the buggy app
   (exit code 1, no errors). If it passes, errors, cannot be run, or the call broke the guard, the test is
   removed and the generated HTTP-level test of ROOK-011 is used instead (said so in a `log` event and
   in `RegressionTest.reason`). The phase ends with `counterexample.saved{test_path}`.
2. FIX (02 section 4). Refused unless the rails allow it: the user answered the "fix" question with an
   approval (or `--auto`). Up to 3 rounds; each starts from the same pre-fix workspace. The Surgeon may
   edit only the diagnosed file (its mode's fileRegex, then the path guard, which reverts everything
   else and rejects the round). The accepted regression test is frozen: it proved the bug by failing,
   so the fix may not change it. The Fix Reviewer sees the diff; only its approval keeps the patch and
   emits `fix.ready`. A rejected round is fully reverted and its reasons go back to the Surgeon, wrapped
   as untrusted data. After 3 rounds without approval the workspace is left as it was, honestly.
3. VERIFY (02 section 7.7). The app is reloaded with the patch and the Verifier's four checks decide.
   The Fix Reviewer never decides whether the fix is verified.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from rook.agents import edit_tape
from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.diagnose import (
    DiagnosisResult,
    _is_test,
    _rule_input,
    _source_files,
    _steps_input,
    check_diagnosis,
)
from rook.agents.modes import write_modes
from rook.agents.prompts import render_prompt
from rook.agents.recorder import recording_key
from rook.agents.registry import get
from rook.agents.schemas import Diagnosis, FixReviewOutput, SurgeonOutput
from rook.agents.understand import check_not_rook_repo
from rook.agents.volatile import Masker, mask_text
from rook.core import rails
from rook.core.events import FixReady, Log, RunPhase, redact_text
from rook.engine.pathguard import GuardReport, PathGuard, Snapshot, check_allowed_paths
from rook.engine.testrunner import TestRun, TestRunner, parse_command
from rook.engine.verifier import Verifier, VerifyResult
from rook.export.counterexample import Counterexample, publish_saved, rule_only_model
from rook.export.tests import TEST_DIR, fallback_test_name, prompt_view, write_fallback_test
from rook.model.schema import RookModel
from rook.sandbox.base import Sandbox

MAX_ROUNDS = rails.MAX_RETRIES
FILE_MAX_CHARS = 30_000
REASON_MAX_CHARS = 1_000
ISSUES_MAX = 10

# The native regression test's file name per source language (Rook picks it, never Bob).
_NATIVE_NAMES = {
    ".py": "test_rook_{cx}.py",
    ".js": "rook_{cx}.test.js", ".mjs": "rook_{cx}.test.mjs", ".cjs": "rook_{cx}.test.cjs",
    ".jsx": "rook_{cx}.test.jsx", ".ts": "rook_{cx}.test.ts", ".tsx": "rook_{cx}.test.tsx",
    ".go": "rook_{cx}_test.go",
}
_LANGUAGE_SUFFIX = {"python": ".py", "javascript": ".js", "typescript": ".ts", "go": ".go"}
Outcome = Literal["approved", "rejected", "guard", "no_change", "failed"]
_ERRORS = re.compile(r"\b\d+ errors?\b")
# Run-specific text an earlier round's reason may quote: a missing recording's key and folder, and local paths.
_MISSING_RECORDING = re.compile(r"no recording for key [0-9a-f]+ in \S+")
_LOCAL_PATH = re.compile(r"(?:/home|/Users|/root)/[^\s\"':,)]+")


class FixNotApproved(PermissionError):
    """The FIX phase was asked to run without an approved "fix" question (rails, 02 section 4)."""


def require_fix_approval(state: rails.RunState) -> None:
    why = rails.check_step(state, "fix")
    if why is not None:
        raise FixNotApproved(f"the Surgeon may not change the app: {why}")


# --- running tests next to the app ---


class TestHarness(Protocol):
    """Runs tests next to the app. `SandboxHarness` is the real one; tests may supply their own."""

    def can_run_native(self) -> bool: ...
    async def run_native(self, test_path: str) -> TestRun: ...
    async def run_fallback(self, test_file: Path) -> TestRun: ...
    async def run_project(self) -> TestRun | None: ...
    async def reload(self) -> None: ...


# Not a pytest test class. Set outside the body: a Protocol attribute would become a protocol member.
TestHarness.__test__ = False  # type: ignore[attr-defined]


class SandboxHarness:
    """The sandbox's view: the project's test command (from the Scout) runs the native test with its
    path appended; the fallback test replays over HTTP against the sandbox; `reload` restarts the app so
    it serves the patched code."""

    __test__ = False

    def __init__(self, sandbox: Sandbox, runner: TestRunner, *, base_url: str,
                 test_command: str | Sequence[str] | None, env: Mapping[str, str] | None = None,
                 timeout: float = 600.0) -> None:
        self.sandbox = sandbox
        self.runner = runner
        self.base_url = base_url
        self.command = parse_command(test_command) if test_command else None
        self.env = dict(env or {})
        self.timeout = timeout

    def can_run_native(self) -> bool:
        return self.command is not None

    async def run_native(self, test_path: str) -> TestRun:
        assert self.command is not None
        return await self.runner.run_in_sandbox(self.sandbox, [*self.command, test_path],
                                                label=f"regression test {test_path}", timeout=self.timeout)

    async def run_fallback(self, test_file: Path) -> TestRun:
        return await self.runner.run_fallback(test_file, self.base_url, self.env)

    async def run_project(self) -> TestRun | None:
        if self.command is None:
            return None
        return await self.runner.run_in_sandbox(self.sandbox, self.command, timeout=self.timeout)

    async def reload(self) -> None:
        self.base_url = await asyncio.to_thread(self.sandbox.restart)


def native_test_path(workspace: Path, cx_id: str, source_file: str | None,
                     language: str | None = None) -> str | None:
    """Where the native regression test goes: next to the project's existing tests of the same language
    (the shallowest such folder), else the workspace root; Go tests sit next to the diagnosed file.
    None when Rook knows no native test layout for the language, or the file already exists."""
    suffix = PurePosixPath(source_file).suffix if source_file else ""
    if suffix not in _NATIVE_NAMES:
        suffix = _LANGUAGE_SUFFIX.get((language or "").strip().lower(), "")
    if suffix not in _NATIVE_NAMES:
        return None
    name = _NATIVE_NAMES[suffix].format(cx=cx_id)
    root = workspace.resolve()
    if suffix == ".go":
        if not source_file:
            return None
        folder = PurePosixPath(source_file).parent
    else:
        test_dirs = sorted(
            {PurePosixPath(p.relative_to(root).as_posix()).parent for p in _source_files(root)
             if p.suffix == suffix and _is_test(p.relative_to(root).as_posix())},
            key=lambda d: (len(d.parts), str(d)),
        )
        folder = test_dirs[0] if test_dirs else PurePosixPath(".")
    rel = (folder / name).as_posix()
    return None if os.path.lexists(root / rel) else rel


def fails_as_expected(run: TestRun) -> tuple[bool, str]:
    """A native regression test is accepted only if it fails cleanly on the buggy app: exit code 1
    (tests failed) and no errors. Exit 0 = it passes; other codes = collection/usage errors, no tests,
    a timeout or a command that could not run."""
    if run.exit_code == 0:
        return False, f"it passes on the buggy app ({run.summary})"
    if run.exit_code != 1:
        return False, f"it did not run cleanly ({run.summary})"
    if _ERRORS.search(run.summary) or _ERRORS.search(run.output):
        return False, f"it errors instead of failing an assertion ({run.summary})"
    return True, f"it fails on the buggy app ({run.summary})"


# --- results ---


@dataclass(frozen=True)
class RegressionTest:
    cx_id: str
    kind: Literal["native", "fallback"]
    path: str  # workspace-relative
    reason: str  # why the native test was accepted, or why the fallback is used
    run: TestRun | None = None  # the native test's run on the buggy app


@dataclass(frozen=True)
class FixRound:
    number: int
    outcome: Outcome
    reason: str
    files: list[str]  # the allowed files the round changed
    reverted: list[str]  # paths the path guard reverted


@dataclass
class FixResult:
    cx_id: str
    applied: bool  # True only when the Fix Reviewer approved the patch (it stays in the workspace)
    files: list[str]
    diff: str
    summary: str
    rounds: list[FixRound] = field(default_factory=list)


@dataclass
class FixOutcome:
    regression: RegressionTest
    fix: FixResult
    verification: VerifyResult | None

    @property
    def verified(self) -> bool:
        return self.verification is not None and self.verification.verified


# --- the pipeline ---


@dataclass(frozen=True)
class _SurgeonCall:
    output: SurgeonOutput | None
    error: str
    snap: Snapshot  # the workspace just before the call
    key: str  # its recording key (names the edit tape)


def _read(path: Path) -> str:
    text = path.read_bytes().decode("utf-8", errors="replace")
    if len(text) > FILE_MAX_CHARS:
        return text[:FILE_MAX_CHARS] + f"\n[truncated by Rook at {FILE_MAX_CHARS} characters]\n"
    return text


def _clip(text: str, limit: int = REASON_MAX_CHARS) -> str:
    text = redact_text(text.strip())
    return text if len(text) <= limit else text[:limit] + "..."


class FixPipeline:
    def __init__(self, client: AgentCaller, workspace: str | os.PathLike[str], *,
                 max_rounds: int = MAX_ROUNDS) -> None:
        """`workspace` is the run's copy of the target: the only place the Surgeon ever edits."""
        self.client = client
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")
        check_not_rook_repo(self.workspace)
        self.guard = PathGuard(self.workspace)
        self.max_rounds = max_rounds

    async def run(self, state: rails.RunState, model: RookModel, cx: Counterexample,
                  diagnosis: DiagnosisResult, harness: TestHarness, verifier: Verifier, *,
                  language: str | None = None) -> FixOutcome:
        """Regression test, FIX and VERIFY in order. Refused before any edit unless the fix is approved."""
        require_fix_approval(state)
        regression = await self.regression_test(model, cx, harness, diagnosis, language=language)
        fixed = await self.fix(state, model, cx, diagnosis, regression)
        verification = await self.verify(cx, regression, harness, verifier) if fixed.applied else None
        return FixOutcome(regression, fixed, verification)

    # --- 1. the regression test ---

    async def regression_test(self, model: RookModel, cx: Counterexample, harness: TestHarness,
                              diagnosis: DiagnosisResult | None = None, *,
                              language: str | None = None) -> RegressionTest:
        source = diagnosis.file if diagnosis and diagnosis.file else None
        path = native_test_path(self.workspace, cx.cx_id, source, language)
        if path is None:
            result = await self._fallback(model, cx, "Rook knows no native test layout for this project")
        elif not harness.can_run_native():
            result = await self._fallback(model, cx, "the project has no test command to run a native test")
        else:
            result = await self._native(model, cx, harness, diagnosis, path)
        await publish_saved(self.client.bus, self.client.run_id, cx, result.path)
        return result

    async def _native(self, model: RookModel, cx: Counterexample, harness: TestHarness,
                      diagnosis: DiagnosisResult | None, path: str) -> RegressionTest:
        try:
            allowed = check_allowed_paths(self.workspace, [path])
        except ValueError as exc:
            return await self._fallback(model, cx, f"the native test path is not usable: {exc}")
        files = self._files([source] if (source := diagnosis.file if diagnosis else "") else [])
        if sample := self._sample_test(path):
            files[f"{sample} (an existing test, for style)"] = _read(self.workspace / sample)
        task = (f"Write ONE new regression test file at {path} in the project's own test framework and "
                "style. It must reproduce the counterexample's steps against the app's code and assert "
                "the broken rule, so it FAILS on the current (buggy) code and passes once the diagnosed "
                "bug is fixed. Do not fix the bug and do not change any other file.")
        call = await self._surgeon(task, allowed, model, cx, diagnosis, files, "")
        error, snap = call.error, call.snap
        try:
            report = self._enforce(call, allowed)
            problem = error or (f"the call changed paths it may not: {report.reason()}" if not report.ok
                                else "")
            written = self.workspace / path
            if not problem and not (written.is_file() and not written.is_symlink() and written.stat().st_size):
                problem = f"the Surgeon did not write {path}"
            if not problem:
                run = await harness.run_native(path)
                accepted, why = fails_as_expected(run)
                if accepted:
                    await self._log("info", f"Native regression test {path}: {why}; accepted")
                    return RegressionTest(cx.cx_id, "native", path, why, run)
                problem = f"the native test {path} was not usable: {why}"
            self.guard.restore(snap)
        finally:
            snap.close()
            write_modes(self.workspace)  # the Surgeon is read-only again
        return await self._fallback(model, cx, problem)

    async def _fallback(self, model: RookModel, cx: Counterexample, why: str) -> RegressionTest:
        rel = (TEST_DIR / fallback_test_name(cx.cx_id)).as_posix()
        try:
            await asyncio.to_thread(write_fallback_test, self.workspace, cx, model)
        except FileExistsError:
            pass  # written earlier for this counterexample; the runner checks it against the template
        reason = f"using the generated HTTP-level test {rel} because {why}"
        await self._log("warn", f"Regression test: {reason}")
        return RegressionTest(cx.cx_id, "fallback", rel, reason)

    def _sample_test(self, test_path: str) -> str | None:
        suffix = PurePosixPath(test_path).suffix
        for p in _source_files(self.workspace):
            rel = p.relative_to(self.workspace).as_posix()
            if p.suffix == suffix and _is_test(rel) and rel != test_path:
                return rel
        return None

    # --- 2. the fix ---

    async def fix(self, state: rails.RunState, model: RookModel, cx: Counterexample,
                  diagnosis: DiagnosisResult, regression: RegressionTest, *,
                  announce: bool = True) -> FixResult:
        """`announce=False` when the caller already published the FIX phase (e.g. before the regression
        test)."""
        require_fix_approval(state)
        if announce:
            await self._publish("run.phase", RunPhase(phase="FIX"))
        if not diagnosis.file:
            raise ValueError("there is no diagnosis to fix")
        checked = await asyncio.to_thread(check_diagnosis, self.workspace, Diagnosis(
            file=diagnosis.file, line=diagnosis.line or 1, explanation=diagnosis.explanation or "-",
            evidence=diagnosis.evidence))
        allowed = check_allowed_paths(self.workspace, [checked.file])
        files = self._files([checked.file])
        test = _read(self.workspace / regression.path)
        if regression.kind == "fallback":  # generated by Rook: show it without the run's time and seed
            test = prompt_view(test, cx.cx_id, Masker().value)
        files[f"{regression.path} (the regression test: read only)"] = test
        task = (f"Fix the diagnosed bug in {checked.file} with the smallest correct change. The regression "
                f"test {regression.path} fails on the current code and must pass after your fix; do not "
                "edit it or any test.")
        rounds: list[FixRound] = []
        try:
            for number in range(1, self.max_rounds + 1):
                round_, diff, summary = await self._fix_round(number, task, allowed, model, cx, diagnosis,
                                                              files, rounds)
                rounds.append(round_)
                if round_.outcome == "approved":
                    await self._publish("fix.ready", FixReady(cx_id=cx.cx_id, files=round_.files, diff=diff,
                                                              reviewed=True))
                    return FixResult(cx.cx_id, True, round_.files, diff, summary, rounds)
                await self._log("warn", f"Fix round {number}/{self.max_rounds} not approved "
                                        f"({round_.outcome}): {round_.reason}")
        finally:
            write_modes(self.workspace)
        await self._log("error", f"No fix was approved in {len(rounds)} rounds; the workspace is unchanged. "
                                 f"Last problem: {rounds[-1].reason}")
        return FixResult(cx.cx_id, False, [], "", f"no approved fix after {len(rounds)} rounds", rounds)

    async def _fix_round(self, number: int, task: str, allowed: list[str], model: RookModel,
                         cx: Counterexample, diagnosis: DiagnosisResult, files: dict[str, str],
                         history: list[FixRound]) -> tuple[FixRound, str, str]:
        call = await self._surgeon(task, allowed, model, cx, diagnosis, files, _feedback(history, self.workspace))
        output, error, snap = call.output, call.error, call.snap
        try:
            report = self._enforce(call, allowed)
            changed = [c.path for c in report.allowed]
            problem = self._judge_call(error, report, changed)
            diff = ""
            if problem is None:
                diff = self.guard.diff(snap, changed)
                problem = await self._review(diff, cx, diagnosis)
            outcome, reason = problem
            if outcome != "approved":
                self.guard.restore(snap)
            summary = _clip(output.summary) if output else ""
            return FixRound(number, outcome, reason, changed, report.reverted), diff, summary
        finally:
            snap.close()

    @staticmethod
    def _judge_call(error: str, report: GuardReport, changed: list[str]) -> tuple[Outcome, str] | None:
        """Why the engine rejects the round before any review, or None."""
        if error:
            return "failed", error
        if not report.ok:
            return "guard", f"changes outside the allowed files were reverted: {report.reason()}"
        if not changed:
            return "no_change", "the Surgeon did not change the allowed file"
        return None

    async def _review(self, diff: str, cx: Counterexample, diagnosis: DiagnosisResult
                      ) -> tuple[Outcome, str]:
        try:
            result = await call_agent(self.client, "fix_reviewer", self.workspace, diff=diff,
                                      diagnosis=_diagnosis_input(diagnosis), rules=[_rule_input(cx)])
        except BOB_FAILURES as exc:
            return "failed", _clip(f"the Fix Reviewer gave no valid answer: {exc}")
        review = result.output
        assert isinstance(review, FixReviewOutput)
        issues = [_clip(i, 300) for i in review.issues[:ISSUES_MAX] if i.strip()]
        if review.verdict == "approve":
            return "approved", "; ".join(issues) or "approved by the Fix Reviewer"
        return "rejected", "; ".join(issues) or "rejected by the Fix Reviewer (no issues given)"

    # --- 3. verification ---

    async def verify(self, cx: Counterexample, regression: RegressionTest, harness: TestHarness,
                     verifier: Verifier) -> VerifyResult:
        await self._publish("run.phase", RunPhase(phase="VERIFY"))
        await harness.reload()

        async def regression_check() -> TestRun:
            if regression.kind == "native":
                return await harness.run_native(regression.path)
            return await harness.run_fallback(self.workspace / regression.path)

        project: Callable[[], Awaitable[TestRun]] | None = None
        if harness.can_run_native():
            async def project_check() -> TestRun:
                run = await harness.run_project()
                assert run is not None
                return run
            project = project_check
        return await verifier.verify(cx, regression_test=regression_check, project_tests=project)

    # --- the Surgeon call ---

    def _files(self, paths: list[str]) -> dict[str, str]:
        return {p: _read(self.workspace / p) for p in paths if (self.workspace / p).is_file()}

    async def _surgeon(self, task: str, allowed: list[str], model: RookModel, cx: Counterexample,
                       diagnosis: DiagnosisResult | None, files: dict[str, str], feedback: str
                       ) -> _SurgeonCall:
        """One Surgeon call with edit rights on `allowed` only. In replay mode the call's taped edits are
        written back first, so a replayed call meets the same guard (`_enforce`) as the live one."""
        write_modes(self.workspace, surgeon_paths=allowed)
        spec = get("surgeon")
        prompt = render_prompt("surgeon", task=task, diagnosis=_diagnosis_input(diagnosis),
                               counterexample=_cx_input(model, cx), allowed_paths=allowed, files=files,
                               feedback=feedback)
        key = recording_key(spec.slug, prompt)
        snap = await asyncio.to_thread(self.guard.snapshot)
        output: SurgeonOutput | None = None
        error = ""
        try:
            try:
                result = await self.client.call("surgeon", spec.slug, prompt, self.workspace,
                                                spec.output_model, max_turns=spec.max_turns)
                assert isinstance(result.output, SurgeonOutput)
                output = result.output
            except BOB_FAILURES as exc:
                error = _clip(f"the Surgeon gave no valid answer: {exc}")
            if edit_tape.tape_mode(self.client) == "replay" and output is not None:
                edit_tape.apply(self.workspace, edit_tape.load(edit_tape.tape_path(self.client, key)))
        except BaseException:
            self.guard.restore(snap)
            snap.close()
            raise
        return _SurgeonCall(output, error, snap, key)

    def _enforce(self, call: _SurgeonCall, allowed: list[str]) -> GuardReport:
        """Run the path guard on a Surgeon call; in record mode, then tape what the guard let through.

        The tape is written only after the guard, from its report: the allowed changes verbatim, and the
        rejected ones by path only (never their content, which may hold a target-app secret). Replaying
        a withheld path writes a fixed placeholder (or deletes it), so the replayed guard rejects the
        round just as the live one did."""
        report = self.guard.enforce(call.snap, allowed)
        if edit_tape.tape_mode(self.client) == "record" and call.output is not None and report.changes:
            rejected = [c.path for c in report.violations]
            # A rejected folder is implied by the rejected paths below it (replay creates it for them).
            withheld: dict[str, str] = {c.path: "deleted" if c.path in allowed else c.kind for c in report.violations
                        if not any(p.startswith(c.path + "/") for p in rejected)}
            approved: dict[str, str] = {c.path: c.kind for c in report.allowed}
            edit_tape.save(edit_tape.tape_path(self.client, call.key), self.workspace, approved, withheld)
        return report

    async def _log(self, level: str, text: str) -> None:
        await self._publish("log", Log(level=level, text=redact_text(text)))  # type: ignore[arg-type]

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.client.bus.publish(self.client.run_id, event_type, data)


def _diagnosis_input(diagnosis: DiagnosisResult | None) -> dict[str, Any]:
    if diagnosis is None or not diagnosis.file:
        return {}
    return {"file": diagnosis.file, "line": diagnosis.line, "explanation": diagnosis.explanation,
            "evidence": list(diagnosis.evidence), "reviewed": diagnosis.reviewed}


def _cx_input(model: RookModel, cx: Counterexample) -> dict[str, Any]:
    """The counterexample and the model's HTTP actions, actors and state readers it needs (no rules
    other than the broken one; env values stay placeholders)."""
    restricted = rule_only_model(model, cx).model_dump(mode="json", by_alias=True, exclude_none=True)
    return {"cx_id": cx.cx_id, "rule": _rule_input(cx), "steps": _steps_input(cx), "model": restricted}


def _feedback(history: list[FixRound], workspace: Path) -> str:
    """What went wrong in earlier rounds, for the Surgeon's next try ("" in the first round).

    It is part of the next prompt, so of its recording key: run-specific text in a reason (the workspace
    path, a missing recording's key and folder, temp and home paths, times, random words) is masked, so the
    same rounds give the same prompt on every run and machine."""
    text = "\n\n".join(
        f"Round {r.number}: {r.outcome}. {r.reason}" + (f"\nFiles you changed: {', '.join(r.files)}"
                                                         if r.files else "")
        for r in history
    )
    text = _MISSING_RECORDING.sub("no recording for this call", text.replace(str(workspace), "/workspace"))
    return mask_text(_LOCAL_PATH.sub("<path>", text))

