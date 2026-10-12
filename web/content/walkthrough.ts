// Sample data for the home walkthrough (06 §6): one frame per step of `flowSteps`, drawn with the app's real
// run components. The case (rule, steps, values, diagnosis, fix and the verify checks) is the recorded minishop
// run of ./story.ts (lib/fixtures/minishop-run.json); the agents' one-line summaries are short illustrations of
// what each agent did. Not a live run, and it never touches the API.

import type { AgentItem, CounterexampleItem, EngineItem, FixItem, RulesItem, SearchItem, VerifyItem } from "@/lib/runStore";
import { refundChecks, refundCounterexample, refundDiagnosis, refundFix, refundFound, refundOutcome, refundRule } from "./story";

export const WALKTHROUGH_LABEL = "Product illustration — not a live run";

export const walkthroughCopy = {
  id: "walkthrough",
  eyebrow: "Inside a run",
  title: "Watch the six steps in the product",
  intro: "The refund case again, drawn with the web app's own components: Bob agents read, propose and write; the engine searches, replays and verifies.",
  tablistLabel: "Steps of a Roook run",
  pause: "Pause",
  play: "Play",
  /** Appended to the control's visible text in its accessible name. */
  controlSuffix: " the walkthrough",
  repo: "minishop",
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

const RULE_ID = refundRule.id;
const CX_ID = refundCounterexample.id;
const TEST_PATH = refundCounterexample.testPath;
const OBSERVED = refundCounterexample.observed;
// counterexample.saved carries each step's refs too: the product and order it acts on (index 0, the first one).
const REFS = [{}, { product_id: 0 }, { order_id: 0 }, { order_id: 0 }];
const STEPS = refundCounterexample.steps.map((step, i) => ({ ...step, refs: REFS[i] ?? {} }));

const rules: RulesItem = {
  kind: "rules",
  key: "rules",
  rules: [
    { id: RULE_ID, text: refundRule.text, evidence: ["app.py:214-216: refund guard checks already + body.amount > order.paid", "app.py:54-55: refunded_total is sum(refunds)"] },
    { id: "order_paid_non_negative", text: "The amount paid for an order is never negative", evidence: ["app.py:196-202: paid = product.price * quantity"] },
    { id: "shipped_order_not_cancelled", text: "A shipped order is never in cancelled status", evidence: ["app.py:222-224: cancel raises 409 if order.shipped is True"] },
    { id: "buy_response_status_paid", text: "Every buy answers with status paid", evidence: [] },
  ],
  verdicts: {
    buy_response_status_paid: [
      {
        rule_id: "buy_response_status_paid",
        verdict: "reject",
        reason: "its check does not parse with the safe evaluator: only direct calls to allowed functions are permitted (no method calls)",
        by: "engine",
      },
    ],
  },
  approvedIds: [RULE_ID],
};

const search: SearchItem = { kind: "search", key: "search", sequences: 1, perSec: 69.4, rules: { [RULE_ID]: "broken" } };

const counterexample: CounterexampleItem = {
  kind: "counterexample",
  key: "cx",
  violationId: "v_79d91d72",
  ruleId: RULE_ID,
  stepCounts: [refundFound.steps],
  observed: OBSERVED,
  saved: {
    cx_id: CX_ID,
    rule_id: RULE_ID,
    rule_text: refundRule.text,
    steps: STEPS,
    observed: OBSERVED,
    expected: refundRule.check,
    reproduced: refundCounterexample.reproduced,
    flaky: false,
    test_path: TEST_PATH,
  },
};

const fix: FixItem = {
  kind: "fix",
  key: "fix",
  cxId: CX_ID,
  diagnosis: { cx_id: CX_ID, file: refundDiagnosis.file, line: refundDiagnosis.line, explanation: refundDiagnosis.explanation, reviewed: true },
  fix: { cx_id: CX_ID, files: [...refundFix.files], diff: refundFix.diff, reviewed: true },
};

const verify: VerifyItem = {
  kind: "verify",
  key: "verify",
  cxId: CX_ID,
  checks: Object.fromEntries(refundChecks.map((check) => [check.id, { status: "passed", detail: check.detail }])),
  freshSearch: null,
  done: { verified: true, summary: refundOutcome.summary },
  committed: { cx_id: CX_ID, branch: refundOutcome.branch, commit: "5bf3ec34f90a36409e4bc847691ef6d610746507", files: ["app.py", "rook/counterexamples/cx_001.json", "rook/rook.yaml", TEST_PATH] },
  pr: null,
};

export const walkthroughFrames: WalkthroughFrame[] = [
  {
    stepId: "understand",
    phase: "MAP",
    items: [
      agent("scout", "scout", "Python + FastAPI shop in app.py: products, orders and refunds"),
      agent("mechanic", "mechanic", "App running in a sandbox, no secrets needed"),
      agent("mapper", "mapper", null, "reading app.py"),
      engine("dry", "runner", true, "6/6 actions dry-ran OK, 2/2 state readers OK"),
    ],
  },
  {
    stepId: "rules",
    phase: "APPROVE",
    items: [agent("lawmaker", "lawmaker", "Proposed rules with evidence from the code"), agent("critic", "rule_critic", "Checked the rules against the code"), rules],
  },
  {
    stepId: "search",
    phase: "SEARCH",
    items: [engine("runner", "runner", true, "1 sequences in 0.0s (69/s)"), engine("judge", "judge", false, `rule ${RULE_ID} broken at step 4`), search],
  },
  {
    stepId: "shrink",
    phase: "SAVE",
    items: [
      engine("shrinker", "shrinker", true, refundCounterexample.shrinkSummary),
      engine("replayer", "replayer", true, `reproduced ${refundCounterexample.reproduced}`),
      counterexample,
    ],
  },
  {
    stepId: "fix",
    phase: "FIX",
    items: [
      agent("detective", "detective", `Root cause in ${refundDiagnosis.file} : ${refundDiagnosis.line}`),
      agent("surgeon", "surgeon", "Wrote the fix in the workspace copy"),
      fix,
    ],
  },
  { stepId: "verify", phase: "VERIFY", items: [verify] },
];

/** The "Before" box of the verify frame: the counterexample's observed values. */
export const verifyBefore = OBSERVED;
