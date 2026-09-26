import { describe, expect, it } from "vitest";
import type { EventDataMap, EventType, RookEvent } from "./events";
import { minishopRun } from "./fixtures/minishop";
import {
  brokenRules,
  initialRunState,
  pendingQuestions,
  reduceEvents,
  reduceRun,
  workingAgents,
  type AgentItem,
  type CounterexampleItem,
  type EngineItem,
  type FixItem,
  type RulesItem,
  type SearchItem,
  type TranscriptItem,
  type VerifyItem,
} from "./runStore";

function ofKind<K extends TranscriptItem["kind"]>(items: TranscriptItem[], kind: K) {
  return items.filter((i): i is Extract<TranscriptItem, { kind: K }> => i.kind === kind);
}

let nextSeq = 1;
function ev<T extends EventType>(type: T, data: EventDataMap[T], seq = nextSeq++, runId = "r_t"): RookEvent {
  return { v: 1, seq, ts: "2026-09-26T08:00:00.000Z", run_id: runId, type, data } as RookEvent;
}

describe("runStore over the recorded minishop run", () => {
  const state = reduceEvents(minishopRun);

  it("ends done, in DONE, after all 18 phases", () => {
    expect(state.status).toBe("done");
    expect(state.summary).toMatch(/Fixed and verified cx_001/);
    expect(state.runId).toBe(minishopRun[0]!.run_id);
    expect(state.lastSeq).toBe(369);
    expect(state.phase).toBe("DONE");
    expect(state.phases).toEqual([
      "PREPARE", "SCOUT", "START_APP", "MAP", "RULES", "APPROVE", "DESIGN", "SEARCH", "SHRINK", "REPLAY",
      "SAVE", "DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE",
    ]);
    expect(state.created?.repo.name).toBe("minishop");
    expect(state.repoSummary?.framework).toBe("fastapi");
    expect(state.sandbox?.base_url_redacted).toBe("http://minishop.test");
    expect(state.model?.actions.length).toBeGreaterThan(0);
  });

  it("collapses every agent row with its summary and cost", () => {
    const agents = ofKind(state.items, "agent");
    expect(agents).toHaveLength(12);
    expect(workingAgents(state)).toEqual([]);
    const scout = agents.find((a) => a.agent === "scout") as AgentItem;
    expect(scout.status).toBe("done");
    expect(scout.recorded).toBe(true);
    expect(scout.cost).toBeCloseTo(0.03818);
    expect(scout.finishedAt).not.toBeNull();
    // This recording's Rule Critic call failed (ok=false): the row shows ✗.
    expect(agents.find((a) => a.agent === "rule_critic")?.status).toBe("failed");
    // Two surgeon calls (regression test, then the fix) are two rows.
    expect(agents.filter((a) => a.agent === "surgeon")).toHaveLength(2);
  });

  it("opens one engine row per engine.started and closes them all", () => {
    const engines = ofKind(state.items, "engine");
    expect(engines).toHaveLength(14);
    expect(engines.every((e) => e.status !== "working")).toBe(true);
    const judge = engines.find((e) => e.summary === "rule refunded_total_le_paid broken at step 4") as EngineItem;
    expect(judge.status).toBe("failed");
    // The verify fresh search: started at seq 132, its label follows engine.progress.
    const fresh = engines.find((e) => e.key === "engine:132") as EngineItem;
    expect(fresh).toMatchObject({ worker: "runner", status: "done", pct: 100, count: 1495 });
    expect(fresh.summary).toBe("1500 sequences in 23.6s (63/s)");
  });

  it("builds the rules card: proposals, the engine's rejection and the approval", () => {
    const [rules] = ofKind(state.items, "rules") as RulesItem[];
    expect(rules!.rules).toHaveLength(10);
    expect(rules!.verdicts["buy_response_status_paid"]?.[0]).toMatchObject({ verdict: "reject", by: "engine" });
    expect(rules!.approvedIds).toEqual(["refunded_total_le_paid"]);
    expect(state.approvedRuleIds).toEqual(["refunded_total_le_paid"]);
  });

  it("answers all three questions", () => {
    const questions = ofKind(state.items, "question");
    expect(questions.map((q) => q.questionKind)).toEqual(["approve_rules", "fix", "pr"]);
    expect(questions.every((q) => q.answered && q.answeredBy === "user")).toBe(true);
    expect(questions[0]!.answer).toEqual(["refunded_total_le_paid"]);
    expect(pendingQuestions(state)).toEqual([]);
  });

  it("keeps the SEARCH stats apart from the fresh search of VERIFY", () => {
    const searches = ofKind(state.items, "search") as SearchItem[];
    expect(searches).toHaveLength(1);
    expect(searches[0]!.rules).toEqual({ refunded_total_le_paid: "broken" });
    expect(brokenRules(state)).toEqual(["refunded_total_le_paid"]);
    const [verify] = ofKind(state.items, "verify") as VerifyItem[];
    expect(verify!.freshSearch?.sequences).toBeGreaterThan(searches[0]!.sequences);
  });

  it("builds one counterexample card, updated by the second save with the test path", () => {
    const cards = ofKind(state.items, "counterexample") as CounterexampleItem[];
    expect(cards).toHaveLength(1);
    const cx = cards[0]!;
    expect(cx.violationId).toBe("v_79d91d72");
    expect(cx.stepCounts).toEqual([4]); // 4 -> 4: no shorter sequence exists
    expect(cx.saved?.cx_id).toBe("cx_001");
    expect(cx.saved?.reproduced).toBe("10/10");
    expect(cx.saved?.test_path).toBe("test_rook_cx_001.py");
    expect(cx.observed).toEqual({ paid: 1, refunded_total: 2, status: "paid", shipped: false });
  });

  it("builds the fix and verify cards", () => {
    const [fix] = ofKind(state.items, "fix") as FixItem[];
    expect(fix!.diagnosis).toMatchObject({ file: "app.py", line: 214, reviewed: true });
    expect(fix!.fix?.files).toEqual(["app.py"]);
    const verifies = ofKind(state.items, "verify") as VerifyItem[];
    expect(verifies).toHaveLength(1);
    const verify = verifies[0]!;
    expect(Object.keys(verify.checks).sort()).toEqual(["fresh_search", "project_tests", "regression_test", "replay"]);
    expect(Object.values(verify.checks).every((c) => c.status === "passed")).toBe(true);
    expect(verify.done).toEqual({ verified: true, summary: "4/4 checks passed" });
    expect(verify.committed?.branch).toBe("rook/fix-cx-001");
    expect(verify.pr).toBeNull();
  });

  it("tracks coins and keeps every log line", () => {
    const lastCost = [...minishopRun].reverse().find((e) => e.type === "cost.update")!;
    expect(state.coins).toBe((lastCost.data as EventDataMap["cost.update"]).coins_total);
    expect(ofKind(state.items, "log")).toHaveLength(11);
  });

  it("indexes every item by key", () => {
    state.items.forEach((item, i) => expect(state.index[item.key]).toBe(i));
    expect(new Set(state.items.map((i) => i.key)).size).toBe(state.items.length);
  });
});

describe("runStore resume and de-duplication", () => {
  const full = reduceEvents(minishopRun);

  it("ignores an event it has already applied (same state object)", () => {
    const once = reduceEvents(minishopRun.slice(0, 50));
    expect(reduceRun(once, minishopRun[49]!)).toBe(once);
    expect(reduceRun(once, minishopRun[10]!)).toBe(once);
  });

  it.each([1, 45, 81, 115, 200, 368])("a reconnect at seq %i with a replayed tail gives the same final state", (cut) => {
    const before = reduceEvents(minishopRun.slice(0, cut));
    const resumed = reduceEvents(minishopRun.slice(Math.max(0, cut - 20)), before);
    expect(resumed).toEqual(full);
  });

  it("never mutates the previous state", () => {
    const before = reduceEvents(minishopRun.slice(0, 100));
    const snapshot = structuredClone(before);
    reduceEvents(minishopRun.slice(100), before);
    expect(before).toEqual(snapshot);
  });

  it("ignores events of another run", () => {
    const s = reduceEvents(minishopRun.slice(0, 5));
    expect(reduceRun(s, ev("log", { level: "info", text: "x" }, 6, "r_other"))).toBe(s);
  });
});

describe("runStore edge cases", () => {
  it("creates an agent row when the stream starts mid-call", () => {
    const s = reduceEvents([ev("agent.progress", { agent: "scout", call_id: "c1", detail: "reading app.py" })]);
    expect(s.items).toEqual([expect.objectContaining({ kind: "agent", agent: "scout", status: "working", detail: "reading app.py" })]);
    expect(workingAgents(s)).toHaveLength(1);
  });

  it("attaches pr.opened to the verify card", () => {
    const s = reduceEvents([
      ev("run.phase", { phase: "VERIFY" }),
      ev("verify.done", { cx_id: "cx_001", verified: true, summary: "ok" }),
      ev("pr.opened", { url: "https://github.com/o/r/pull/88", number: 88, branch: "rook/fix-cx-001" }),
    ]);
    const [verify] = ofKind(s.items, "verify") as VerifyItem[];
    expect(verify!.pr?.number).toBe(88);
    expect(s.pr?.url).toBe("https://github.com/o/r/pull/88");
  });

  it("adds a shrink chip per new length only", () => {
    const s = reduceEvents([
      ev("violation.found", { violation_id: "v1", rule_id: "r", steps_count: 12, observed: {} }),
      ev("shrink.step", { violation_id: "v1", steps_count: 8 }),
      ev("shrink.step", { violation_id: "v1", steps_count: 8 }),
      ev("shrink.step", { violation_id: "v1", steps_count: 5 }),
      ev("shrink.step", { violation_id: "v1", steps_count: 3 }),
    ]);
    expect((ofKind(s.items, "counterexample")[0] as CounterexampleItem).stepCounts).toEqual([12, 8, 5, 3]);
  });

  it("gives a second verification of the same cx its own card", () => {
    const s = reduceEvents([
      ev("run.phase", { phase: "VERIFY" }),
      ev("verify.done", { cx_id: "cx_001", verified: false, summary: "replay still breaks" }),
      ev("run.phase", { phase: "DIAGNOSE" }),
      ev("run.phase", { phase: "VERIFY" }),
      ev("verify.done", { cx_id: "cx_001", verified: true, summary: "4/4" }),
    ]);
    expect((ofKind(s.items, "verify") as VerifyItem[]).map((v) => v.done?.verified)).toEqual([false, true]);
  });

  it("shows user and guide chat in order and records a pending question", () => {
    const s = reduceEvents([
      ev("chat.message", { role: "user", text: "why refunds?" }),
      ev("chat.message", { role: "guide", text: "The Strategist guessed so." }),
      ev("question.asked", { question_id: "q1", kind: "fix", text: "Fix it?", options: [{ id: "yes", label: "Fix it" }], payload: null }),
    ]);
    expect(ofKind(s.items, "chat").map((c) => c.role)).toEqual(["user", "guide"]);
    expect(pendingQuestions(s).map((q) => q.questionId)).toEqual(["q1"]);
    expect(s.status).toBe("running");
  });

  it("starts idle", () => {
    expect(initialRunState.status).toBe("idle");
  });
});
