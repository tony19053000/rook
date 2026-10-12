"use client";

// `/runs/[id]` (04 §3.2): the live run. It opens GET /runs/{id}/events through useRunStream (resuming with
// `after` on every reconnect) and renders RunView; a guest gets the auto-answer countdown. Above the transcript:
// how the run gets Bob's answers ("Recorded example run" / "Live run", 06 §4) and "Delete run" (ROOK-051).

import { AppShell } from "./AppShell";
import { DeleteConfirm } from "./DeleteConfirm";
import { ErrorCard } from "./ErrorCard";
import { RunView } from "./RunView";
import type { ApiClient, RunSummary } from "@/lib/api";
import { apiBase } from "@/lib/config";
import { RUN_MODE_TEXT, runDelete, runMode, shellProps, streamNotice, type RunMode } from "@/lib/pages";
import type { RunState } from "@/lib/runStore";
import { getToken, type Session } from "@/lib/session";
import type { StreamStatus, StreamStatusInfo } from "@/lib/sse";
import { useRunStream } from "@/lib/useRunStream";

export interface RunPageProps {
  runId: string;
  api: Pick<ApiClient, "answer" | "chat" | "deleteRun">;
  session: Session;
  runs: { runs: RunSummary[]; loading: boolean };
  /** Where the page goes after the run is deleted (the router; a full page load by default). */
  navigate?: (href: string) => void;
}

/** "Recorded example run" / "Live run" with its one-line explanation; nothing until the run has said which. */
export function RunModeLabel({ mode }: { mode: RunMode | null }) {
  if (mode === null) return null;
  const text = RUN_MODE_TEXT[mode];
  return (
    <p data-run-mode={mode} className="min-w-0 flex-1 basis-[220px] text-[12.5px] text-muted">
      <span className="mr-1.5 inline-block rounded-full bg-sunk px-2.5 py-0.5 text-[11.5px] font-semibold text-ink">{text.label}</span>
      {text.explain}
    </p>
  );
}

/** Where a deleted run's page goes: the runs list, or the home for a guest (no list to return to). */
export function afterDeleteHref(session: Session): string {
  return session.kind === "guest" ? "/app" : "/runs";
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
export function RunPageView({ runId, api, session, runs, navigate, state, status, info, retry }: RunPageViewProps) {
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

  const go = navigate ?? ((href: string) => window.location.assign(href));
  const header = (
    <>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-x-4 gap-y-2" data-run-bar>
        <RunModeLabel mode={runMode(state)} />
        <DeleteConfirm
          name="run"
          label="Delete run"
          confirmLabel="Yes, delete this run"
          explain="This removes the run, its events, its counterexamples and its workspace files from Roook's server. A run that is still going is stopped first. It can't be undone."
          run={() => runDelete(() => api.deleteRun(runId), "run")}
          onDeleted={() => go(afterDeleteHref(session))}
          onRefresh={() => window.location.reload()}
        />
      </div>
      {state.lastSeq === 0 && (
        <div className="flex flex-col gap-2.5" aria-busy="true" data-skeleton="run">
          <p className="text-[13px] text-muted">Waiting for the run to start. A queued run starts when an earlier one finishes.</p>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded-xl bg-surface" />
          ))}
        </div>
      )}
    </>
  );

  return (
    <RunView state={state} runId={runId} api={api} guest={session.kind === "guest"} banner={banner} header={header} shell={shell} />
  );
}
