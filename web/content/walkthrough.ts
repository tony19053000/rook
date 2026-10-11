// Sample data for the home walkthrough (06 §6): one frame per step of `flowSteps`, drawn with the app's real
// run components. It is an illustration modelled on the recorded minishop run (lib/fixtures/minishop-run.json)
// and the shop-app demo bug (buy 100, refund 60, refund 50: paid 100, refunded 110). Not a live run, and it
// never touches the API.

import type { AgentItem, CounterexampleItem, EngineItem, FixItem, RulesItem, SearchItem, VerifyItem } from "@/lib/runStore";

export const WALKTHROUGH_LABEL = "Product illustration — not a live run";

export const walkthroughCopy = {
  id: "walkthrough",
  eyebrow: "How it works",
  title: "From your repo to a verified fix, in six steps",
  intro: "Bob agents do the reading, proposing and writing. The deterministic engine does the searching, replaying and verifying.",
  tablistLabel: "Steps of a Rook run",
  pause: "Pause",
  play: "Play",
  /** Appended to the control's visible text in its accessible name. */
  controlSuffix: " the walkthrough",
  repo: "shop-app",
} as const;

export type WalkthroughItem = AgentItem | EngineItem | RulesItem | SearchItem | CounterexampleItem | FixItem | VerifyItem;

export interface WalkthroughFrame {
  /** The `flowSteps` id this frame illustrates. */
  stepId: string;
  /** The run phase shown in the frame's title bar. */
  phase: string;
  items: WalkthroughItem[];
}

const T0 = "2026-09-26T13:43:27.000Z";

function agent(key: string, id: string, summary: string | null, detail = ""): AgentItem {
  return {
    kind: "agent",
    key,
    agent: id,
    callId: `c_${key}`,
    status: summary === null ? "working" : "done",
    detail,
    summary,
    cost: null,
    recorded: false,
    startedAt: T0,
    finishedAt: summary === null ? null : T0,
  };
}

function engine(key: string, worker: EngineItem["worker"], ok: boolean, summary: string): EngineItem {
  return { kind: "engine", key, worker, status: ok ? "done" : "failed", label: "", pct: 100, count: null, summary };
}

const RULE_ID = "refunded_total_le_paid";
const RULE_TEXT = "Total refunds on an order never exceed the amount paid";
const CHECK = "order.refunded_total <= order.paid";
const CX_ID = "cx_001";
const TEST_PATH = "test/rook_cx_001.test.js";
const OBSERVED = { paid: 100, refunded_total: 110, status: "paid" };

const STEPS = [
  { actor: "shopper", action: "buy", params: { price: 100, quantity: 1 } },
  { actor: "admin", action: "refund", params: { amount: 60 } },
  { actor: "admin", action: "refund", params: { amount: 50 } },
];

const DIFF = [
  "--- a/src/services/refunds.js",
  "+++ b/src/services/refunds.js",
  "-  if (amount > order.total) {",
  "+  if (amount > order.total - order.refundedTotal) {",
  '     throw badRequest("refund exceeds amount paid");',
  "   }",
].join("\n");

const rules: RulesItem = {
  kind: "rules",
  key: "rules",
  rules: [
    { id: RULE_ID, text: RULE_TEXT, evidence: ["src/services/refunds.js: refund checks amount against order.total"] },
    { id: "stock_non_negative", text: "Product stock never goes below zero", evidence: ["src/services/orders.js: stock is decremented on buy"] },
    { id: "shipped_not_cancelled", text: "A shipped order is never cancelled", evidence: ["src/routes/orders.js: cancel allows unshipped orders only"] },
    { id: "buy_status_ok", text: "Every buy answers with status paid", evidence: [] },
  ],
  verdicts: {
    buy_status_ok: [{ rule_id: "buy_status_ok", verdict: "reject", reason: "about one response, not the app's state", by: "critic" }],
  },
  approvedIds: [RULE_ID, "stock_non_negative", "shipped_not_cancelled"],
};

const search: SearchItem = {
  kind: "search",
  key: "search",
  sequences: 1240,
  perSec: 62,
  rules: { [RULE_ID]: "broken", stock_non_negative: "holding", shipped_not_cancelled: "holding" },
};

const counterexample: CounterexampleItem = {
  kind: "counterexample",
  key: "cx",
  violationId: "v_001",
  ruleId: RULE_ID,
  stepCounts: [7, 5, 3],
  observed: OBSERVED,
  saved: {
    cx_id: CX_ID,
    rule_id: RULE_ID,
    rule_text: RULE_TEXT,
    steps: STEPS,
    observed: OBSERVED,
    expected: CHECK,
    reproduced: "10/10",
    flaky: false,
    test_path: TEST_PATH,
  },
};

const fix: FixItem = {
  kind: "fix",
  key: "fix",
  cxId: CX_ID,
  diagnosis: {
    cx_id: CX_ID,
    file: "src/services/refunds.js",
    line: 23,
    explanation: "Each refund is compared with the order total on its own, ignoring the refunds already made, so two partial refunds can add up to more than was paid.",
    reviewed: true,
  },
  fix: { cx_id: CX_ID, files: ["src/services/refunds.js"], diff: DIFF, reviewed: true },
};

const verify: VerifyItem = {
  kind: "verify",
  key: "verify",
  cxId: CX_ID,
  checks: {
    replay: { status: "passed", detail: "rule held in 10/10 replays" },
    project_tests: { status: "passed", detail: "exit 0: all tests passed" },
    regression_test: { status: "passed", detail: `${TEST_PATH}: exit 0` },
    fresh_search: { status: "passed", detail: "no violation in 20,000 sequences (new seed)" },
  },
  freshSearch: null,
  done: { verified: true, summary: "4/4 checks passed" },
  committed: null,
  pr: { url: "github.com/you/shop-app/pull/1", number: 1, branch: "rook/fix-cx-001" },
};

export const walkthroughFrames: WalkthroughFrame[] = [
  {
    stepId: "understand",
    phase: "MAP",
    items: [
      agent("scout", "scout", "Node.js + Express shop: products, orders and refunds"),
      agent("mechanic", "mechanic", "App running in a Docker sandbox"),
      agent("mapper", "mapper", null, "reading src/routes/orders.js"),
      engine("dry", "runner", true, "6/6 actions dry-ran OK, 2/2 state readers OK"),
    ],
  },
  {
    stepId: "rules",
    phase: "APPROVE",
    items: [
      agent("lawmaker", "lawmaker", "Proposed 4 rules with evidence from the code"),
      agent("critic", "rule_critic", "Checked 4 rules and rejected 1 as weak"),
      rules,
    ],
  },
  {
    stepId: "search",
    phase: "SEARCH",
    items: [
      engine("runner", "runner", true, "1,240 sequences (seed 1)"),
      engine("judge", "judge", false, `rule ${RULE_ID} broken at step 7`),
      search,
    ],
  },
  {
    stepId: "shrink",
    phase: "SAVE",
    items: [engine("shrinker", "shrinker", true, "7 -> 3 steps"), engine("replayer", "replayer", true, "reproduced 10/10"), counterexample],
  },
  {
    stepId: "fix",
    phase: "FIX",
    items: [agent("detective", "detective", `Root cause in src/services/refunds.js : 23`), agent("surgeon", "surgeon", "Wrote the fix in the workspace copy"), fix],
  },
  {
    stepId: "verify",
    phase: "VERIFY",
    items: [verify],
  },
];

/** The "Before" box of the verify frame: the counterexample's observed values. */
export const verifyBefore = OBSERVED;
