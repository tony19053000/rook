"use client";

// Agent and engine rows (ROOK-034) plus plain text for the other items; the cards come with ROOK-035.

import { useMemo } from "react";
import { AppShell } from "@/components/AppShell";
import { Composer } from "@/components/Composer";
import { AgentRow } from "@/components/AgentRow";
import { EngineRow } from "@/components/EngineRow";
import { createFakeEventServer } from "@/lib/fakeServer";
import { minishopRun } from "@/lib/fixtures/minishop";
import type { TranscriptItem } from "@/lib/runStore";
import { useRunStream } from "@/lib/useRunStream";

const RUN_ID = minishopRun[0]!.run_id;

function Row({ item }: { item: TranscriptItem }) {
  switch (item.kind) {
    case "agent":
      return <AgentRow item={item} />;
    case "engine":
      return <EngineRow item={item} />;
    case "question":
      return (
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          <span className="text-warn">?</span> {item.text}{" "}
          {item.answered && <span className="text-good">✓ {JSON.stringify(item.answer)} ({item.answeredBy})</span>}
        </div>
      );
    case "chat":
      return <div className={item.role === "user" ? "self-end rounded-xl border border-line bg-surface px-3.5 py-2" : ""}>{item.text}</div>;
    case "log":
      return <div className={`text-[13px] ${item.level === "info" ? "text-muted" : item.level === "warn" ? "text-warn" : "text-bad"}`}>{item.text}</div>;
    case "rules":
      return (
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          Rules: {item.rules.length} proposed · {item.approvedIds === null ? "needs your OK" : `${item.approvedIds.length} approved`}
        </div>
      );
    case "search":
      return (
        <div className="num rounded-lg border border-line bg-surface px-3 py-2">
          Search: {item.sequences.toLocaleString()} sequences · {Math.round(item.perSec)}/s ·{" "}
          {Object.entries(item.rules).map(([id, s]) => `${id}: ${s}`).join(", ")}
        </div>
      );
    case "counterexample":
      return (
        <div className="rounded-lg border border-bad bg-surface px-3 py-2">
          Counterexample {item.saved?.cx_id ?? "(shrinking)"} · rule {item.ruleId} · steps{" "}
          <span className="num">{item.stepCounts.join(" → ")}</span>
          {item.saved && ` · reproduced ${item.saved.reproduced}`}
        </div>
      );
    case "fix":
      return (
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          Fix {item.cxId}: {item.diagnosis ? `${item.diagnosis.file}:${item.diagnosis.line ?? "?"}` : "diagnosing"}
          {item.fix && ` · ${item.fix.files.join(", ")}`}
        </div>
      );
    case "verify":
      return (
        <div className="rounded-lg border border-line bg-surface px-3 py-2">
          Verify {item.cxId}:{" "}
          {Object.entries(item.checks).map(([check, c]) => `${check} ${c.status}`).join(" · ")}
          {item.done && <b className={item.done.verified ? "text-good" : "text-bad"}> {item.done.verified ? "✓ FIX VERIFIED" : "✗ not verified"}</b>}
          {item.committed && ` · branch ${item.committed.branch}`}
        </div>
      );
  }
}

export function DevStream() {
  // One fake server per mount; it drops connection 1 after 60 events and connection 2 after 90 more, and
  // replays 5 old events on each reconnect.
  const server = useMemo(() => createFakeEventServer(minishopRun, { intervalMs: 40, dropAfter: [60, 95], overlap: 5 }), []);
  const { state, status, info, retry } = useRunStream({ baseUrl: "http://fake.local", runId: RUN_ID, fetch: server.fetch });

  const banner =
    status === "reconnecting" ? (
      <div role="status" className="flex items-center justify-center gap-3 bg-warn-soft px-3 py-1 text-[13px] text-warn">
        Reconnecting… (attempt {info.attempt})
        <button type="button" className="underline" onClick={retry}>
          Retry now
        </button>
      </div>
    ) : null;

  return (
    <AppShell banner={banner} coins={state.coins} composer={<Composer disabled placeholder="Chat arrives with ROOK-035" />}>
      <p className="num text-[13px] text-muted">
        dev · stream {status} · phase {state.phase ?? "-"} · run {state.status} · seq {state.lastSeq}
      </p>
      {state.items.map((item) => (
        <Row key={item.key} item={item} />
      ))}
      {state.summary && <p className="font-semibold">{state.summary}</p>}
    </AppShell>
  );
}
