import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RunView } from "./RunView";
import { Transcript } from "./Transcript";
import { RulesCard } from "./cards/RulesCard";
import { PrLink } from "./cards/VerifyCard";
import { RunActionsContext, type RunActions } from "./cards/ui";
import type { ApiClient } from "@/lib/api";
import type { EventDataMap, EventType, RookEvent } from "@/lib/events";
import { minishopRun } from "@/lib/fixtures/minishop";
import { reduceEvents, type QuestionItem, type RulesItem, type RunState } from "@/lib/runStore";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);
const count = (s: string, needle: string) => s.split(needle).length - 1;

const RUN_ID = minishopRun[0]!.run_id;
const api: Pick<ApiClient, "answer" | "chat"> = { answer: async () => ({ ok: true }), chat: async () => ({ ok: true }) };

function tail<T extends EventType>(seq: number, type: T, data: EventDataMap[T], runId = RUN_ID): RookEvent {
  return { v: 1, seq, ts: "2026-09-26T09:00:00.000Z", run_id: runId, type, data } as RookEvent;
}

/** The recorded run with a pr.opened before run.finished (test mode only commits to a local branch). */
function withPr(url: string): RookEvent[] {
  const finished = minishopRun[minishopRun.length - 1]!;
  const body = minishopRun.slice(0, -1);
  const last = body[body.length - 1]!.seq;
  return [
    ...body,
    tail(last + 1, "pr.opened", { url, number: 88, branch: "rook/fix-cx-001" }),
    { ...finished, seq: last + 2 } as RookEvent,
  ];
}

function runView(state: RunState, guest = false) {
  return html(<RunView state={state} runId={RUN_ID} api={api} guest={guest} />);
}

function withActions(node: React.ReactElement, actions: Partial<RunActions> = {}) {
  const value: RunActions = { answer: async () => ({ status: "sent" }), guest: false, autoSeconds: 6, ...actions };
  return <RunActionsContext.Provider value={value}>{node}</RunActionsContext.Provider>;
}

describe("the recorded event log reaches the final state (AC)", () => {
  const state = reduceEvents(withPr("https://github.com/acme/minishop/pull/88"));
  const out = runView(state);

  it("ends with a View pull request button that links to GitHub", () => {
    expect(state.status).toBe("done");
    expect(out).toContain('href="https://github.com/acme/minishop/pull/88"');
    expect(out).toContain("View pull request");
    expect(out).toContain('rel="noopener noreferrer"');
    expect(out).toContain("PR #88 opened");
    expect(out).toContain("✓ FIX VERIFIED");
    expect(out).toContain('data-run-summary="done"');
    expect(out).toContain("Fixed and verified cx_001");
  });

  it("draws every card once and every question on its card", () => {
    for (const card of ["rules", "search", "counterexample", "fix", "verify"]) expect(count(out, `data-card="${card}"`)).toBe(1);
    expect(count(out, 'data-card="question"')).toBe(0);
    // All three questions were answered by the user in the recording.
    expect(out).toContain("Approved 1 rule");
    expect(out).toContain("Fix it");
    expect(out).toContain("Ship it");
    expect(count(out, "data-answered")).toBe(3);
    // Answered questions have no buttons left.
    for (const label of ["Fix it", "Ship it", "Not now", "Reject all"]) expect(out).not.toContain(`>${label}</button>`);
    expect(out).not.toContain('type="checkbox"');
    expect(out).not.toContain("data-countdown");
  });

  it("shows the counterexample, the shrink chips, the diff and the verify checks", () => {
    expect(out).toContain("Counterexample #001");
    expect(out).toContain("data-shrink");
    expect(out).toContain("customer: refund(amount=1)");
    expect(out).toContain("Reproduced 10/10 · real bug");
    expect(out).toContain("app.py : 214");
    expect(count(out, 'data-diff="add"')).toBe(1);
    expect(count(out, 'data-diff="remove"')).toBe(2);
    for (const check of ["replay", "project_tests", "regression_test", "fresh_search"]) expect(out).toContain(`data-check="${check}"`);
    expect(out).toContain("Fix committed to");
    expect(out).toContain("5bf3ec3");
    expect(out).not.toContain("5bf3ec34f");
  });

  it("without pr.opened (the plain recording) there is the commit line and no PR button", () => {
    const plain = runView(reduceEvents(minishopRun));
    expect(plain).toContain("data-committed");
    expect(plain).not.toContain("View pull request");
    expect(plain).not.toContain("data-pr");
  });

  it("a PR URL that isn't https://github.com/ is plain text, not a link", () => {
    for (const url of ["javascript:alert(1)", "https://github.com.evil.test/x", "http://github.com/a/b/pull/1"]) {
      const bad = html(<PrLink url={url} number={1} />);
      expect(bad).not.toContain("<a");
      expect(bad).not.toContain("href");
      expect(bad).toContain("data-pr-text");
    }
    const good = html(<PrLink url="https://github.com/a/b/pull/1" number={1} />);
    expect(good).toContain('<a href="https://github.com/a/b/pull/1"');
  });
});

describe("already_broken on the RulesCard", () => {
  const i = minishopRun.findIndex((e) => e.type === "question.answered");
  const state = reduceEvents(minishopRun.slice(0, i));
  const rules = state.items.find((x): x is RulesItem => x.kind === "rules")!;
  const q = state.items.find((x): x is QuestionItem => x.kind === "question")!;
  const out = html(withActions(<RulesCard item={rules} question={q} />));

  function ruleRow(id: string): string {
    const start = out.indexOf(`data-rule="${id}"`);
    const end = out.indexOf("data-rule=", start + 1);
    return out.slice(start, end === -1 ? undefined : end);
  }

  it("reads 'possibly already broken', and its box is not ticked", () => {
    const flagged = ruleRow("admin_export_forbidden_for_customer");
    expect(flagged).toContain("Possibly already broken");
    expect(flagged).toContain("needs your explicit OK");
    expect(flagged).toContain('type="checkbox"');
    expect(flagged).not.toContain("checked");
  });

  it("pre-ticks the other accepted rules, gives the rejected one no box, and counts the selection", () => {
    expect(ruleRow("refunded_total_le_paid")).toContain('checked=""');
    const rejected = ruleRow("buy_response_status_paid");
    expect(rejected).not.toContain('type="checkbox"');
    expect(rejected).toContain("Rejected");
    expect(count(out, 'checked=""')).toBe(8);
    expect(out).toContain("Approve 8 rules");
    expect(out).toContain("Reject all");
    expect(out).toContain("Needs your OK");
    expect(out).not.toContain("Approve all");
  });

  it("shows a guest countdown only in guest mode", () => {
    expect(out).not.toContain("data-countdown");
    const guest = html(withActions(<RulesCard item={rules} question={q} />, { guest: true }));
    expect(guest).toContain("data-countdown");
    expect(guest).toContain("in 6s");
  });

  it("for a guest, pre-ticks only the demo's featured rule; a signed-in user still gets every rule", () => {
    const payload = q.payload as { rules: Array<Record<string, unknown>> };
    const featured = { ...q, payload: { rules: payload.rules.map((r) => ({ ...r, featured: r.id === "refunded_total_le_paid" })) } };
    const guest = html(withActions(<RulesCard item={rules} question={featured} />, { guest: true }));
    expect(count(guest, 'checked=""')).toBe(1);
    expect(guest).toContain("Approve 1 rule");
    expect(guest).toContain("Demo rule");
    const user = html(withActions(<RulesCard item={rules} question={featured} />));
    expect(count(user, 'checked=""')).toBe(8);
  });
});

describe("questions without a card", () => {
  function events(...list: Array<[EventType, unknown]>): RookEvent[] {
    return list.map(([type, data], i) => ({ v: 1, seq: i + 1, ts: "2026-09-26T09:00:00.000Z", run_id: "r_x", type, data }) as RookEvent);
  }

  it("a setup value is a masked input with no countdown, even for a guest", () => {
    const state = reduceEvents(
      events(["question.asked", { question_id: "q_s", kind: "setup_value", text: "Your app needs PAYMENT_API_KEY.", options: [], payload: { name: "PAYMENT_API_KEY", secret: true } }]),
    );
    const out = html(<RunView state={state} runId="r_x" api={api} guest />);
    expect(out).toContain('data-card="question"');
    expect(out).toContain('type="password"');
    expect(out).toContain('autoComplete="off"');
    expect(out).not.toContain("data-countdown");
  });

  it("an answered setup value reads 'NAME provided' and never the value", () => {
    const state = reduceEvents(
      events(
        ["question.asked", { question_id: "q_s", kind: "setup_value", text: "Needs KEY", options: [], payload: { name: "KEY", secret: true } }],
        ["question.answered", { question_id: "q_s", answer: { name: "KEY", provided: true }, by: "user" }],
      ),
    );
    const out = html(<Transcript state={state} />);
    expect(out).toContain("KEY provided");
    expect(out).not.toContain("<input");
  });

  it("a menu is one button per option; an auto answer is marked (auto)", () => {
    const state = reduceEvents(
      events(
        ["question.asked", { question_id: "q_m", kind: "menu", text: "What next?", options: [{ id: "retry", label: "Retry" }, { id: "stop", label: "Stop" }], payload: {} }],
      ),
    );
    const open = html(withActions(<Transcript state={state} />));
    expect(open).toContain(">Retry</button>");
    expect(open).toContain(">Stop</button>");
    const answered = reduceEvents(events(["question.answered", { question_id: "q_m", answer: "stop", by: "auto" }]).map((e) => ({ ...e, seq: 2 }) as RookEvent), state);
    const out = html(<Transcript state={answered} />);
    expect(out).toContain("Stop");
    expect(out).toContain("(auto)");
    expect(out).not.toContain("<button");
  });

  it("an open fix question shows a guest countdown on the FixCard", () => {
    const i = minishopRun.findIndex((e) => e.type === "question.asked" && e.data.kind === "fix");
    const state = reduceEvents(minishopRun.slice(0, i + 1));
    const out = runView(state, true);
    const fix = out.slice(out.indexOf('data-card="fix"'));
    expect(fix).toContain(">Fix it</button>");
    expect(fix).toContain(">Not now</button>");
    expect(fix).toContain("data-countdown");
  });
});

describe("untrusted text (XSS and control characters)", () => {
  const XSS = '<script>alert(1)</script><img src=x onerror="alert(2)">';
  const CTRL = "\x1b[31mred\x1b]0;title\x07\x00\u009b";
  const T = `${XSS}${CTRL}`;

  function hostile(): RunState {
    const list: Array<[EventType, unknown]> = [
      ["run.created", { repo: { kind: "demo", ref: "x", name: T }, request: T, options: { auto: false, budget: 1 } }],
      ["log", { level: "warn", text: T }],
      ["chat.message", { role: "user", text: T }],
      ["chat.message", { role: "guide", text: T }],
      ["rules.proposed", { rules: [{ id: T, text: T, evidence: [T] }] }],
      ["rules.reviewed", { verdicts: [{ rule_id: T, verdict: "reject", reason: T, by: "critic" }] }],
      ["question.asked", { question_id: "q_r", kind: "approve_rules", text: T, options: [{ id: "all", label: T }], payload: { rules: [{ id: T, text: T, accepted: true, reason: T, already_broken: true }] } }],
      ["search.progress", { sequences: 10, per_sec: 5, rules: { [T]: "broken" } }],
      ["violation.found", { violation_id: "v1", rule_id: T, steps_count: 3, observed: { [T]: T } }],
      ["counterexample.saved", { cx_id: T, rule_id: T, rule_text: T, steps: [{ action: T, actor: T, params: { [T]: T } }], observed: { [T]: T }, expected: T, reproduced: T, flaky: false, test_path: T }],
      ["diagnosis.ready", { cx_id: T, file: T, line: 1, explanation: T, reviewed: true }],
      ["question.asked", { question_id: "q_f", kind: "fix", text: T, options: [{ id: "yes", label: T }, { id: "no", label: T }], payload: { cx_id: T } }],
      ["fix.ready", { cx_id: T, files: [T], diff: `-${T}\n+${T}`, reviewed: false }],
      ["verify.step", { cx_id: T, check: "replay", status: "passed", detail: T }],
      ["verify.done", { cx_id: T, verified: false, summary: T }],
      ["fix.committed", { cx_id: T, branch: T, commit: T, files: [T] }],
      ["pr.opened", { url: `javascript:alert(3)//${T}`, number: 1, branch: T }],
      ["question.asked", { question_id: "q_m", kind: "menu", text: T, options: [{ id: T, label: T }], payload: {} }],
      ["question.asked", { question_id: "q_v", kind: "setup_value", text: T, options: [], payload: { name: T, secret: false } }],
      ["agent.finished", { agent: "scout", call_id: "c1", ok: true, summary: T, cost: 0, recorded: false }],
      ["engine.finished", { worker: "runner", ok: false, summary: T }],
      ["run.finished", { status: "failed", summary: T }],
    ];
    return reduceEvents(list.map(([type, data], i) => ({ v: 1, seq: i + 1, ts: "2026-09-26T09:00:00.000Z", run_id: "r_h", type, data }) as RookEvent));
  }

  const out = html(<RunView state={hostile()} runId="r_h" api={api} />);

  it("renders the payloads as text, never as markup", () => {
    expect(out).not.toContain("<script");
    expect(out).not.toContain("<img");
    expect(out).not.toContain("onerror=\"alert");
    expect(out).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(out).not.toMatch(/href="javascript:/i);
    // The only links are the sidebar's own app paths; no payload ever becomes a link.
    const anchors = out.match(/<a [^>]*>/g) ?? [];
    expect(anchors.length).toBeGreaterThan(0);
    for (const a of anchors) expect(a).toMatch(/href="\/(runs|counterexamples|rules|repositories|login)?"/);
  });

  it("drops every control character", () => {
    // eslint-disable-next-line no-control-regex
    expect(out).not.toMatch(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/);
    expect(out).toContain("[31mred]0;title");
  });

  it("the card for every item type is there (nothing was skipped)", () => {
    for (const card of ["rules", "search", "counterexample", "fix", "verify", "question"]) expect(out).toContain(`data-card="${card}"`);
    expect(out).toContain('data-chat="user"');
    expect(out).toContain('data-chat="guide"');
    expect(out).toContain('data-log="warn"');
  });
});

describe("the run's final card (04 §3.6)", () => {
  it("shows a success card for a verified fix", () => {
    const out = runView(reduceEvents(minishopRun));
    expect(out).toContain('data-outcome="verified"');
    expect(out).toContain("Fixed and verified</p>");
    expect(out).toContain("border-good bg-good-soft");
  });

  it("shows a calm warn card (not red) for the unverified ending, with the server's summary", () => {
    const cut = minishopRun.findIndex((e) => e.type === "verify.done");
    const last = minishopRun[cut - 1]!.seq;
    const summary = "Found and saved cx_001; the fix for rule refund_le_paid was written and the exact replay now passes. NOT verified.";
    const out = runView(
      reduceEvents([
        ...minishopRun.slice(0, cut),
        tail(last + 1, "verify.done", { cx_id: "cx_001", verified: false, summary: "3/4 checks passed; failed: fresh_search" }),
        tail(last + 2, "run.finished", { status: "done", summary }),
      ]),
    );
    expect(out).toContain('data-run-summary="done"');
    expect(out).toContain('data-outcome="unverified"');
    expect(out).toContain("border-warn bg-warn-soft");
    expect(out).toContain("Found and saved cx_001; the fix for rule refund_le_paid was written");
    expect(out).toMatch(/data-pill="warn"[^>]*>! Not verified/);
    expect(out).not.toContain("border-bad bg-bad-soft px-4");
  });
});
