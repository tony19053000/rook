"use client";

// The recorded run through the real SSE client, runStore and RunView (every card, answers and chat). The
// fake API accepts every answer and chat message; the recording answers its own questions.

import { useMemo } from "react";
import { RunView } from "@/components/RunView";
import type { ApiClient } from "@/lib/api";
import { createFakeEventServer } from "@/lib/fakeServer";
import { minishopRun } from "@/lib/fixtures/minishop";
import { useRunStream } from "@/lib/useRunStream";

const RUN_ID = minishopRun[0]!.run_id;

const fakeApi: Pick<ApiClient, "answer" | "chat"> = {
  answer: async () => ({ ok: true }),
  chat: async () => ({ ok: true }),
};

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
    <RunView
      state={state}
      runId={RUN_ID}
      api={fakeApi}
      banner={banner}
      header={
        <p className="num text-[13px] text-muted">
          dev · stream {status} · phase {state.phase ?? "-"} · run {state.status} · seq {state.lastSeq}
        </p>
      }
    />
  );
}
