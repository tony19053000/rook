// The refund bug, end to end (ROOK-054): one real case, the home page's central story. Every value below is
// copied from the recorded minishop run in lib/fixtures/minishop-run.json (the ROOK-023 run on
// tests/fixtures/minishop, Rook's own small test shop, with recorded Bob answers and the engine running live),
// and components/site/home/story.test.tsx fails if any of them drifts from that file. A guest "Try Rook" run of
// minishop on the hosted site finds the same counterexample (the screenshot on the home page is one).
// The walkthrough's sample data (./walkthrough.ts) reuses these values.

export interface StoryStep {
  actor: string;
  action: string;
  params: Record<string, number>;
}

/** The rule, as approved in the run (rules.approved / counterexample.saved). */
export const refundRule = {
  id: "refunded_total_le_paid",
  text: "Total refunds on an order never exceed the amount paid",
  check: "order.refunded_total <= order.paid",
} as const;

/** The first failing sequence the search found (violation.found), before the shrinker. */
export const refundFound = { steps: 4, paid: 50, refundedTotal: 60 } as const;

const STEPS: StoryStep[] = [
  { actor: "admin", action: "create_product", params: { price: 1, stock: 1 } },
  { actor: "customer", action: "buy", params: { quantity: 1 } },
  { actor: "customer", action: "refund", params: { amount: 1 } },
  { actor: "customer", action: "refund", params: { amount: 1 } },
];

/** The minimal counterexample (counterexample.saved). */
export const refundCounterexample = {
  id: "cx_001",
  steps: STEPS,
  observed: { paid: 1, refunded_total: 2, status: "paid", shipped: false },
  reproduced: "10/10",
  testPath: "test_rook_cx_001.py",
  /** The engine's shrinker summary (engine.finished, worker shrinker). */
  shrinkSummary: "4 -> 4 steps in 38 runs",
  /** The generated regression test on the unfixed code (engine.finished, worker testrunner). */
  testBeforeFix: "exit 1: 1 failed, 13 passed in 0.44s",
} as const;

/** The Detective's diagnosis, reviewed by the Diagnosis Reviewer (diagnosis.ready). */
export const refundDiagnosis = {
  file: "app.py",
  line: 214,
  /** The diagnosis's first sentence, verbatim. */
  sentence: "On line 214, in buggy mode (is_fixed=False), `already` is set to 0 instead of `order.refunded_total`.",
  explanation:
    "On line 214, in buggy mode (is_fixed=False), `already` is set to 0 instead of `order.refunded_total`. Each refund is therefore checked only against `body.amount > order.paid` in isolation, ignoring previously recorded refunds. This allows the cumulative refunded_total to exceed the amount paid.",
} as const;

/** The Surgeon's fix, reviewed by the Fix Reviewer (fix.ready): verbatim, without the `@@` hunk header line. */
export const refundFix = {
  files: ["app.py"],
  diff: [
    "--- a/app.py",
    "+++ b/app.py",
    '     @app.post("/orders/{order_id}/refunds")',
    "     async def refund(order_id: int, body: NewRefund, user: CurrentUser) -> dict[str, int]:",
    "         order = get_order(order_id, user)",
    "-        # BUG 1 (buggy mode): each refund is compared with the amount paid on its own.",
    "-        already = order.refunded_total if is_fixed else 0",
    "+        already = order.refunded_total",
    "         if already + body.amount > order.paid:",
    '             raise HTTPException(400, "refund exceeds amount paid")',
    "         order.refunds.append(body.amount)",
    "",
  ].join("\n"),
} as const;

export type CheckId = "replay" | "project_tests" | "regression_test" | "fresh_search";

/** The four engine checks of VERIFY (verify.step, status passed), with the engine's own detail lines. */
export const refundChecks: { id: CheckId; label: string; meaning: string; detail: string }[] = [
  {
    id: "replay",
    label: "Exact replay",
    meaning: "The same 4 steps, replayed on the fixed app.",
    detail: "rule refunded_total_le_paid held in 10/10 replays",
  },
  { id: "project_tests", label: "Your project's tests", meaning: "The app's own test suite.", detail: "exit 0: 13 passed in 0.37s" },
  {
    id: "regression_test",
    label: "The generated regression test",
    meaning: "The new test, with the project's tests. It failed before the fix.",
    detail: "exit 0: 14 passed in 0.44s",
  },
  {
    id: "fresh_search",
    label: "A fresh search, new seed",
    meaning: "New random sequences against the fixed app. This run's budget was 1,500; the CLI default is 20,000.",
    detail: "no violation of 1 rules in 1500 sequences (seed 1:verify:1)",
  },
];

/** verify.done and fix.committed. */
export const refundOutcome = { summary: "4/4 checks passed", branch: "rook/fix-cx-001" } as const;

export const storyCopy = {
  id: "refund-bug",
  eyebrow: "One real case",
  title: "The refund bug, end to end",
  intro:
    "Every value here comes from a recorded Rook run on minishop, Rook's own small test shop: one of the two example repos you can run with Try Rook.",
  /** Shown after the "Recorded example run" label (06 §4). */
  source: "Bob's answers were replayed from a saved real run; the engine ran live against the real app.",
  stages: {
    rule: {
      label: "1 · The rule",
      title: "A rule you approved",
      body: "Bob proposed it with evidence from the code. Each refund on its own looks valid, so no single request breaks it.",
    },
    sequence: {
      label: "2 · The smallest sequence",
      title: "Four normal calls break it",
      body: `The search broke the rule with paid ${refundFound.paid} and refunded ${refundFound.refundedTotal}. The shrinker kept the ${refundFound.steps} steps and cut the values to the smallest that still fail.`,
    },
    replay: {
      label: "3 · Replayed",
      title: "Proved on the real app",
      body: "The engine replayed the sequence on the running app and saved it as a counterexample plus a regression test.",
    },
    diagnosis: {
      label: "4 · Diagnosis",
      title: "One line is the cause",
      body: "The Detective's diagnosis, checked by the Diagnosis Reviewer against the evidence:",
    },
    fix: {
      label: "5 · The fix",
      title: "A one-line fix, reviewed",
      body: "Written by the Surgeon in a workspace copy after approval, checked by the Fix Reviewer.",
    },
    verify: {
      label: "6 · Verified",
      title: "Four engine checks, all passed",
      body: "Only the engine decides. The fix then landed on its own branch.",
    },
  },
  observedLabel: `Observed after step ${refundCounterexample.steps.length}`,
  mustHold: "Must hold",
  broken: "Rule broken",
  replayedLabel: "Reproduced",
  regressionLabel: "Regression test",
  testBeforeFixLabel: "On the unfixed code",
  diffLabel: "Fix · app.py",
  branchLabel: "Committed to branch",
} as const;
