"""ROOK-017: the Scout -> Mechanic -> Mapper pipeline, with engine dry-runs deciding pass/fail.

The default suite uses scripted fakes and a committed replay of a real Bob run on minishop (served
in-process). The live run (`-m bob`, which also needs Docker) re-records it when ROOK_RECORD_DIR is set:

    source ~/.bob-key.env
    ROOK_RECORD_DIR=tests/fixtures/recordings/understand_minishop \
        uv run pytest -m bob tests/unit/test_pipeline_understand.py
"""

import asyncio
import importlib.util
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest import mock

import httpx
import pytest
from pydantic import BaseModel

from rook.agents.bob import AgentOutputError, AgentResult, BobClient
from rook.agents.schemas import MapperOutput, RepoSummary, SandboxPlan, example_for
from rook.agents.understand import (
    StartedApp,
    UnderstandError,
    UnderstandPipeline,
    build_model,
    clean_summary,
    disable_failed,
    safe_file,
    workspace_digest,
)
from rook.core.events import EventBus, QuestionAsked, clear_secrets
from rook.engine.dryrun import Check, DryRunReport, action_order, dry_run
from rook.engine.inprocess import InProcessTransport
from rook.model.loader import ModelError, load_model
from rook.sandbox.base import ExecResult, Sandbox, SandboxError

RUN = "r_understand"
FIXTURES = Path(__file__).parents[1] / "fixtures"
MINISHOP_DIR = FIXTURES / "minishop"
RECORDINGS = FIXTURES / "recordings" / "understand_minishop"
BASE = "http://minishop.test"
SETUP_VALUE = "rook-test-admin-pw-17"  # a fake setup answer, not a real secret

_spec = importlib.util.spec_from_file_location("minishop_app_understand", MINISHOP_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)

MINISHOP_MODEL = load_model(MINISHOP_DIR / "rook.yaml")
MAPPER_PARTS = {k: v for k, v in MINISHOP_MODEL.model_dump(mode="json", by_alias=True, exclude_none=True).items()
                if k in ("actors", "actions", "state")}
SUMMARY = {
    "language": "python", "framework": "fastapi", "entrypoints": ["app.py"], "routes_files": ["app.py"],
    "models_files": ["app.py"], "test_command": "pytest -q", "run_hints": {"port": 8000},
    "business_summary": "A small shop.",
}
PLAN = {"mode": "command", "build": "pip install fastapi uvicorn",
        "start": "uvicorn app:app --host 0.0.0.0 --port 8000", "port": 8000, "health_path": "/health",
        "env_required": ["MINISHOP_ADMIN_PASSWORD"], "env_defaults": {}}


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """The run's copy of minishop, as a plain folder (without the hand-written rook.yaml)."""
    ws = tmp_path / "ws"
    shutil.copytree(MINISHOP_DIR, ws, ignore=shutil.ignore_patterns("__pycache__", "rook.yaml", ".pytest_cache"))
    return ws


class NullSandbox(Sandbox):
    def __init__(self) -> None:
        self.stopped = 0

    def start(self, plan: SandboxPlan | None = None) -> str:
        return BASE

    def stop(self) -> None:
        self.stopped += 1

    def restart(self) -> str:
        return BASE

    def exec(self, cmd: Any, timeout: float = 600.0) -> ExecResult:
        return ExecResult(0, "", "")

    def logs(self, tail: int = 200) -> str:
        return ""


async def _health(app: Any, path: str) -> int:
    async with httpx.AsyncClient(transport=InProcessTransport(app), base_url=BASE) as http:
        return (await http.get(path)).status_code


class InProcessLauncher:
    """Stands in for Docker: minishop in-process, with the plan's env. Can fail the first N launches."""

    def __init__(self, fail: list[str] | None = None) -> None:
        self.fail = list(fail or [])
        self.calls: list[tuple[SandboxPlan, dict[str, str]]] = []
        self.sandbox = NullSandbox()

    def __call__(self, plan: SandboxPlan, values: Mapping[str, str], summary: RepoSummary) -> StartedApp:
        self.calls.append((plan, dict(values)))
        if self.fail:
            raise SandboxError(self.fail.pop(0))
        missing = [n for n in plan.env_required if n not in values]
        if missing:
            raise SandboxError(f"missing required setup values: {missing}")
        env = {**plan.env_defaults, **values}
        with mock.patch.dict(os.environ, env):
            app = minishop.create_app()
        status = asyncio.run(_health(app, plan.health_path))  # the check a real sandbox does
        if status != 200:
            raise SandboxError(f"the app was not healthy ({plan.health_path}: HTTP {status})")
        return StartedApp(sandbox=self.sandbox, base_url=BASE, transport=InProcessTransport(app))


class Answerer:
    def __init__(self, value: str | None = SETUP_VALUE) -> None:
        self.value = value
        self.questions: list[QuestionAsked] = []

    async def __call__(self, question: QuestionAsked) -> str | None:
        self.questions.append(question)
        return self.value


class FakeClient:
    """Scripted agent replies per agent id; records every prompt."""

    def __init__(self, replies: dict[str, list[dict[str, Any] | Exception]]) -> None:
        self.bus = EventBus()
        self.run_id = RUN
        self.replies = {k: list(v) for k, v in replies.items()}
        self.calls: list[tuple[str, str, Path]] = []

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        self.calls.append((agent_id, prompt, Path(workspace)))
        reply = self.replies[agent_id].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return AgentResult(output=output_model.model_validate(reply), text="", cost=0.0, recorded=False,
                           call_id="c_1")

    def prompts(self, agent_id: str) -> list[str]:
        return [p for a, p, _ in self.calls if a == agent_id]


def events(client: FakeClient | BobClient, event_type: str | None = None) -> list[Any]:
    history = client.bus._channel(RUN).history
    return [e for e in history if event_type is None or e.type == event_type]


def broken_parts(**changes: str) -> dict[str, Any]:
    """The minishop Mapper parts with some action paths replaced."""
    parts = {k: [dict(x) for x in v] for k, v in MAPPER_PARTS.items()}
    for action in parts["actions"]:
        if action["name"] in changes:
            action["request"] = {**action["request"], "path": changes[action["name"]]}
    return parts


# --- workspace reading ---


def test_digest_is_deterministic_and_skips_private_folders(workspace: Path, tmp_path: Path) -> None:
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("secret remote")
    (workspace / ".bob").mkdir()
    (workspace / ".bob" / "custom_modes.yaml").write_text("x")
    other = tmp_path / "copy2"
    shutil.copytree(workspace, other)
    digest = workspace_digest(workspace)
    assert digest == workspace_digest(other)  # no absolute path inside
    assert "app.py" in digest and "test_minishop_app.py" in digest
    assert ".git" not in digest and ".bob" not in digest and str(tmp_path) not in digest
    (other / "app.py").write_text("changed")
    assert workspace_digest(other) != digest  # content hashes make the recording key change


def test_safe_file_confines_paths_to_the_workspace(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.env"
    outside.write_text("BOB_API_KEY=nope")
    (workspace / "link.env").symlink_to(outside)
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("x")
    assert safe_file(workspace, "app.py") is not None
    for bad in ["../outside.env", str(outside), "link.env", ".git/config", "app.py\n", "", "missing.py",
                ".", "sub\\..\\app.py"]:
        assert safe_file(workspace, bad) is None, bad


def test_clean_summary_drops_paths_that_are_not_workspace_files(workspace: Path) -> None:
    summary = RepoSummary.model_validate({**SUMMARY, "routes_files": ["app.py", "../../etc/passwd", "nope.py"]})
    cleaned, dropped = clean_summary(workspace, summary)
    assert cleaned.routes_files == ["app.py"]
    assert dropped == ["../../etc/passwd", "nope.py"]


# --- model building and the dry-run (the engine decides) ---


def test_build_model_rejects_vars_that_no_action_captures() -> None:
    parts = broken_parts()
    parts["actions"] = [a for a in parts["actions"] if a["name"] != "create_product"]
    with pytest.raises(ModelError) as info:
        build_model(MapperOutput.model_validate(parts), SandboxPlan.model_validate(PLAN))
    assert any("'product_id' is not captured" in e for e in info.value.errors)


def test_action_order_puts_producers_first() -> None:
    names = [a.name for a in action_order(MINISHOP_MODEL)]
    assert names.index("create_product") < names.index("buy") < names.index("refund")


async def test_dry_run_passes_every_minishop_action() -> None:
    with mock.patch.dict(os.environ, {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}):
        app = minishop.create_app()
    report = await dry_run(MINISHOP_MODEL, BASE, env={"MINISHOP_ADMIN_PASSWORD": "admin-pass"},
                           transport=InProcessTransport(app))
    assert report.ok, report.failures()
    assert set(report.actions) == {a.name for a in MINISHOP_MODEL.actions}
    assert set(report.readers) == {"order", "product"}


async def test_dry_run_reports_a_wrong_path() -> None:
    model = build_model(MapperOutput.model_validate(broken_parts(ship="/orders/{{ref.order_id}}/dispatch")),
                        SandboxPlan.model_validate(PLAN))
    with mock.patch.dict(os.environ, {"MINISHOP_ADMIN_PASSWORD": "pw-1"}):
        app = minishop.create_app()
    report = await dry_run(model, BASE, env={"MINISHOP_ADMIN_PASSWORD": "pw-1"}, transport=InProcessTransport(app))
    assert not report.ok and report.failed_actions == ["ship"]
    assert report.actions["ship"].detail.startswith("POST /orders/{{ref.order_id}}/dispatch -> HTTP 404")
    assert report.failures().startswith("action ship: POST /orders/{{ref.order_id}}/dispatch -> HTTP 404")


async def test_dry_run_reports_a_failed_login_and_its_dependents() -> None:
    model = build_model(MapperOutput.model_validate(MAPPER_PARTS), SandboxPlan.model_validate(PLAN))
    with mock.patch.dict(os.environ, {"MINISHOP_ADMIN_PASSWORD": "pw-1"}):
        app = minishop.create_app()
    report = await dry_run(model, BASE, env={"MINISHOP_ADMIN_PASSWORD": "wrong"}, transport=InProcessTransport(app))
    detail = report.actions["create_product"].detail
    assert "setup of actor 'admin'" in detail and "HTTP 401" in detail
    assert "no captured value for required var 'product_id'" in report.actions["buy"].detail
    assert report.actions["admin_export"].ok  # a customer action that needs nothing still works
    assert report.readers["product"].detail == "never read: no action captured 'product_id'"


def test_disable_failed_drops_dependents_and_readers() -> None:
    model = build_model(MapperOutput.model_validate(MAPPER_PARTS), SandboxPlan.model_validate(PLAN))
    report = DryRunReport(actions={a.name: Check(a.name, a.name != "buy", "") for a in model.actions},
                          readers={"order": Check("order", True, ""), "product": Check("product", True, "")})
    reduced, disabled = disable_failed(model, report)
    assert {a.name for a in reduced.actions} == {"create_product", "admin_export"}
    assert disabled == ["buy", "refund", "cancel", "ship", "state:order"]


# --- the pipeline with scripted agents ---


async def test_pipeline_happy_path_writes_a_valid_model(workspace: Path) -> None:
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN], "mapper": [MAPPER_PARTS]})
    answer = Answerer()
    launcher = InProcessLauncher()
    result = await UnderstandPipeline(client, workspace, answer=answer, launcher=launcher).run()

    assert result.dry_run.ok and result.disabled == []
    assert load_model(result.model_path) == result.model
    assert result.model_path == workspace / "rook" / "rook.yaml"
    assert result.env == {"MINISHOP_ADMIN_PASSWORD": SETUP_VALUE}
    assert (workspace / ".bob" / "custom_modes.yaml").is_file()
    assert all(ws == workspace.resolve() for _, _, ws in client.calls)  # Bob runs in the workspace copy
    # The setup value was asked once, and never appears in any event.
    assert [q.payload["name"] for q in answer.questions] == ["MINISHOP_ADMIN_PASSWORD"]
    assert SETUP_VALUE not in "".join(e.model_dump_json() for e in events(client))
    phases = [e.data["phase"] for e in events(client, "run.phase")]
    assert phases == ["SCOUT", "START_APP", "MAP"]
    types = [e.type for e in events(client)]
    assert types.index("repo.summary") < types.index("question.asked") < types.index("sandbox.ready")
    assert types.index("model.actions") < types.index("engine.finished")
    finished = events(client, "engine.finished")[-1].data
    assert finished["ok"] is True and finished["worker"] == "runner"
    # The Mapper got the env names (never values) and the route file content.
    mapper_prompt = client.prompts("mapper")[0]
    assert "MINISHOP_ADMIN_PASSWORD" in mapper_prompt and SETUP_VALUE not in mapper_prompt
    assert '<untrusted path="app.py">' in mapper_prompt


async def test_mechanic_loop_feeds_logs_back_and_stops_after_three(workspace: Path) -> None:
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN, PLAN, PLAN], "mapper": [MAPPER_PARTS]})
    launcher = InProcessLauncher(fail=["ModuleNotFoundError: No module named 'uvicorn'", "port in use"])
    result = await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=launcher).run()
    prompts = client.prompts("mechanic")
    assert len(prompts) == 3 and len(launcher.calls) == 3
    assert "No module named" not in prompts[0]
    assert "No module named 'uvicorn'" in prompts[1] and "port in use" in prompts[2]
    assert result.dry_run.ok

    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN, PLAN, PLAN]})
    launcher = InProcessLauncher(fail=["boom 1", "boom 2", "boom 3"])
    with pytest.raises(UnderstandError) as info:
        await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=launcher).run()
    assert info.value.phase == "START_APP" and len(launcher.calls) == 3


async def test_bad_env_names_are_fed_back_not_asked(workspace: Path) -> None:
    bad = {**PLAN, "env_required": ["LD_PRELOAD"]}
    client = FakeClient({"scout": [SUMMARY], "mechanic": [bad, PLAN], "mapper": [MAPPER_PARTS]})
    answer = Answerer()
    await UnderstandPipeline(client, workspace, answer=answer, launcher=InProcessLauncher()).run()
    assert [q.payload["name"] for q in answer.questions] == ["MINISHOP_ADMIN_PASSWORD"]
    assert "LD_PRELOAD" in client.prompts("mechanic")[1]


async def test_no_setup_value_stops_the_run(workspace: Path) -> None:
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN]})
    with pytest.raises(UnderstandError, match="no value was given for MINISHOP_ADMIN_PASSWORD"):
        await UnderstandPipeline(client, workspace, answer=Answerer(None), launcher=InProcessLauncher()).run()


async def test_mapper_loop_feeds_http_errors_back(workspace: Path) -> None:
    wrong = broken_parts(ship="/orders/{{ref.order_id}}/dispatch")
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN], "mapper": [wrong, MAPPER_PARTS]})
    result = await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=InProcessLauncher()).run()
    prompts = client.prompts("mapper")
    assert len(prompts) == 2
    assert "(none)" in prompts[0].split("Dry-run failures of your last attempt", 1)[1][:40]
    feedback = prompts[1].split("Dry-run failures of your last attempt", 1)[1]
    assert "action ship: POST /orders/{{ref.order_id}}/dispatch -> HTTP 404" in feedback
    assert "Your last model was" in feedback
    assert result.dry_run.ok and result.disabled == []


async def test_mapper_invalid_model_is_fed_back(workspace: Path) -> None:
    parts = broken_parts()
    parts["actions"] = [a for a in parts["actions"] if a["name"] != "create_product"]
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN], "mapper": [parts, MAPPER_PARTS]})
    result = await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=InProcessLauncher()).run()
    assert "'product_id' is not captured by any action" in client.prompts("mapper")[1]
    assert result.dry_run.ok


async def test_action_failing_three_times_is_disabled(workspace: Path) -> None:
    wrong = broken_parts(ship="/orders/{{ref.order_id}}/dispatch")
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN], "mapper": [wrong, wrong, wrong]})
    launcher = InProcessLauncher()
    result = await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=launcher).run()
    assert result.disabled == ["ship"]
    assert "ship" not in {a.name for a in result.model.actions}
    assert result.dry_run.ok
    assert load_model(result.model_path) == result.model
    assert launcher.sandbox.stopped == 0  # the app stays up for the next phases


def test_refuses_to_run_bob_in_the_rook_repo() -> None:
    client = FakeClient({})
    repo = Path(__file__).parents[2]
    for bad in (repo, repo / "src", MINISHOP_DIR):
        with pytest.raises(ValueError, match="Rook's own repo"):
            UnderstandPipeline(client, bad, answer=Answerer(), launcher=InProcessLauncher())


async def test_mapper_failure_stops_the_sandbox(workspace: Path) -> None:
    client = FakeClient({"scout": [SUMMARY], "mechanic": [PLAN], "mapper": [AgentOutputError("bad json")]})
    launcher = InProcessLauncher()
    with pytest.raises(UnderstandError) as info:
        await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=launcher).run()
    assert info.value.phase == "MAP" and launcher.sandbox.stopped == 1


# --- the recorded real run ---

_SECRET_PATTERNS = [
    re.compile(r"bob_[A-Za-z0-9]{8,}", re.IGNORECASE),
    re.compile(r"\bgh[psuor]_[A-Za-z0-9]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"BOB_API_KEY\s*[=:]\s*\S"),
]


def test_recordings_hold_no_secrets() -> None:
    files = sorted(RECORDINGS.glob("*.ndjson"))
    assert files, "the recorded run is missing"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text


async def test_recorded_run_on_minishop_produces_a_model_that_dry_runs_ok(workspace: Path) -> None:
    client = BobClient(EventBus(), RUN, mode="replay", recordings_dir=RECORDINGS, replay_speed=1e9,
                       replay_max_gap=0.0)
    answer = Answerer()
    result = await UnderstandPipeline(client, workspace, answer=answer, launcher=InProcessLauncher()).run()
    _check_real_run(result, client)
    finished = [e.data for e in events(client, "agent.finished")]
    assert [f["agent"] for f in finished][:3] == ["scout", "mechanic", "mapper"]
    assert all(f["recorded"] and f["ok"] for f in finished)
    assert client.total_cost == 0.0  # replays are free


def _check_real_run(result: Any, client: BobClient) -> None:
    model = load_model(result.model_path)  # a valid rook.yaml on disk
    assert model == result.model
    assert result.dry_run.ok, result.dry_run.failures()
    assert result.disabled == []
    assert set(result.dry_run.actions) == {a.name for a in model.actions}
    assert all(c.ok for c in result.dry_run.actions.values())
    paths = {(a.request.method, a.request.path) for a in model.actions}
    assert ("POST", "/orders") in paths  # the Mapper found minishop's buy endpoint
    assert any(p.endswith("/refunds") for _, p in paths)
    assert [e.data["phase"] for e in events(client, "run.phase")] == ["SCOUT", "START_APP", "MAP"]


@pytest.mark.bob
@pytest.mark.docker
async def test_live_run_on_minishop(workspace: Path, tmp_path: Path) -> None:
    """A real run: Bob (Scout, Mechanic, Mapper) and a DockerSandbox. Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    client = BobClient(EventBus(), RUN, mode="record" if record_dir else "live",
                       recordings_dir=Path(record_dir).resolve() if record_dir else tmp_path / "rec")
    result = await UnderstandPipeline(client, workspace, answer=Answerer()).run()
    try:
        print(f"\ncoins used: {client.total_cost:.4f}")
        print(result.model_path.read_text())
        _check_real_run(result, client)
    finally:
        result.app.sandbox.stop()


def test_example_shapes_still_match() -> None:
    # The fakes above use real agent shapes; keep them in sync with the schemas' own examples.
    assert set(SUMMARY) == set(example_for(RepoSummary))
    SandboxPlan.model_validate(PLAN)
    MapperOutput.model_validate(MAPPER_PARTS)
