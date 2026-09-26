"""ROOK-018: the RULES phase (Lawmaker -> engine sanity checks -> Rule Critic).

The default suite uses scripted fakes and a committed replay of real Bob calls. The Understand phase is
replayed from its own recording (tests/fixtures/recordings/understand_minishop), so only the Lawmaker and
the Rule Critic are live. The app is minishop in fixed mode, in-process. The live run (`-m bob`, no
Docker needed) re-records the RULES calls when ROOK_RECORD_DIR is set:

    source ~/.bob-key.env
    ROOK_RECORD_DIR=tests/fixtures/recordings/rules_minishop \
        uv run pytest -m bob tests/unit/test_pipeline_rules.py

Then replace the local workspace path (`/tmp/pytest-of-<user>/.../ws`) in the new files with `/workspace`:
Bob's tool calls quote it, and replay never uses it.
"""

import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from pydantic import BaseModel
from test_pipeline_understand import (
    _SECRET_PATTERNS,
    BASE,
    MINISHOP_DIR,
    MINISHOP_MODEL,
    RUN,
    SUMMARY,
    Answerer,
    FakeClient,
    InProcessLauncher,
    NullSandbox,
    events,
    minishop,
)

from rook.agents.bob import AgentOutputError, AgentResult, BobClient
from rook.agents.rules import RulesError, RulesPipeline, RulesResult, lawmaker_files
from rook.agents.schemas import LawmakerOutput, RepoSummary
from rook.agents.understand import StartedApp, Understanding, UnderstandPipeline
from rook.core.events import EventBus
from rook.engine.inprocess import InProcessTransport
from rook.model.loader import load_model
from rook.model.schema import Rule

RECORDINGS = Path(__file__).parents[1] / "fixtures" / "recordings" / "rules_minishop"
UNDERSTAND_RECORDINGS = RECORDINGS.parent / "understand_minishop"
ENV = {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}  # the fixture's built-in default, not a secret

MINISHOP_RULES = [r.model_dump(mode="json", by_alias=True, exclude_none=True) | {"status": "proposed"}
                  for r in MINISHOP_MODEL.rules]
FAILING = {"id": "refund_already_positive", "text": "Every order has a refund", "kind": "state",
           "scope": "order", "check": "order.refunded > 0", "evidence": ["app.py: refund()"]}
UNKNOWN_FIELD = {"id": "discount_le_paid", "text": "Discounts never exceed the price", "kind": "state",
                 "scope": "order", "check": "order.discount <= order.paid", "evidence": ["app.py"]}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """The run's copy of minishop, as a plain folder (without the hand-written rook.yaml)."""
    ws = tmp_path / "ws"
    shutil.copytree(MINISHOP_DIR, ws, ignore=shutil.ignore_patterns("__pycache__", "rook.yaml", ".pytest_cache"))
    return ws


def approve(*ids: str) -> dict[str, Any]:
    return {"verdicts": [{"rule_id": i, "verdict": "approve", "reason": "backed by the code"} for i in ids]}


def fixed_app() -> StartedApp:
    with mock.patch.dict(os.environ, ENV):
        app = minishop.create_app(fixed=True)
    return StartedApp(sandbox=NullSandbox(), base_url=BASE, transport=InProcessTransport(app))


def pipeline(client: Any, workspace: Path) -> RulesPipeline:
    return RulesPipeline(client, workspace, model=MINISHOP_MODEL, summary=RepoSummary.model_validate(SUMMARY),
                         app=fixed_app(), env=ENV)


def outcome(result: RulesResult, rule_id: str) -> Any:
    return next(o for o in result.outcomes if o.proposed.id == rule_id)


# --- inputs ---


def test_lawmaker_files_put_code_first_then_tests_and_docs(workspace: Path) -> None:
    (workspace / "README.md").write_text("# minishop\nRefunds never exceed the price.\n")
    (workspace / "docs").mkdir()
    (workspace / "docs" / "rules.md").write_text("Stock never goes negative.\n")
    (workspace / "notes.py").write_text("x = 1\n")
    files = lawmaker_files(workspace, RepoSummary.model_validate(SUMMARY))
    assert list(files) == ["app.py", "README.md", "docs/rules.md", "test_minishop_app.py"]


# --- the pipeline with scripted agents ---


async def test_engine_rejects_before_the_critic_and_the_critic_judges_the_rest(workspace: Path) -> None:
    ids = [r["id"] for r in MINISHOP_RULES]
    client = FakeClient({"lawmaker": [{"rules": [*MINISHOP_RULES, FAILING, UNKNOWN_FIELD]}],
                         "rule_critic": [approve(*ids)]})
    result = await pipeline(client, workspace).run()

    assert [r.id for r in result.accepted] == ids
    failing = outcome(result, "refund_already_positive")
    assert not failing.accepted and failing.critic is None and failing.engine.stage == "fresh"
    assert failing.reason.startswith("engine: it is already false on a fresh app: a new order gives")
    unknown = outcome(result, "discount_le_paid")
    assert not unknown.accepted and unknown.engine.stage == "static"
    assert "'order' has no field 'discount'" in unknown.reason
    # An expected 403 is judged by the rule's own check, not treated as a failed request.
    admin = outcome(result, "admin_export_forbidden")
    assert admin.accepted and "HTTP 403" in admin.engine.reason
    # The critic never sees engine-rejected rules; untrusted inputs are wrapped.
    critic_prompt = client.prompts("rule_critic")[0]
    assert "refund_already_positive" not in critic_prompt and "discount_le_paid" not in critic_prompt
    assert '<untrusted path="rules">' in critic_prompt and '<untrusted path="app.py">' in critic_prompt
    assert '<untrusted path="app.py">' in client.prompts("lawmaker")[0]
    # rook.yaml holds only the accepted rules, still `proposed` (a human approves).
    saved = load_model(result.model_path)
    assert saved == result.model
    assert [(r.id, r.status) for r in saved.rules] == [(i, "proposed") for i in ids]
    assert result.model_path == workspace / "rook" / "rook.yaml"


async def test_events_follow_the_rules_phase(workspace: Path) -> None:
    client = FakeClient({"lawmaker": [{"rules": [*MINISHOP_RULES, FAILING]}],
                         "rule_critic": [approve(*[r["id"] for r in MINISHOP_RULES])]})
    await pipeline(client, workspace).run()
    types = [e.type for e in events(client)]
    assert [e.data["phase"] for e in events(client, "run.phase")] == ["RULES"]
    assert types.index("rules.proposed") < types.index("engine.started") < types.index("engine.finished")
    assert types.index("engine.finished") < types.index("rules.reviewed")
    assert [r["id"] for r in events(client, "rules.proposed")[0].data["rules"]][-1] == "refund_already_positive"
    started, finished = events(client, "engine.started")[0].data, events(client, "engine.finished")[0].data
    assert started["worker"] == finished["worker"] == "judge"
    assert finished["summary"] == "4/5 proposed rules hold on a fresh app"
    verdicts = events(client, "rules.reviewed")[0].data["verdicts"]
    assert verdicts[0]["rule_id"] == "refund_already_positive" and verdicts[0]["by"] == "engine"
    assert verdicts[0]["verdict"] == "reject" and "already false on a fresh app" in verdicts[0]["reason"]
    assert [v["by"] for v in verdicts[1:]] == ["critic"] * 4
    assert "rules.approved" not in types  # only a human (or auto mode) approves
    warns = [e.data["text"] for e in events(client, "log") if e.data["level"] == "warn"]
    assert any(w.startswith("Rule refund_already_positive rejected by the engine") for w in warns)


async def test_critic_verdicts_never_override_the_engine(workspace: Path) -> None:
    # The critic "approves" a rule the engine rejected (and an id that does not exist): both ignored.
    client = FakeClient({"lawmaker": [{"rules": [MINISHOP_RULES[0], FAILING]}],
                         "rule_critic": [approve("refund_le_paid", "refund_already_positive", "ghost")]})
    result = await pipeline(client, workspace).run()
    assert [r.id for r in result.accepted] == ["refund_le_paid"]
    assert not outcome(result, "refund_already_positive").accepted
    warns = [e.data["text"] for e in events(client, "log")]
    assert any("unknown rule ids (ignored): ghost, refund_already_positive" in w for w in warns)


async def test_critic_reject_and_revise_are_applied_and_revisions_are_rechecked(workspace: Path) -> None:
    good_revision = {"id": "stock_ge_zero", "text": "Stock never goes below zero", "kind": "state",
                     "scope": "product", "check": "product.stock >= 0", "evidence": []}
    bad_revision = {**FAILING, "id": "ship_rule_v2"}
    critic = {"verdicts": [
        {"rule_id": "refund_le_paid", "verdict": "approve", "reason": "ok"},
        {"rule_id": "stock_non_negative", "verdict": "revise", "reason": "clearer id", "revised": good_revision},
        {"rule_id": "cancelled_never_ships", "verdict": "revise", "reason": "stronger", "revised": bad_revision},
        {"rule_id": "admin_export_forbidden", "verdict": "reject", "reason": "not a business rule"},
    ]}
    client = FakeClient({"lawmaker": [{"rules": MINISHOP_RULES}], "rule_critic": [critic]})
    result = await pipeline(client, workspace).run()

    assert [r.id for r in result.accepted] == ["refund_le_paid", "stock_ge_zero"]
    revised = outcome(result, "stock_non_negative")
    assert revised.accepted and revised.rule.evidence == MINISHOP_MODEL.rules[1].evidence  # kept
    failed = outcome(result, "cancelled_never_ships")
    assert not failed.accepted and failed.reason.startswith("the critic's revision failed the engine")
    assert outcome(result, "admin_export_forbidden").reason == "critic: not a business rule"
    labels = [e.data["label"] for e in events(client, "engine.started")]
    assert labels == ["Sanity-checking 4 proposed rules on a fresh app",
                      "Sanity-checking 2 revised rules on a fresh app"]
    verdicts = events(client, "rules.reviewed")[0].data["verdicts"]
    assert {"rule_id": "ship_rule_v2", "verdict": "reject", "by": "engine"}.items() <= verdicts[-1].items()


async def test_a_failed_critic_leaves_engine_checked_rules_for_the_human(workspace: Path) -> None:
    client = FakeClient({"lawmaker": [{"rules": [MINISHOP_RULES[0], FAILING]}],
                         "rule_critic": [AgentOutputError("bad json")]})
    result = await pipeline(client, workspace).run()
    kept = outcome(result, "refund_le_paid")
    assert kept.accepted and kept.critic is None
    assert [r.id for r in result.accepted] == ["refund_le_paid"]


async def test_no_critic_call_when_the_engine_rejects_everything(workspace: Path) -> None:
    client = FakeClient({"lawmaker": [{"rules": [FAILING]}]})
    result = await pipeline(client, workspace).run()
    assert result.accepted == [] and client.prompts("rule_critic") == []
    assert load_model(result.model_path).rules == []


async def test_a_failed_lawmaker_stops_the_phase(workspace: Path) -> None:
    client = FakeClient({"lawmaker": [AgentOutputError("no json block")]})
    with pytest.raises(RulesError, match="the Lawmaker failed"):
        await pipeline(client, workspace).run()


async def test_approve_marks_rules_approved_and_publishes(workspace: Path) -> None:
    client = FakeClient({"lawmaker": [{"rules": [*MINISHOP_RULES, FAILING]}],
                         "rule_critic": [approve(*[r["id"] for r in MINISHOP_RULES])]})
    rules = pipeline(client, workspace)
    with pytest.raises(RuntimeError):
        await rules.approve(["refund_le_paid"])
    await rules.run()
    with pytest.raises(ValueError, match="refund_already_positive"):
        await rules.approve(["refund_already_positive"])  # engine-rejected rules cannot be approved
    model = await rules.approve(["refund_le_paid", "admin_export_forbidden"])
    status = {r.id: r.status for r in load_model(workspace / "rook" / "rook.yaml").rules}
    assert status == {"refund_le_paid": "approved", "stock_non_negative": "proposed",
                      "cancelled_never_ships": "proposed", "admin_export_forbidden": "approved"}
    assert model.rules == load_model(workspace / "rook" / "rook.yaml").rules
    assert events(client, "rules.approved")[0].data == {"rule_ids": ["refund_le_paid", "admin_export_forbidden"]}


def test_refuses_to_run_bob_in_the_rook_repo() -> None:
    with pytest.raises(ValueError, match="Rook's own repo"):
        pipeline(FakeClient({}), Path(__file__).parents[2])


# --- the recorded real run ---


class InjectingClient:
    """A real (replaying) BobClient whose Lawmaker output gets one extra rule that is false on a fresh app."""

    def __init__(self, inner: BobClient, extra: dict[str, Any]) -> None:
        self.inner, self.extra = inner, extra
        self.bus, self.run_id = inner.bus, inner.run_id

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: type[BaseModel],
                   max_turns: int = 8, max_cost: float | None = None) -> AgentResult:
        result = await self.inner.call(agent_id, slug, prompt, workspace, output_model, max_turns, max_cost)
        if agent_id == "lawmaker":
            assert isinstance(result.output, LawmakerOutput)
            rules = [*result.output.rules, Rule.model_validate(self.extra)]
            return replace(result, output=LawmakerOutput(rules=rules))
        return result


async def understand(workspace: Path) -> Understanding:
    """The recorded Understand run (Scout, Mechanic, Mapper), replayed on buggy minishop as recorded."""
    client = BobClient(EventBus(), RUN, mode="replay", recordings_dir=UNDERSTAND_RECORDINGS, replay_speed=1e9,
                       replay_max_gap=0.0)
    return await UnderstandPipeline(client, workspace, answer=Answerer(), launcher=InProcessLauncher()).run()


def rules_pipeline(client: Any, workspace: Path, known: Understanding) -> RulesPipeline:
    """The RULES phase on the understood model, sanity-checked on a correct (fixed) minishop."""
    return RulesPipeline(client, workspace, model=known.model, summary=known.summary, app=fixed_app(),
                         env=known.env)


def _check_real_rules(result: RulesResult) -> None:
    """The AC: the refund, stock, ship and admin rules are proposed and accepted on a correct app."""
    accepted = result.accepted
    state = [r for r in accepted if r.kind == "state"]
    assert any(r.scope == "order" and "refund" in r.check and "paid" in r.check for r in state), accepted
    assert any("stock" in r.check and ">= 0" in r.check for r in state), accepted
    assert any("cancelled" in r.check and "shipped" in r.check for r in state), accepted
    admin = [r for r in accepted if r.kind == "response" and r.when is not None
             and r.when.action == "admin_export" and r.when.actor == "customer"]
    assert admin and all("403" in r.check for r in admin), accepted
    assert all(r.evidence and r.status == "proposed" for r in accepted)
    assert load_model(result.model_path).rules == accepted
    # The admin rule expects a 4xx: it passed because its own check held, not despite the status.
    assert any("-> HTTP 403" in o.engine.reason for o in result.outcomes if o.rule in admin)


def test_recordings_hold_no_secrets() -> None:
    files = sorted(RECORDINGS.glob("*.ndjson"))
    assert len(files) == 2, "the recorded Lawmaker and Rule Critic calls are missing"
    for path in files:
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} matches {pattern.pattern}"
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text
        assert "pytest-of-" not in text and "/home/" not in text  # no local paths or user names


async def test_recorded_run_on_minishop_accepts_the_four_rules(workspace: Path) -> None:
    known = await understand(workspace)
    bob = BobClient(EventBus(), RUN, mode="replay", recordings_dir=RECORDINGS, replay_speed=1e9,
                    replay_max_gap=0.0)
    client = InjectingClient(bob, {**FAILING, "check": "order.refunded_total > 0"})  # the Mapper's field name
    result = await rules_pipeline(client, workspace, known).run()

    _check_real_rules(result)
    # The real Lawmaker also proposed a check with a method call: the safe evaluator refuses it.
    method_call = outcome(result, "buy_response_status_paid")
    assert not method_call.accepted and method_call.engine.stage == "static"
    assert "no method calls" in method_call.reason
    injected = outcome(result, "refund_already_positive")
    assert not injected.accepted and injected.critic is None
    assert injected.reason.startswith("engine: it is already false on a fresh app: a new order gives")
    finished = [e.data for e in events(bob, "agent.finished")]
    assert [f["agent"] for f in finished] == ["lawmaker", "rule_critic"]
    assert all(f["recorded"] and f["ok"] for f in finished)
    assert bob.total_cost == 0.0  # replays are free
    verdicts = {v["rule_id"]: v for v in events(bob, "rules.reviewed")[0].data["verdicts"]}
    assert verdicts["refund_already_positive"]["by"] == "engine"
    assert verdicts["refund_already_positive"]["verdict"] == "reject"
    assert {v["by"] for i, v in verdicts.items() if i not in ("refund_already_positive", "buy_response_status_paid")} \
        == {"critic"}


@pytest.mark.bob
async def test_live_rules_on_minishop(workspace: Path, tmp_path: Path) -> None:
    """Real Lawmaker and Rule Critic calls (the Understand phase is replayed). Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    known = await understand(workspace)
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    client = BobClient(EventBus(), RUN, mode="record" if record_dir else "live",
                       recordings_dir=Path(record_dir).resolve() if record_dir else tmp_path / "rec")
    result = await rules_pipeline(client, workspace, known).run()
    print(f"\ncoins used: {client.total_cost:.4f}")
    for o in result.outcomes:
        print(f"{o.proposed.id}: accepted={o.accepted} ({o.reason}) check={o.rule.check!r}")
    _check_real_rules(result)
