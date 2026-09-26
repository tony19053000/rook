"""The RULES phase: Lawmaker -> engine sanity checks -> Rule Critic (02_ARCHITECTURE.md section 4).

Bob proposes and code decides (CLAUDE.md rule 1):
- the Lawmaker proposes rules with evidence (`rules.proposed`);
- the engine (engine/sanity.py) checks each rule: it must parse with the safe evaluator, use only known
  names and fields, and hold on a fresh app. A rule that fails is rejected with the engine's reason and
  never reaches the critic. A response rule the app breaks on its very first request is kept but flagged
  `already_broken` (a one-step bug or a wrong rule): the critic is told, the flag is carried on its verdicts
  and outcome, and only a human can approve it (never auto mode);
- the Rule Critic judges what the surviving rules mean (a real invariant, too weak, a duplicate). Its
  verdict can reject or revise a rule, but it never overrides the engine: a revised rule is sanity-checked
  again, and a critic "approve" cannot save a rule the engine rejected;
- every verdict (engine and critic) is published as `rules.reviewed`. Accepted rules are written to
  `rook/rook.yaml` with status `proposed`; only `approve()` (a human, or auto mode) marks them `approved`.

Rules from Bob are untrusted data: they are validated and evaluated with the safe evaluator only.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rook.agents.caller import BOB_FAILURES, AgentCaller, call_agent
from rook.agents.schemas import LawmakerOutput, RuleCriticOutput, RuleVerdict
from rook.agents.understand import (
    FILES_MAX_TOTAL,
    StartedApp,
    _walk,
    check_not_rook_repo,
    read_files,
    write_model,
)
from rook.core.events import (
    EngineFinished,
    EngineStarted,
    Log,
    RepoSummary,
    RulesApproved,
    RulesProposed,
    RulesReviewed,
    RunPhase,
    redact_text,
)
from rook.engine.sanity import SanityResult, sanity_check
from rook.model.schema import RookModel, Rule

RULES_NOTE = "Written by Rook (Mapper, Lawmaker), checked by the engine. Review the rules before approving."
MAX_EXTRA_FILES = 40
_DOC_SUFFIXES = (".md", ".rst", ".txt")


class RulesError(RuntimeError):
    """The RULES phase could not finish (the Lawmaker failed)."""


@dataclass
class RuleOutcome:
    """What happened to one proposed rule. `rule` is the critic's revision when there is one."""

    proposed: Rule
    rule: Rule
    engine: SanityResult
    critic: RuleVerdict | None
    accepted: bool
    reason: str

    @property
    def already_broken(self) -> bool:
        """The engine saw the (final) rule fail on the first request to a fresh app (see engine/sanity.py)."""
        return self.engine.already_broken


@dataclass
class RulesResult:
    model: RookModel  # the model with the accepted rules (status `proposed`)
    outcomes: list[RuleOutcome]
    model_path: Path

    @property
    def accepted(self) -> list[Rule]:
        return [o.rule for o in self.outcomes if o.accepted]

    @property
    def rejected(self) -> list[RuleOutcome]:
        return [o for o in self.outcomes if not o.accepted]


# --- inputs ---


def _is_test_or_doc(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1].lower()
    if any(p in ("tests", "test", "__tests__", "spec", "docs", "doc") for p in parts[:-1]):
        return True
    if name.startswith("test_") or name.endswith(("_test.py", "_test.go", "_spec.rb")):
        return True
    if ".test." in name or ".spec." in name:
        return True
    return name.startswith("readme") or (len(parts) == 1 and name.endswith(_DOC_SUFFIXES))


def lawmaker_files(workspace: Path, summary: RepoSummary) -> dict[str, str]:
    """The model, route and entrypoint files first, then tests and docs with what is left of the budget."""
    code = read_files(workspace, [*summary.models_files, *summary.routes_files, *summary.entrypoints])
    root = workspace.resolve()
    extras = [p.relative_to(root).as_posix() for p in _walk(root)]
    extras = [rel for rel in extras if _is_test_or_doc(rel) and rel not in code]
    total = sum(len(t) for t in code.values())
    out = dict(code)
    for rel, text in read_files(workspace, extras[:MAX_EXTRA_FILES]).items():
        if total + len(text) > FILES_MAX_TOTAL:
            break
        out[rel] = text
        total += len(text)
    return out


def model_parts(model: RookModel) -> dict[str, Any]:
    data = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {k: data[k] for k in ("actors", "actions", "state")}


def _rule_data(rule: Rule) -> dict[str, Any]:
    return rule.model_dump(mode="json", by_alias=True, exclude_none=True)


# What the critic is told about a flagged rule. Fixed text (no app output), so prompts stay reproducible.
ALREADY_BROKEN_NOTE = ("The engine saw this rule fail on the very first request to a fresh app. Either the "
                       "app already breaks it in one step, or the rule is wrong. Judge what it means; a human "
                       "decides whether to approve it.")


def _critic_rule_data(rule: Rule, check: SanityResult) -> dict[str, Any]:
    data = _rule_data(rule)
    if check.already_broken:
        data |= {"already_broken": True, "engine_note": ALREADY_BROKEN_NOTE}
    return data


def _verdict(rule_id: str, verdict: Literal["approve", "reject", "revise"], reason: str,
             by: Literal["engine", "critic"], revised: Rule | None = None,
             already_broken: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {"rule_id": rule_id, "verdict": verdict, "reason": redact_text(reason), "by": by}
    if revised is not None:
        data["revised"] = _rule_data(revised)
    if already_broken:
        data["already_broken"] = True
    return data


# --- the pipeline ---


class RulesPipeline:
    def __init__(
        self,
        client: AgentCaller,
        workspace: str | os.PathLike[str],
        *,
        model: RookModel,
        summary: RepoSummary,
        app: StartedApp,
        env: Mapping[str, str],
    ) -> None:
        """`model` is the Mapper's model (its rules are ignored); `app` is the running sandboxed app."""
        self.client = client
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")
        check_not_rook_repo(self.workspace)
        self.model = model.model_copy(update={"rules": []})
        self.summary = summary
        self.app = app
        self.env = dict(env)  # may hold user secrets: only handed to the executor, never logged
        self.result: RulesResult | None = None

    async def run(self) -> RulesResult:
        await self._publish("run.phase", RunPhase(phase="RULES"))
        files = lawmaker_files(self.workspace, self.summary)
        proposed = await self._lawmaker(files)
        await self._publish("rules.proposed", RulesProposed(rules=[_rule_data(r) for r in proposed]))

        checks = await self._sanity(proposed, "proposed")
        verdicts: list[dict[str, Any]] = []
        outcomes: dict[str, RuleOutcome] = {}
        passed: list[Rule] = []
        for rule, check in zip(proposed, checks, strict=True):
            if check.ok:
                passed.append(rule)
                continue
            outcomes[rule.id] = RuleOutcome(rule, rule, check, None, False, f"engine: {check.reason}")
            verdicts.append(_verdict(rule.id, "reject", check.reason, "engine"))
            await self._log("warn", f"Rule {rule.id} rejected by the engine: {redact_text(check.reason)}")

        engine_ok = {c.rule_id: c for c in checks}
        critic = await self._critic(passed, engine_ok, files) if passed else {}
        revisions: list[tuple[Rule, Rule, RuleVerdict]] = []
        taken = {r.id for r in passed}
        for rule in passed:
            verdict = critic.get(rule.id)
            check = engine_ok[rule.id]
            if verdict is None:
                seen = check.reason if check.already_broken else "holds on a fresh app"
                outcomes[rule.id] = RuleOutcome(rule, rule, check, None, True,
                                                f"{seen}; no critic verdict (left for the human)")
                continue
            verdicts.append(_verdict(rule.id, verdict.verdict, verdict.reason, "critic", verdict.revised,
                                     check.already_broken))
            if verdict.verdict == "approve":
                outcomes[rule.id] = RuleOutcome(rule, rule, check, verdict, True, f"critic: {verdict.reason}")
            elif verdict.verdict == "reject":
                outcomes[rule.id] = RuleOutcome(rule, rule, check, verdict, False, f"critic: {verdict.reason}")
            else:
                assert verdict.revised is not None  # enforced by RuleVerdict
                revised = verdict.revised.model_copy(update={
                    "status": "proposed", "evidence": verdict.revised.evidence or list(rule.evidence)})
                if revised.id != rule.id and revised.id in taken:
                    outcomes[rule.id] = RuleOutcome(
                        rule, revised, check, verdict, False,
                        f"critic revision uses the id {revised.id!r} of another rule")
                    verdicts.append(_verdict(revised.id, "reject", "duplicate rule id", "engine"))
                    continue
                taken.add(revised.id)
                revisions.append((rule, revised, verdict))

        if revisions:
            rechecks = await self._sanity([r for _, r, _ in revisions], "revised")
            for (rule, revised, verdict), check in zip(revisions, rechecks, strict=True):
                if check.ok:
                    outcomes[rule.id] = RuleOutcome(rule, revised, check, verdict, True,
                                                    f"critic revised it: {verdict.reason}")
                else:
                    outcomes[rule.id] = RuleOutcome(rule, revised, check, verdict, False,
                                                    f"the critic's revision failed the engine: {check.reason}")
                    verdicts.append(_verdict(revised.id, "reject", check.reason, "engine"))

        ordered = [outcomes[r.id] for r in proposed]
        await self._publish("rules.reviewed", RulesReviewed(verdicts=verdicts))
        model = self.model.model_copy(update={"rules": [o.rule for o in ordered if o.accepted]})
        model = RookModel.model_validate(model.model_dump(mode="json", by_alias=True, exclude_none=True))
        path = write_model(self.workspace, model, RULES_NOTE)
        accepted = sum(o.accepted for o in ordered)
        await self._log("info", f"{accepted}/{len(ordered)} proposed rules accepted; wrote rook/rook.yaml")
        self.result = RulesResult(model=model, outcomes=ordered, model_path=path)
        return self.result

    async def approve(self, rule_ids: Iterable[str]) -> RookModel:
        """Mark accepted rules as approved (after the human's answer, or auto mode), write rook.yaml and
        publish `rules.approved`. Only rules that passed the engine can be approved."""
        if self.result is None:
            raise RuntimeError("run() must finish before rules are approved")
        ids = list(dict.fromkeys(rule_ids))
        known = {r.id for r in self.result.model.rules}
        unknown = [i for i in ids if i not in known]
        if unknown:
            raise ValueError(f"not accepted rules, cannot approve: {unknown}")
        rules = [r.model_copy(update={"status": "approved"}) if r.id in ids else r
                 for r in self.result.model.rules]
        model = self.result.model.model_copy(update={"rules": rules})
        self.result.model_path = write_model(self.workspace, model, RULES_NOTE)
        self.result.model = model
        await self._publish("rules.approved", RulesApproved(rule_ids=ids))
        return model

    # agents

    async def _lawmaker(self, files: dict[str, str]) -> list[Rule]:
        try:
            result = await call_agent(self.client, "lawmaker", self.workspace,
                                      model=model_parts(self.model), files=files)
        except BOB_FAILURES as exc:
            raise RulesError(f"RULES: the Lawmaker failed: {exc}") from exc
        output = result.output
        assert isinstance(output, LawmakerOutput)
        return [r.model_copy(update={"status": "proposed"}) for r in output.rules]

    async def _critic(self, rules: list[Rule], checks: Mapping[str, SanityResult],
                      files: dict[str, str]) -> dict[str, RuleVerdict]:
        """The critic's verdicts by rule id ({} if the critic failed: the human then decides alone)."""
        try:
            result = await call_agent(self.client, "rule_critic", self.workspace,
                                      rules=[_critic_rule_data(r, checks[r.id]) for r in rules], files=files)
        except BOB_FAILURES as exc:
            await self._log("warn", f"The Rule Critic failed; the rules are left for the human: "
                                    f"{redact_text(str(exc)).splitlines()[0] if str(exc) else 'error'}")
            return {}
        output = result.output
        assert isinstance(output, RuleCriticOutput)
        ids = {r.id for r in rules}
        verdicts: dict[str, RuleVerdict] = {}
        for verdict in output.verdicts:
            if verdict.rule_id in ids and verdict.rule_id not in verdicts:
                verdicts[verdict.rule_id] = verdict
        ignored = sorted({v.rule_id for v in output.verdicts} - ids)
        if ignored:
            await self._log("warn", f"The Rule Critic judged unknown rule ids (ignored): {', '.join(ignored)}")
        missing = [r.id for r in rules if r.id not in verdicts]
        if missing:
            await self._log("warn", f"No critic verdict for: {', '.join(missing)} (left for the human)")
        return verdicts

    # engine

    async def _sanity(self, rules: list[Rule], label: str) -> list[SanityResult]:
        await self._publish("engine.started", EngineStarted(
            worker="judge", label=f"Sanity-checking {len(rules)} {label} rules on a fresh app"))
        results = await sanity_check(self.model, rules, self.app.base_url, env=self.env,
                                     transport=self.app.transport)
        good = sum(r.ok and not r.already_broken for r in results)
        flagged = sum(r.already_broken for r in results)
        summary = f"{good}/{len(results)} {label} rules hold on a fresh app"
        if flagged:
            summary += f" ({flagged} may already be broken)"
        await self._publish("engine.finished", EngineFinished(worker="judge", ok=good + flagged > 0,
                                                              summary=summary))
        return results

    # events

    async def _log(self, level: str, text: str) -> None:
        await self._publish("log", Log(level=level, text=text))  # type: ignore[arg-type]

    async def _publish(self, event_type: str, data: Any) -> None:
        await self.client.bus.publish(self.client.run_id, event_type, data)
