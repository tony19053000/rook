// The run's final card (04 §3.6): a headline and a tone picked from the engine's own events (verify.done,
// counterexample.saved, fix.ready, search) once run.finished arrived. The server's summary line is shown
// under it as-is; this only decides how to frame it, never whether a rule broke or a fix passed.

import type { RunState } from "./runStore";

export type OutcomeKind = "verified" | "unverified" | "found" | "held" | "nothing" | "failed" | "cancelled";

export interface Outcome {
  kind: OutcomeKind;
  tone: "good" | "warn" | "bad" | "idle";
  /** ✓ / ! / ✗ / · so colour is never the only signal (04 §3.7). */
  mark: string;
  title: string;
  /** One plain sentence under the title, before the server's summary. */
  lead: string;
}

const OUTCOMES: Record<OutcomeKind, Omit<Outcome, "kind">> = {
  verified: {
    tone: "good",
    mark: "✓",
    title: "Fixed and verified",
    lead: "Rook found the bug, proved it on the real app, and the engine verified the fix.",
  },
  unverified: {
    tone: "warn",
    mark: "!",
    title: "Bug proven · fix not verified",
    lead: "The counterexample is real and saved. The fix did not pass every engine check, so nothing was shipped.",
  },
  found: {
    tone: "warn",
    mark: "!",
    title: "Rule broken · counterexample saved",
    lead: "Rook found and replayed the smallest sequence of actions that breaks the rule.",
  },
  held: {
    tone: "good",
    mark: "✓",
    title: "Every approved rule held",
    lead: "The search found no sequence of actions that breaks an approved rule.",
  },
  nothing: { tone: "idle", mark: "·", title: "Run finished", lead: "" },
  failed: { tone: "bad", mark: "✗", title: "Run failed", lead: "" },
  cancelled: { tone: "idle", mark: "·", title: "Run cancelled", lead: "" },
};

/** The final framing of a finished run, or null while it is still running. */
export function runOutcome(state: Pick<RunState, "status" | "items">): Outcome | null {
  const kind = outcomeKind(state);
  return kind === null ? null : { kind, ...OUTCOMES[kind] };
}

function outcomeKind({ status, items }: Pick<RunState, "status" | "items">): OutcomeKind | null {
  if (status === "failed" || status === "cancelled") return status;
  if (status !== "done") return null;
  let verify: boolean | null = null;
  let saved = false;
  let fixed = false;
  let searched = false;
  for (const item of items) {
    if (item.kind === "verify" && item.done !== null) verify = item.done.verified;
    else if (item.kind === "counterexample" && item.saved !== null) saved = true;
    else if (item.kind === "fix" && item.fix !== null) fixed = true;
    else if (item.kind === "search") searched = true;
  }
  if (verify === true) return "verified";
  if (verify === false || fixed) return "unverified";
  if (saved) return "found";
  return searched ? "held" : "nothing";
}
