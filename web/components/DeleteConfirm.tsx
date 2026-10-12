"use client";

// A delete control with a confirm step (ROOK-052): the trigger, then what will be deleted with Delete / Cancel,
// then how it went. A failure keeps the explanation and offers Retry; a timeout reads as "still deleting".

import { useState, type ReactNode } from "react";
import type { DeleteOutcome } from "@/lib/pages";
import { clean } from "@/lib/safeText";

export interface DeleteConfirmProps {
  /** The trigger's label, e.g. "Delete run". */
  label: string;
  /** What is deleted, in plain words (shown before anything is sent). */
  explain: ReactNode;
  /** The confirm button's label, e.g. "Yes, delete this run". */
  confirmLabel: string;
  /** Sends the deletion; never throws (lib/pages.runDelete). */
  run: () => Promise<DeleteOutcome>;
  /** Called once the server confirmed the deletion. */
  onDeleted: () => void | Promise<void>;
  /** Reloads the page after a timeout ("refresh in a moment"). */
  onRefresh?: () => void;
  triggerClassName?: string;
  triggerRole?: "menuitem";
  icon?: ReactNode;
  /** Names the control in the markup (`data-delete`). */
  name: string;
}

type Step = { at: "idle" } | { at: "confirm" } | { at: "sending" } | { at: "done" } | { at: "result"; outcome: Exclude<DeleteOutcome, { kind: "deleted" }> };

const SMALL_BUTTON = "rounded-lg border px-3 py-1.5 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-50";
const DANGER = `${SMALL_BUTTON} border-bad bg-bad-soft text-bad hover:opacity-90`;
const PLAIN = `${SMALL_BUTTON} border-line bg-app text-ink hover:bg-hover`;

export function DeleteConfirm({ label, explain, confirmLabel, run, onDeleted, onRefresh, triggerClassName, triggerRole, icon, name }: DeleteConfirmProps) {
  const [step, setStep] = useState<Step>({ at: "idle" });

  const send = async () => {
    setStep({ at: "sending" });
    const outcome = await run();
    if (outcome.kind !== "deleted") {
      setStep({ at: "result", outcome });
      return;
    }
    setStep({ at: "done" });
    await onDeleted();
  };

  if (step.at === "idle") {
    return (
      <button type="button" role={triggerRole} data-delete={name} onClick={() => setStep({ at: "confirm" })} className={triggerClassName ?? PLAIN}>
        {icon}
        {label}
      </button>
    );
  }

  const sending = step.at === "sending";
  const outcome = step.at === "result" ? step.outcome : null;
  return (
    <div role="group" aria-label={label} data-delete={name} data-step={step.at} className="flex min-w-0 flex-col gap-2 rounded-xl border border-line bg-surface px-3 py-2.5 text-[13px]">
      <p className="font-semibold">{label}?</p>
      <div className="text-muted">{explain}</div>
      {outcome !== null && (
        <p role={outcome.kind === "error" ? "alert" : "status"} data-delete-result={outcome.kind} className={outcome.kind === "error" ? "text-bad" : "text-warn"}>
          {clean(outcome.message)}
        </p>
      )}
      {step.at === "done" ? (
        <p role="status" className="text-good">
          Deleted.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {outcome === null && (
            <button type="button" className={DANGER} disabled={sending} onClick={() => void send()}>
              {sending ? "Deleting…" : confirmLabel}
            </button>
          )}
          {outcome?.kind === "error" && outcome.retryable && (
            <button type="button" className={DANGER} onClick={() => void send()}>
              Retry
            </button>
          )}
          {outcome?.kind === "pending" && onRefresh && (
            <button type="button" className={PLAIN} onClick={onRefresh}>
              Refresh
            </button>
          )}
          <button type="button" className={PLAIN} disabled={sending} onClick={() => setStep({ at: "idle" })}>
            {outcome === null ? "Cancel" : "Close"}
          </button>
        </div>
      )}
    </div>
  );
}
