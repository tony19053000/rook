import { describe, expect, it } from "vitest";
import type { EventDataMap, EventType, RookEvent } from "./events";
import { minishopRun } from "./fixtures/minishop";
import { runOutcome } from "./outcome";
import { initialRunState, reduceEvents } from "./runStore";

const RUN_ID = minishopRun[0]!.run_id;
function ev<T extends EventType>(seq: number, type: T, data: EventDataMap[T]): RookEvent {
  return { v: 1, seq, ts: "2026-09-26T09:00:00.000Z", run_id: RUN_ID, type, data } as RookEvent;
}

/** The recorded run up to (not including) the first event of `type`, then `extra`, with fresh seqs. */
function until(type: EventType, extra: [EventType, unknown][]): RookEvent[] {
  const cut = minishopRun.findIndex((e) => e.type === type);
  const body = minishopRun.slice(0, cut);
  const last = body[body.length - 1]!.seq;
  return [...body, ...extra.map(([t, d], i) => ev(last + 1 + i, t, d as never))];
}

const UNVERIFIED =
  "Found and saved cx_001; the fix for rule admin_export_forbidden_for_customer was written and the exact replay now passes, " +
  "but the fresh search found another approved rule still broken: refund_le_paid. NOT verified: the patch was reverted and not shipped.";

describe("run outcome (the final card, 04 §3.6)", () => {
  it("is null while the run is live", () => {
    expect(runOutcome(initialRunState)).toBeNull();
    expect(runOutcome(reduceEvents(minishopRun.slice(0, -1)))).toBeNull();
  });

  it("is 'Fixed and verified' when the engine verified the fix (the recorded run)", () => {
    const o = runOutcome(reduceEvents(minishopRun));
    expect(o).toMatchObject({ kind: "verified", tone: "good", mark: "✓", title: "Fixed and verified" });
  });

  it("is a calm 'not verified' (warn, not bad) when verify.done says verified=false", () => {
    const state = reduceEvents(
      until("verify.done", [
        ["verify.done", { cx_id: "cx_001", verified: false, summary: "3/4 checks passed; failed: fresh_search" }],
        ["run.finished", { status: "done", summary: UNVERIFIED }],
      ]),
    );
    const o = runOutcome(state);
    expect(o).toMatchObject({ kind: "unverified", tone: "warn", mark: "!" });
    expect(o!.title).toMatch(/not verified/i);
    expect(o!.lead).toMatch(/nothing was shipped/);
  });

  it("is 'not verified' when a fix was written but never verified", () => {
    const state = reduceEvents(until("verify.step", [["run.finished", { status: "done", summary: "a fix was written but NOT verified" }]]));
    expect(runOutcome(state)?.kind).toBe("unverified");
  });

  it("is 'rule broken' when a counterexample was saved but no fix was made", () => {
    const state = reduceEvents(until("fix.ready", [["run.finished", { status: "done", summary: "Found and saved cx_001; no fix." }]]));
    expect(runOutcome(state)).toMatchObject({ kind: "found", tone: "warn" });
  });

  it("is 'every rule held' when the search ran and found nothing", () => {
    const state = reduceEvents(until("counterexample.saved", [["run.finished", { status: "done", summary: "No counterexample" }]]));
    // The recorded run's first saved counterexample comes after its violation; drop those items to model a clean search.
    const clean = { ...state, items: state.items.filter((i) => i.kind !== "counterexample") };
    expect(runOutcome(clean)).toMatchObject({ kind: "held", tone: "good" });
  });

  it("is plain 'Run finished' when nothing was searched, and says failed/cancelled for those statuses", () => {
    expect(runOutcome({ status: "done", items: [] })?.kind).toBe("nothing");
    expect(runOutcome({ status: "failed", items: [] })).toMatchObject({ kind: "failed", tone: "bad", title: "Run failed" });
    expect(runOutcome({ status: "cancelled", items: [] })).toMatchObject({ kind: "cancelled", tone: "idle" });
  });
});
