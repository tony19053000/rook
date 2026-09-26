"use client";

// A live run (04 §3.2 `/runs/[id]`): the transcript with its cards, answers through POST /runs/{id}/answers
// and the composer sending chat to POST /runs/{id}/chat (the Guide's reply, and the user's own line, come
// back as chat.message events). The page that opens the stream (ROOK-036) renders this.

import { useMemo, useState, type ReactNode } from "react";
import { AppShell } from "./AppShell";
import { Composer } from "./Composer";
import { Transcript } from "./Transcript";
import { Note, RunActionsContext, type RunActions } from "./cards/ui";
import type { ApiClient } from "@/lib/api";
import { GUEST_AUTO_SECONDS, sendAnswer, sendChat, type SendOutcome } from "@/lib/questions";
import type { RunState } from "@/lib/runStore";
import { clean } from "@/lib/safeText";

export interface RunViewProps {
  state: RunState;
  runId: string;
  api: Pick<ApiClient, "answer" | "chat">;
  /** Guest demo mode: questions auto-answer "yes" after a visible countdown. */
  guest?: boolean;
  autoSeconds?: number;
  banner?: ReactNode;
  header?: ReactNode;
}

export function isLive(state: Pick<RunState, "status">): boolean {
  return state.status === "running" || state.status === "idle";
}

export function RunView({ state, runId, api, guest = false, autoSeconds = GUEST_AUTO_SECONDS, banner, header }: RunViewProps) {
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
      <AppShell banner={banner} coins={state.coins} composer={composer}>
        {header}
        <Transcript state={state} />
        {state.summary !== null && (
          <p data-run-summary={state.status} className={`font-semibold ${state.status === "done" ? "" : "text-bad"}`}>
            {clean(state.summary)}
          </p>
        )}
      </AppShell>
    </RunActionsContext.Provider>
  );
}
