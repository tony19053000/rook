"""The Understand pipeline: SCOUT -> START_APP -> MAP (02_ARCHITECTURE.md section 4).

Bob proposes and code decides (CLAUDE.md rule 1):
- the Scout summarises the workspace; paths it names are kept only if they are real files inside it;
- the Mechanic proposes a SandboxPlan; the sandbox's health check decides whether it works. Up to 3
  attempts, each failure's logs going back to the Mechanic. Missing `env_required` values are asked
  from the user (`question.asked` kind `setup_value`) through the injected `answer` callback;
- the Mapper proposes actors, actions and state readers; the rook.yaml schema validates them and the
  engine dry-run (engine/dryrun.py) decides whether each action works. Up to 3 attempts, each failure's
  HTTP errors going back to the Mapper. Actions that still fail are disabled (02 section 16).

Everything Bob returns is untrusted data (03 section 4): it is only validated and used as data, never
executed. Bob always runs with cwd = the run's workspace copy, never the Rook repo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import ValidationError

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.modes import write_modes
from rook.agents.schemas import MapperOutput, SandboxPlan
from rook.agents.volatile import mask_text
from rook.core import rails
from rook.core.events import (
    EngineFinished,
    EngineStarted,
    Log,
    ModelActions,
    Phase,
    QuestionAnswered,
    QuestionAsked,
    RepoSummary,
    RunPhase,
    SandboxReady,
    redact_text,
    register_secret,
)
from rook.engine.dryrun import DryRunReport, dry_run
from rook.model.loader import ModelError, load_model_str
from rook.model.schema import RookModel
from rook.sandbox.allowlist import check_env_name
from rook.sandbox.base import Sandbox, SandboxError
from rook.sandbox.docker import DEFAULT_LIMITS, DockerSandbox, Limits, base_image_for

MAX_ATTEMPTS = rails.MAX_RETRIES
MODEL_PATH = Path("rook") / "rook.yaml"

# Workspace walking: folders that are never part of the app's source.
SKIP_DIRS = frozenset({
    ".git", ".bob", ".rook", ".rook-sandbox", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build", ".next",
})
# Build and manifest files shown to the Mechanic (at the workspace root).
MANIFESTS = (
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "package.json", "go.mod", "Gemfile", "Cargo.toml", "Makefile", "Procfile", ".env.example",
    "README.md",
)
DIGEST_MAX_FILES = 400
FILE_MAX_CHARS = 20_000
FILES_MAX_TOTAL = 120_000
LOGS_MAX_CHARS = 4_000
_HASH_MAX_BYTES = 5_000_000


class UnderstandError(RuntimeError):
    """A phase could not finish (after its retries). `phase` says which one."""

    def __init__(self, phase: Phase, message: str) -> None:
        self.phase = phase
        super().__init__(f"{phase}: {message}")


@dataclass
class StartedApp:
    sandbox: Sandbox
    base_url: str
    # An in-process transport (tests); None means real HTTP to `base_url`.
    transport: httpx.AsyncBaseTransport | None = None


# (plan, values for plan.env_required, summary) -> a started app. Synchronous; runs in a thread.
# Raises SandboxError (or ValueError for a bad plan) with the logs if the app does not start.
Launcher = Callable[[SandboxPlan, Mapping[str, str], RepoSummary], StartedApp]
# Gets a `setup_value` question and returns the value (None or "" if the user gives none).
SetupAnswerer = Callable[[QuestionAsked], Awaitable[str | None]]


def docker_launcher(workspace: str | os.PathLike[str], run_id: str, *, access_network: str | None = None,
                    limits: Limits = DEFAULT_LIMITS) -> Launcher:
    """A DockerSandbox built from the Mechanic's plan (02 section 8): the local CLI's launcher, and the hosted
    server's for a signed-in user's GitHub repo (`access_network` and `limits` from trusted server config)."""

    def launch(plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
        sandbox = DockerSandbox(Path(workspace), run_id=run_id, env=values,
                                base_image=base_image_for(summary.language), access_network=access_network,
                                limits=limits)
        return StartedApp(sandbox=sandbox, base_url=sandbox.start(plan))  # start() cleans up on failure

    return launch


@dataclass
class Understanding:
    summary: RepoSummary
    plan: SandboxPlan
    app: StartedApp
    # The app's env as the engine sees it (`{{env.X}}`): plan defaults plus setup values. Holds
    # user-provided secrets: never log or publish it.
    env: dict[str, str]
    model: RookModel
    dry_run: DryRunReport
    model_path: Path
    disabled: list[str] = field(default_factory=list)  # actions/readers removed after 3 failed dry-runs


# --- workspace reading (every path from Bob is confined to the workspace) ---


def safe_file(workspace: Path, rel: str) -> Path | None:
    """The real file `rel` inside `workspace`, or None if it is outside, hidden from Bob, or not a file."""
    if not isinstance(rel, str) or not rel or any(ord(c) < 0x20 or ord(c) == 0x7F for c in rel):
        return None
    if Path(rel).is_absolute() or "\\" in rel:
        return None
    root = workspace.resolve()
    try:
        path = (root / rel).resolve()
        rel_path = path.relative_to(root)
    except (OSError, ValueError):
        return None
    if any(part in (".git", ".bob") for part in rel_path.parts) or not path.is_file():
        return None
    return path


def _read_text(path: Path, limit: int = FILE_MAX_CHARS) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        text = fh.read(limit + 1)
    return text if len(text) <= limit else text[:limit] + "\n[truncated by Rook]"


def _walk(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(workspace):  # never follows symlinked folders
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_symlink() and path.is_file():
                files.append(path)
    return sorted(files, key=lambda p: p.relative_to(workspace).as_posix())


def workspace_digest(workspace: str | os.PathLike[str]) -> str:
    """A deterministic listing of the workspace: path, size and content hash of each file.

    It never contains the workspace's absolute path, so recordings replay from any copy of the repo."""
    root = Path(workspace).resolve()
    files = _walk(root)
    lines = [f"{len(files)} files"]
    for path in files[:DIGEST_MAX_FILES]:
        size = path.stat().st_size
        if size > _HASH_MAX_BYTES:
            digest = "large"
        else:
            digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        lines.append(f"{path.relative_to(root).as_posix()}  {size} bytes  {digest}")
    if len(files) > DIGEST_MAX_FILES:
        lines.append(f"... and {len(files) - DIGEST_MAX_FILES} more files")
    return "\n".join(lines)


def read_files(workspace: Path, rels: list[str]) -> dict[str, str]:
    """Read the given workspace files (confined, capped per file and in total)."""
    out: dict[str, str] = {}
    total = 0
    for rel in sorted(dict.fromkeys(rels)):
        path = safe_file(workspace, rel)
        if path is None:
            continue
        text = _read_text(path)
        if "\x00" in text:  # a binary file (an image in docs/): no use to Bob, and argv can't carry NUL
            continue
        if total + len(text) > FILES_MAX_TOTAL:
            break
        out[path.relative_to(workspace.resolve()).as_posix()] = text
        total += len(text)
    return out


def manifest_files(workspace: Path) -> dict[str, str]:
    return read_files(workspace, list(MANIFESTS))


def mapper_files(workspace: Path, summary: RepoSummary) -> dict[str, str]:
    rels = [*summary.routes_files, *summary.models_files]
    return read_files(workspace, rels or list(summary.entrypoints))


def clean_summary(workspace: Path, summary: RepoSummary) -> tuple[RepoSummary, list[str]]:
    """Keep only file paths that are real files inside the workspace. Returns (summary, dropped paths)."""
    dropped: list[str] = []

    def keep(paths: list[str]) -> list[str]:
        kept = []
        for p in paths:
            (kept if safe_file(workspace, p) is not None else dropped).append(p)
        return kept

    cleaned = summary.model_copy(update={
        "entrypoints": keep(summary.entrypoints),
        "routes_files": keep(summary.routes_files),
        "models_files": keep(summary.models_files),
    })
    return cleaned, sorted(set(dropped))


# --- the model ---


def build_model(output: MapperOutput, plan: SandboxPlan) -> RookModel:
    """The Mapper's parts plus the app section, validated as rook.yaml. Raises ModelError."""
    data: dict[str, Any] = {
        "version": 1,
        "app": {
            "base_url": "{{sandbox.base_url}}",
            "health": {"method": "GET", "path": plan.health_path, "expect_status": 200},
            "isolation": "fresh_entities",
        },
        **output.to_model_parts(),
    }
    text = yaml.safe_dump(json.loads(json.dumps(data)), sort_keys=False, allow_unicode=True)
    model = load_model_str(text, source="Mapper output")
    captured = {var for action in model.actions for var in action.capture}
    issues = [f"actions.{a.name}.requires: {var!r} is not captured by any action"
              for a in model.actions for var in a.requires if var not in captured]
    issues += [f"state.{r.name}.each: {r.each!r} is not captured by any action"
               for r in model.state if r.each not in captured]
    if issues:
        raise ModelError("Mapper output", issues)
    return model


MAPPER_NOTE = "Written by Rook (Mapper), checked by an engine dry-run. Review before approving."


def model_yaml(model: RookModel, note: str = MAPPER_NOTE) -> str:
    data = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    return f"# {note}\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def write_model(workspace: Path, model: RookModel, note: str = MAPPER_NOTE) -> Path:
    path = workspace / MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = model_yaml(model, note)
    load_model_str(text, source=str(path))  # what we write must load back
    path.write_text(text, encoding="utf-8")
    return path


def disable_failed(model: RookModel, report: DryRunReport) -> tuple[RookModel, list[str]]:
    """Remove failed actions and readers, then anything left without a producer for its vars."""
    actions = [a for a in model.actions if a.name not in report.failed_actions]
    while True:
        captured = {var for a in actions for var in a.capture}
        kept = [a for a in actions if set(a.requires) <= captured]
        if len(kept) == len(actions):
            break
        actions = kept
    captured = {var for a in actions for var in a.capture}
    readers = [r for r in model.state if r.name not in report.failed_readers and r.each in captured]
    disabled = [a.name for a in model.actions if a not in actions]
    disabled += [f"state:{r.name}" for r in model.state if r not in readers]
    if not actions:
        raise UnderstandError("MAP", "no action dry-ran OK")
    data = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    data["actions"] = [a.model_dump(mode="json", by_alias=True, exclude_none=True) for a in actions]
    data["state"] = [r.model_dump(mode="json", by_alias=True, exclude_none=True) for r in readers]
    return RookModel.model_validate(data), disabled


def _mapper_feedback(output: MapperOutput, problems: str) -> str:
    previous = json.dumps(output.to_model_parts(), sort_keys=True, indent=2, ensure_ascii=False)
    return f"{problems}\n\nYour last model was:\n{previous}"


def _tail(text: str, limit: int = LOGS_MAX_CHARS) -> str:
    text = redact_text(text)
    return text if len(text) <= limit else "...\n" + text[-limit:]


# --- the pipeline ---


def check_not_rook_repo(workspace: Path) -> None:
    """Bob must run in the run's copy of the target, never in (or above) Rook's own source."""
    package = Path(__file__).resolve().parents[1]  # .../rook
    repo = package.parents[1]  # the checkout root when running from source (src/rook)
    from_source = (repo / "src" / "rook").resolve() == package
    if package.is_relative_to(workspace) or (from_source and workspace.is_relative_to(repo)):
        raise ValueError(f"refusing to run agents in Rook's own repo: {workspace}")


class UnderstandPipeline:
    def __init__(
        self,
        client: AgentCaller,
        workspace: str | os.PathLike[str],
        *,
        answer: SetupAnswerer,
        launcher: Launcher | None = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        """`workspace` is the run's copy of the target (Bob runs there and may write `.rook-sandbox/`)."""
        self.client = client
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")
        check_not_rook_repo(self.workspace)
        self.answer = answer
        self.launcher = launcher or docker_launcher(self.workspace, client.run_id)
        self.max_attempts = max_attempts

    async def run(self) -> Understanding:
        write_modes(self.workspace)
        summary = await self.scout()
        plan, app, env = await self.start_app(summary)
        try:
            model, report, disabled = await self.map(summary, plan, app, env)
            path = write_model(self.workspace, model)
        except BaseException:
            await asyncio.to_thread(app.sandbox.stop)
            raise
        await self._log("info", f"Wrote {MODEL_PATH.as_posix()}: {report.summary()}")
        return Understanding(summary=summary, plan=plan, app=app, env=env, model=model, dry_run=report,
                             model_path=path, disabled=disabled)

    # SCOUT

    async def scout(self) -> RepoSummary:
        await self._publish("run.phase", RunPhase(phase="SCOUT"))
        try:
            result = await call_agent(self.client, "scout", self.workspace,
                                      workspace_digest=workspace_digest(self.workspace))
        except BOB_FAILURES as exc:
            raise UnderstandError("SCOUT", f"the Scout failed: {exc}") from exc
        output = result.output
        assert isinstance(output, RepoSummary)
        summary, dropped = clean_summary(self.workspace, output)
        if dropped:
            await self._log("warn", f"Scout named paths that are not files in the repo: {', '.join(dropped)}")
        await self._publish("repo.summary", summary)
        return summary

    # START_APP

    async def start_app(self, summary: RepoSummary) -> tuple[SandboxPlan, StartedApp, dict[str, str]]:
        await self._publish("run.phase", RunPhase(phase="START_APP"))
        files = manifest_files(self.workspace)
        values: dict[str, str] = {}
        logs = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await call_agent(self.client, "mechanic", self.workspace,
                                          summary=summary, files=files, logs=logs)
            except BOB_FAILURES as exc:
                raise UnderstandError("START_APP", f"the Mechanic failed: {exc}") from exc
            plan = result.output
            assert isinstance(plan, SandboxPlan)
            try:
                for name in plan.env_required:
                    check_env_name(name)
                await self._ask_missing(plan, values)
                needed = {name: values[name] for name in plan.env_required}
                app = await asyncio.to_thread(self.launcher, plan, needed, summary)
            except (SandboxError, ValueError, OSError) as exc:
                logs = _tail(f"Attempt {attempt} with plan {plan.model_dump_json()} failed:\n"
                             f"{mask_text(str(exc))}")
                await self._log("warn", f"The app did not start (attempt {attempt}/{self.max_attempts}): "
                                        f"{redact_text(str(exc)).splitlines()[0] if str(exc) else 'error'}")
                continue
            await self._publish("sandbox.ready", SandboxReady(base_url_redacted=redact_text(app.base_url),
                                                              mode=plan.mode))
            return plan, app, {**plan.env_defaults, **needed}
        raise UnderstandError("START_APP", f"the app did not start after {self.max_attempts} attempts")

    async def _ask_missing(self, plan: SandboxPlan, values: dict[str, str]) -> None:
        for name in plan.env_required:
            if name in values:
                continue
            question = QuestionAsked(
                question_id=f"q_{uuid.uuid4().hex[:10]}",
                kind="setup_value",
                text=f"Your app needs {name}. Enter a value for the sandbox (it is never logged).",
                options=[],
                payload={"name": name, "secret": True},
            )
            await self._publish("question.asked", question)
            value = await self.answer(question)
            if not value:
                raise UnderstandError("START_APP", f"no value was given for {name}")
            register_secret(value)  # scrubbed from every event, log and recording from now on
            values[name] = value
            await self._publish("question.answered", QuestionAnswered(
                question_id=question.question_id, answer={"name": name, "provided": True}, by="user"))

    # MAP

    async def map(
        self, summary: RepoSummary, plan: SandboxPlan, app: StartedApp, env: dict[str, str]
    ) -> tuple[RookModel, DryRunReport, list[str]]:
        await self._publish("run.phase", RunPhase(phase="MAP"))
        files = mapper_files(self.workspace, summary)
        env_names = sorted(env)
        feedback = ""
        last: tuple[RookModel, DryRunReport] | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = await call_agent(self.client, "mapper", self.workspace, summary=summary, files=files,
                                          logs=feedback, env_names=env_names)
            except BOB_FAILURES as exc:
                raise UnderstandError("MAP", f"the Mapper failed: {exc}") from exc
            output = result.output
            assert isinstance(output, MapperOutput)
            try:
                model = build_model(output, plan)
            except (ModelError, ValidationError) as exc:
                problems = "\n".join(exc.errors) if isinstance(exc, ModelError) else str(exc)
                feedback = _tail(_mapper_feedback(output, f"The model is invalid:\n{problems}"), 12_000)
                await self._log("warn", f"The Mapper's model is invalid (attempt {attempt}/{self.max_attempts})")
                continue
            await self._publish("model.actions", ModelActions(**output.to_model_parts()))
            report = await self._dry_run(model, app, env)
            if report.ok:
                return model, report, []
            last = (model, report)
            feedback = _tail(_mapper_feedback(output, f"Dry-run failures:\n{mask_text(report.failures())}"),
                             12_000)
        if last is None:
            raise UnderstandError("MAP", f"no valid model after {self.max_attempts} attempts")
        model, disabled = disable_failed(*last)
        await self._log("warn", f"Disabled after {self.max_attempts} failed dry-runs: {', '.join(disabled)}")
        report = await self._dry_run(model, app, env)
        return model, report, disabled

    async def _dry_run(self, model: RookModel, app: StartedApp, env: dict[str, str]) -> DryRunReport:
        await self._publish("engine.started", EngineStarted(
            worker="runner", label=f"Dry-running {len(model.actions)} actions"))
        report = await dry_run(model, app.base_url, env=env, transport=app.transport)
        for check in [*report.actions.values(), *report.readers.values()]:
            if not check.ok:
                await self._log("warn", f"dry-run {check.name}: {check.detail}")
        await self._publish("engine.finished", EngineFinished(worker="runner", ok=report.ok,
                                                              summary=report.summary()))
        return report

    # events

    async def _log(self, level: str, text: str) -> None:
        await self._publish("log", Log(level=level, text=text))  # type: ignore[arg-type]

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.client.bus.publish(self.client.run_id, event_type, data)
