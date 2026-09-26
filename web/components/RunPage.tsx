"use client";

// `/runs/[id]` (04 §3.2): the live run. It opens GET /runs/{id}/events through useRunStream (resuming with
// `after` on every reconnect) and renders RunView; a guest gets the auto-answer countdown.

import { AppShell } from "./AppShell";
import { ErrorCard } from "./ErrorCard";
import { RunView } from "./RunView";
import type { ApiClient, RunSummary } from "@/lib/api";
import { apiBase } from "@/lib/config";
import { shellProps, streamNotice } from "@/lib/pages";
import type { RunState } from "@/lib/runStore";
import { getToken, type Session } from "@/lib/session";
import type { StreamStatus, StreamStatusInfo } from "@/lib/sse";
import { useRunStream } from "@/lib/useRunStream";

export interface RunPageProps {
  runId: string;
  api: Pick<ApiClient, "answer" | "chat">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
}

export function RunPage(props: RunPageProps) {
  const { state, status, info, retry } = useRunStream({ baseUrl: apiBase(), runId: props.runId, getToken });
  return <RunPageView {...props} state={state} status={status} info={info} retry={retry} />;
}

export interface RunPageViewProps extends RunPageProps {
  state: RunState;
  status: StreamStatus;
  info: StreamStatusInfo;
  retry: () => void;
}

/** The page without the stream hook, so it renders in tests from a folded RunState. */
export function RunPageView({ runId, api, session, runs, state, status, info, retry }: RunPageViewProps) {
  const notice = streamNotice(status, info, state.lastSeq);
  const shell = { ...shellProps(session, runs), active: "run" as const, currentRunId: runId };

  if (notice.kind === "refused") {
    return (
      <AppShell {...shell}>
        <ErrorCard view={notice.error} />
      </AppShell>
    );
  }

  const banner =
    notice.kind === "reconnecting" ? (
      <div role="status" className="flex items-center justify-center gap-3 bg-warn-soft px-3 py-1 text-[13px] text-warn">
        Reconnecting… (attempt {notice.attempt})
        <button type="button" className="underline" onClick={retry}>
          Retry now
        </button>
      </div>
    ) : null;

  const header =
    state.lastSeq === 0 ? (
      <div className="flex flex-col gap-2.5" aria-busy="true" data-skeleton="run">
        <p className="text-[13px] text-muted">Waiting for the run to start…</p>
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded-xl bg-surface" />
        ))}
      </div>
    ) : null;

  return (
    <RunView state={state} runId={runId} api={api} guest={session.kind === "guest"} banner={banner} header={header} shell={shell} />
  );
}
