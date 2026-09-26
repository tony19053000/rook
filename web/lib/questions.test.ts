import { describe, expect, it } from "vitest";
import { ApiError, createApiClient } from "./api";
import type { EventDataMap, EventType, RookEvent } from "./events";
import { minishopRun } from "./fixtures/minishop";
import {
  attachQuestions,
  chatText,
  confirmChoices,
  describeAnswer,
  describeRulesAnswer,
  failureOutcome,
  guestAutoAnswer,
  guestRulesAnswer,
  initialSelection,
  questionUi,
  ruleRows,
  rulesApproval,
  sendAnswer,
  sendChat,
  valueQuestion,
} from "./questions";
import { reduceEvents, type QuestionItem, type RulesItem } from "./runStore";

let nextSeq = 1;
function ev<T extends EventType>(type: T, data: EventDataMap[T]): RookEvent {
  return { v: 1, seq: nextSeq++, ts: "2026-09-26T08:00:00.000Z", run_id: "r_q", type, data } as RookEvent;
}

function question(patch: Partial<QuestionItem>): QuestionItem {
  return {
    kind: "question",
    key: "q:q1",
    questionId: "q1",
    questionKind: "menu",
    text: "?",
    options: [],
    payload: null,
    answered: false,
    answer: null,
    answeredBy: null,
    ...patch,
  };
}

/** The recorded run up to (not including) the answer of its approve_rules question. */
function atApproval() {
  const i = minishopRun.findIndex((e) => e.type === "question.answered");
  const state = reduceEvents(minishopRun.slice(0, i));
  const rules = state.items.find((x): x is RulesItem => x.kind === "rules")!;
  const q = state.items.find((x): x is QuestionItem => x.kind === "question")!;
  return { state, rules, q };
}

function mockApi(respond: (path: string, body: unknown) => Response = () => Response.json({ ok: true })) {
  const calls: Array<{ method: string; path: string; body: unknown }> = [];
  const api = createApiClient({
    baseUrl: "https://api.test",
    fetch: async (input, init) => {
      const path = String(input).replace("https://api.test/api/v1", "");
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method: init?.method ?? "GET", path, body });
      return respond(path, body);
    },
  });
  return { api, calls };
}

describe("already_broken rules (the recorded approve_rules question)", () => {
  const { rules, q } = atApproval();
  const rows = ruleRows(rules, q);

  it("merges the proposal, the verdicts and the payload", () => {
    expect(q.questionKind).toBe("approve_rules");
    expect(questionUi(q)).toBe("rules");
    expect(rows).toHaveLength(10);
    const flagged = rows.find((r) => r.id === "admin_export_forbidden_for_customer")!;
    expect(flagged.alreadyBroken).toBe(true);
    expect(flagged.status).toBe("accepted");
    expect(rows.find((r) => r.id === "buy_response_status_paid")!.status).toBe("rejected");
    expect(rows[0]!.sources[0]).toMatch(/^app\.py:214-216/);
    expect(rows.every((r) => r.approved === null)).toBe(true);
  });

  it("never pre-selects a flagged rule or a rejected one", () => {
    const selected = initialSelection(rows);
    expect(selected).toHaveLength(8);
    expect(selected).not.toContain("admin_export_forbidden_for_customer");
    expect(selected).not.toContain("buy_response_status_paid");
  });

  it("approves a flagged rule only when it is ticked explicitly, and always as an id list", () => {
    const withFlag = rulesApproval(rows, [...initialSelection(rows), "admin_export_forbidden_for_customer"]);
    expect(withFlag).toContain("admin_export_forbidden_for_customer");
    expect(withFlag).toHaveLength(9);
    // A rejected rule can't be smuggled in by id, and the order follows the card.
    expect(rulesApproval(rows, ["buy_response_status_paid", "order_paid_non_negative", "refunded_total_le_paid"])).toEqual([
      "refunded_total_le_paid",
      "order_paid_non_negative",
    ]);
    expect(rulesApproval(rows, [])).toEqual([]);
  });

  it("the guest auto-answer is the default selection, never 'all' and never the flagged rule", () => {
    const auto = guestRulesAnswer(rows);
    expect(Array.isArray(auto)).toBe(true);
    expect(auto).not.toContain("admin_export_forbidden_for_customer");
    expect(auto).toEqual(initialSelection(rows));
    expect(guestAutoAnswer(q)).toBeNull();
    // Only a flagged rule left: nothing is auto-approved, a person decides.
    const onlyFlagged = rows.filter((r) => r.alreadyBroken);
    expect(guestRulesAnswer(onlyFlagged)).toBeNull();
  });

  it("marks the approval once answered (from rules.approved, or from the answer)", () => {
    const answered = { ...q, answered: true, answer: ["refunded_total_le_paid"], answeredBy: "user" as const };
    const byAnswer = ruleRows(rules, answered);
    expect(byAnswer.filter((r) => r.approved).map((r) => r.id)).toEqual(["refunded_total_le_paid"]);
    const final = reduceEvents(minishopRun.slice(0, minishopRun.findIndex((e) => e.type === "rules.approved") + 1));
    const card = final.items.find((x): x is RulesItem => x.kind === "rules")!;
    expect(ruleRows(card, null).filter((r) => r.approved).map((r) => r.id)).toEqual(["refunded_total_le_paid"]);
    // "all" (e.g. an older client or an auto answer) never counts the rejected rule.
    expect(ruleRows(rules, { ...answered, answer: "all" }).find((r) => r.status === "rejected")!.approved).toBe(false);
  });

  it("a critic verdict with already_broken flags the rule too", () => {
    nextSeq = 1;
    const state = reduceEvents([
      ev("rules.proposed", { rules: [{ id: "r1", text: "one" }, { id: "r2", text: "two" }] }),
      ev("rules.reviewed", { verdicts: [{ rule_id: "r1", verdict: "approve", reason: "ok", by: "critic", already_broken: true }] }),
      ev("rules.reviewed", { verdicts: [{ rule_id: "r2", verdict: "revise", reason: "clearer", by: "critic", revised: { text: "two (revised)" } }] }),
    ]);
    const rows = ruleRows(state.items[0] as RulesItem, null);
    expect(rows[0]).toMatchObject({ alreadyBroken: true, status: "accepted", reason: "critic: ok" });
    expect(rows[1]).toMatchObject({ text: "two (revised)", status: "accepted" });
    expect(initialSelection(rows)).toEqual(["r2"]);
  });
});

describe("question prompts", () => {
  it("picks the prompt like the TUI", () => {
    const opts = [{ id: "yes", label: "Fix it" }, { id: "no", label: "Not now" }];
    expect(questionUi(question({ questionKind: "fix", options: opts }))).toBe("confirm");
    expect(questionUi(question({ questionKind: "pr", options: opts }))).toBe("confirm");
    expect(questionUi(question({ questionKind: "menu", options: opts }))).toBe("menu");
    expect(questionUi(question({ questionKind: "setup_value" }))).toBe("value");
    // approve_rules is always the rules prompt, so its "all" option is never a button.
    expect(questionUi(question({ questionKind: "approve_rules", options: [{ id: "all", label: "Approve" }] }))).toBe("rules");
    expect(confirmChoices(question({ options: opts }))).toEqual(opts);
    expect(confirmChoices(question({}))).toEqual([{ id: "yes", label: "Yes" }, { id: "no", label: "No" }]);
  });

  it("auto-answers only fix and pr in guest mode, never a setup value or a menu", () => {
    const opts = [{ id: "yes", label: "Ship it" }, { id: "no", label: "Not now" }];
    expect(guestAutoAnswer(question({ questionKind: "pr", options: opts }))).toBe("yes");
    expect(guestAutoAnswer(question({ questionKind: "setup_value", payload: { name: "API_KEY", secret: true } }))).toBeNull();
    expect(guestAutoAnswer(question({ questionKind: "menu", options: opts }))).toBeNull();
  });

  it("masks setup values unless the payload says secret: false", () => {
    expect(valueQuestion(question({ payload: { name: "PAYMENT_API_KEY", secret: true } }))).toEqual({ name: "PAYMENT_API_KEY", secret: true });
    expect(valueQuestion(question({ payload: { name: "PORT", secret: false } })).secret).toBe(false);
    expect(valueQuestion(question({ payload: null })).secret).toBe(true);
  });

  it("describes answers without ever showing a secret", () => {
    const opts = [{ id: "yes", label: "Fix it" }];
    expect(describeAnswer("yes", opts)).toBe("Fix it");
    expect(describeAnswer(true)).toBe("Yes");
    expect(describeAnswer({ name: "API_KEY", provided: true })).toBe("API_KEY provided");
    expect(describeAnswer(["r1", "r2"])).toBe("Approve r1, r2");
    expect(describeAnswer("<b>\x1b[2J")).toBe("<b>[2J");
    expect(describeRulesAnswer(["a"])).toBe("Approved 1 rule");
    expect(describeRulesAnswer(["a", "b"])).toBe("Approved 2 rules");
    expect(describeRulesAnswer("none")).toBe("Rejected all rules");
  });

  it("attaches approve_rules, fix and pr to their cards in the recorded run", () => {
    const state = reduceEvents(minishopRun);
    const { byCard, attached } = attachQuestions(state.items);
    const questions = state.items.filter((x): x is QuestionItem => x.kind === "question");
    expect(questions.map((q) => q.questionKind)).toEqual(["approve_rules", "fix", "pr"]);
    expect(attached.size).toBe(3);
    const kinds = [...byCard.keys()].map((k) => state.items[state.index[k]!]!.kind);
    expect(kinds).toEqual(["rules", "fix", "verify"]);
  });

  it("leaves a setup value or a menu as its own card", () => {
    nextSeq = 1;
    const state = reduceEvents([
      ev("question.asked", { question_id: "q_s", kind: "setup_value", text: "Your app needs KEY.", options: [], payload: { name: "KEY", secret: true } }),
      ev("question.asked", { question_id: "q_m", kind: "menu", text: "What next?", options: [{ id: "retry", label: "Retry" }], payload: {} }),
    ]);
    expect(attachQuestions(state.items).attached.size).toBe(0);
  });
});

describe("answer payloads (POST /runs/{id}/answers)", () => {
  it("sends the explicit id list for a rules approval", async () => {
    const { rules, q } = atApproval();
    const rows = ruleRows(rules, q);
    const m = mockApi();
    const outcome = await sendAnswer(m.api, "r_1", q.questionId, rulesApproval(rows, initialSelection(rows)));
    expect(outcome).toEqual({ status: "sent" });
    expect(m.calls).toHaveLength(1);
    expect(m.calls[0]!.method).toBe("POST");
    expect(m.calls[0]!.path).toBe("/runs/r_1/answers");
    const body = m.calls[0]!.body as { question_id: string; answer: unknown };
    expect(body.question_id).toBe(q.questionId);
    expect(Array.isArray(body.answer)).toBe(true);
    expect(body.answer).toHaveLength(8);
    expect(body.answer).not.toContain("admin_export_forbidden_for_customer");
    expect(JSON.stringify(body)).not.toContain('"all"');
  });

  it("sends option ids for confirm and menu, and the raw string for a setup value", async () => {
    const m = mockApi();
    await sendAnswer(m.api, "r 1", "q_fix", "yes");
    await sendAnswer(m.api, "r 1", "q_val", "s3cret value");
    expect(m.calls.map((c) => c.path)).toEqual(["/runs/r%201/answers", "/runs/r%201/answers"]);
    expect(m.calls.map((c) => c.body)).toEqual([
      { question_id: "q_fix", answer: "yes" },
      { question_id: "q_val", answer: "s3cret value" },
    ]);
  });

  it("turns {ok: false} and 4xx errors into plain messages", async () => {
    const closed = await sendAnswer(mockApi(() => Response.json({ ok: false })).api, "r", "q", "yes");
    expect(closed.status).toBe("closed");
    const cases: Array<[number, "closed" | "error", RegExp]> = [
      [409, "closed", /Already answered/],
      [404, "closed", /no longer available/],
      [400, "error", /didn't accept/],
      [401, "error", /Sign in/],
      [403, "error", /access/],
      [413, "error", /too long/],
      [429, "error", /Too many requests/],
      [500, "error", /HTTP 500/],
    ];
    for (const [status, kind, message] of cases) {
      const detail = "<script>alert(1)</script>";
      const outcome = await sendAnswer(mockApi(() => Response.json({ detail }, { status })).api, "r", "q", "yes");
      expect(outcome.status).toBe(kind);
      if (outcome.status !== "sent") {
        expect(outcome.message).toMatch(message);
        expect(outcome.message).not.toContain("script"); // the server's text is never echoed
      }
    }
    expect(failureOutcome(new TypeError("fetch failed"))).toEqual({
      status: "error",
      message: "Couldn't reach the server. Check your connection and try again.",
    });
    expect(failureOutcome(new ApiError(409, "x"), "chat").status).toBe("closed");
  });
});

describe("chat (POST /runs/{id}/chat)", () => {
  it("sends trimmed text and refuses empty or too long text without a call", async () => {
    const m = mockApi();
    expect(await sendChat(m.api, "r_1", "  why is rule 2 broken?  ")).toEqual({ status: "sent" });
    expect(m.calls).toEqual([{ method: "POST", path: "/runs/r_1/chat", body: { text: "why is rule 2 broken?" } }]);
    expect((await sendChat(m.api, "r_1", "   ")).status).toBe("error");
    expect((await sendChat(m.api, "r_1", "x".repeat(2001))).status).toBe("error");
    expect(m.calls).toHaveLength(1);
    expect(chatText("x".repeat(2000))).toEqual({ text: "x".repeat(2000) });
  });

  it("explains a finished run and server errors", async () => {
    const notLive = await sendChat(mockApi(() => Response.json({ ok: false })).api, "r", "hi");
    expect(notLive).toMatchObject({ status: "closed", message: expect.stringMatching(/isn't live/) });
    const limited = await sendChat(mockApi(() => Response.json({ detail: "slow down" }, { status: 429 })).api, "r", "hi");
    expect(limited).toMatchObject({ status: "error", message: expect.stringMatching(/Too many/) });
    const bad = await sendChat(mockApi(() => Response.json({ detail: "x" }, { status: 400 })).api, "r", "hi");
    expect(bad).toMatchObject({ status: "error", message: "The server didn't accept this message." });
  });
});
