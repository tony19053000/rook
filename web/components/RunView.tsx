"use client";

// A live run (04 §3.2 `/runs/[id]`): the transcript with its cards, answers through POST /runs/{id}/answers
// and the composer sending chat to POST /runs/{id}/chat (the Guide's reply, and the user's own line, come
// back as chat.message events). RunPage (`/runs/[id]`) opens the stream and renders this.

import { useMemo, useState, type ReactNode } from "react";
import { AppShell, type AppShellProps } from "./AppShell";
import { Composer } from "./Composer";
import { Transcript } from "./Transcript";
import { Note, RunActionsContext, type RunActions } from "./cards/ui";
import type { ApiClient } from "@/lib/api";
import { GUEST_AUTO_SECONDS, sendAnswer, sendChat, type SendOutcome } from "@/lib/questions";
import type { RunState } from "@/lib/runStore";
import { runOutcome, type Outcome } from "@/lib/outcome";
import { clean } from "@/lib/safeText";

const OUTCOME_STYLE: Record<Outcome["tone"], { box: string; mark: string }> = {
  good: { box: "border-good bg-good-soft", mark: "bg-good text-app" },
  warn: { box: "border-warn bg-warn-soft", mark: "bg-warn text-app" },
  bad: { box: "border-bad bg-bad-soft", mark: "bg-bad text-app" },
  idle: { box: "border-line bg-surface", mark: "bg-sunk text-muted" },
};

/** The run's final card (04 §3.6): the outcome headline, then the server's summary line. */
function OutcomeCard({ state, summary }: { state: RunState; summary: string }) {
  const outcome = runOutcome(state);
  const style = OUTCOME_STYLE[outcome?.tone ?? "idle"];
  return (
    <div
      data-run-summary={state.status}
      data-outcome={outcome?.kind}
      role="status"
      className={`mt-2 flex min-w-0 gap-3 rounded-xl border px-4 py-3.5 ${style.box}`}
    >
      <span aria-hidden className={`grid size-7 flex-none place-items-center rounded-full text-[15px] font-bold ${style.mark}`}>
        {outcome?.mark ?? "·"}
      </span>
      <div className="flex min-w-0 flex-col gap-1">
        <p className="text-[15px] font-semibold">{outcome?.title ?? "Run finished"}</p>
        {outcome !== null && outcome.lead !== "" && <p className="text-[13.5px]">{outcome.lead}</p>}
        <p className="break-words text-[13px] text-muted">{clean(summary)}</p>
      </div>
    </div>
  );
}

export interface RunViewProps {
  state: RunState;
  runId: string;
  api: Pick<ApiClient, "answer" | "chat">;
  /** Guest demo mode: questions auto-answer "yes" after a visible countdown. */
  guest?: boolean;
  autoSeconds?: number;
  banner?: ReactNode;
  header?: ReactNode;
  /** Sidebar props from the page (recents, account, active entry). */
  shell?: Omit<Partial<AppShellProps>, "children" | "composer" | "banner" | "coins">;
}

export function isLive(state: Pick<RunState, "status">): boolean {
  return state.status === "running" || state.status === "idle";
}

export function RunView({ state, runId, api, guest = false, autoSeconds = GUEST_AUTO_SECONDS, banner, header, shell }: RunViewProps) {
  const [chatNote, setChatNote] = useState<SendOutcome | null>(null);
  const [sending, setSending] = useState(false);
  const actions = useMemo<RunActions>(
    () => ({ answer: (questionId, answer) => sendAnswer(api, runId, questionId, answer), guest, autoSeconds }),
    [api, runId, guest, autoSeconds],
  );
  const live = isLive(state);

  const onSend = async (text: string) => {
    setSending(true);
    setChatNote(null);
    const outcome = await sendChat(api, runId, text);
    setSending(false);
    setChatNote(outcome.status === "sent" ? null : outcome);
  };

  const composer = (
    <div className="flex flex-col gap-1.5">
      {chatNote !== null && chatNote.status !== "sent" && (
        <div className="mx-auto w-full max-w-[760px] px-1">
          <Note tone={chatNote.status === "error" ? "bad" : "warn"}>{chatNote.message}</Note>
        </div>
      )}
      <Composer
        onSend={(text) => void onSend(text)}
        disabled={!live || sending}
        placeholder={live ? "Ask the Guide about this run" : "This run has finished"}
        repoLabel={state.created ? clean(state.created.repo.name) : undefined}
      />
    </div>
  );

  return (
    <RunActionsContext.Provider value={actions}>
      <AppShell {...shell} banner={banner} coins={state.coins} composer={composer}>
        {header}
        <Transcript state={state} />
        {state.summary !== null && <OutcomeCard state={state} summary={state.summary} />}
      </AppShell>
    </RunActionsContext.Provider>
  );
}
