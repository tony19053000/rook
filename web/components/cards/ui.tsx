"use client";

// Shared pieces of the inline cards (04 §3.4, docs/mockups/4-web-app.html): the card frame, pills, buttons,
// the collapsed answer line, and the answer plumbing (context, send state, guest countdown).

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Mark } from "../AgentRow";
import { GUEST_AUTO_SECONDS, type SendOutcome } from "@/lib/questions";
import type { QuestionItem } from "@/lib/runStore";

// ---------------------------------------------------------------------------
// Frame
// ---------------------------------------------------------------------------

export type Tone = "good" | "bad" | "warn" | "idle";

const PILL: Record<Tone, string> = {
  good: "bg-good-soft text-good",
  bad: "bg-bad-soft text-bad",
  warn: "bg-warn-soft text-warn",
  idle: "bg-sunk text-faint",
};

export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span data-pill={tone} className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${PILL[tone]}`}>
      {children}
    </span>
  );
}

export function Label({ children, tone }: { children: ReactNode; tone?: "bad" }) {
  return (
    <span className={`text-[11px] font-semibold uppercase tracking-[.08em] ${tone === "bad" ? "text-bad" : "text-faint"}`}>{children}</span>
  );
}

export function Card({ children, alert = false, name }: { children: ReactNode; alert?: boolean; name: string }) {
  return (
    <div
      data-card={name}
      className={`flex min-w-0 flex-col gap-2.5 rounded-xl border bg-surface px-4 py-3.5 ${alert ? "border-bad" : "border-line"}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({ label, pill, labelTone }: { label: ReactNode; pill?: ReactNode; labelTone?: "bad" }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Label tone={labelTone}>{label}</Label>
      {pill}
    </div>
  );
}

export function Button({
  children,
  primary = false,
  disabled = false,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  primary?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-50 ${
        primary ? "border-accent bg-accent text-accent-ink" : "border-line bg-app text-ink hover:bg-hover"
      }`}
    >
      {children}
    </button>
  );
}

/** `✓ <answer>` once a question is answered, `(auto)` when the run answered it. */
export function AnsweredLine({ text, by }: { text: string; by?: "user" | "auto" | null }) {
  return (
    <span data-answered className="text-[13px] font-semibold text-good">
      <Mark ok /> {text}
      {by === "auto" && <span className="ml-1.5 font-normal text-faint">(auto)</span>}
    </span>
  );
}

export function Note({ tone, children }: { tone: "bad" | "warn" | "muted"; children: ReactNode }) {
  const color = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-muted";
  return (
    <span role={tone === "bad" ? "alert" : undefined} className={`text-[13px] ${color}`}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Answering
// ---------------------------------------------------------------------------

export interface RunActions {
  /** POST /runs/{id}/answers through api.ts; never throws. */
  answer: (questionId: string, answer: unknown) => Promise<SendOutcome>;
  /** Guest demo mode: open questions auto-answer "yes" after a countdown (04 §3.4). */
  guest: boolean;
  autoSeconds: number;
}

const READ_ONLY: RunActions = {
  answer: async () => ({ status: "closed", message: "Answers are not available here." }),
  guest: false,
  autoSeconds: GUEST_AUTO_SECONDS,
};

export const RunActionsContext = createContext<RunActions>(READ_ONLY);

export function useRunActions(): RunActions {
  return useContext(RunActionsContext);
}

export interface AnswerState {
  status: "idle" | "sending" | "sent" | "closed" | "error";
  message: string | null;
  /** What the user chose, shown until question.answered arrives. */
  shown: string | null;
}

/** One answer per question: while sending, after it is accepted, or once closed, the buttons are off. */
export function useAnswer(question: QuestionItem) {
  const actions = useRunActions();
  const [state, setState] = useState<AnswerState>({ status: "idle", message: null, shown: null });
  const busy = useRef(false);

  const submit = async (answer: unknown, shown: string) => {
    if (busy.current || question.answered) return;
    busy.current = true;
    setState({ status: "sending", message: null, shown });
    const outcome = await actions.answer(question.questionId, answer);
    if (outcome.status === "error") busy.current = false; // a retry is allowed
    setState({ status: outcome.status, message: outcome.status === "sent" ? null : outcome.message, shown });
  };

  const locked = question.answered || state.status === "sending" || state.status === "sent" || state.status === "closed";
  return { state, submit, locked };
}

/** What an answer area shows once it is no longer open, or null while it still takes input. */
export function ClosedAnswer({ question, state, describe }: { question: QuestionItem; state: AnswerState; describe: (a: unknown) => string }) {
  if (question.answered) return <AnsweredLine text={describe(question.answer)} by={question.answeredBy} />;
  if (state.status === "sent") return <AnsweredLine text={state.shown ?? "Sent"} />;
  if (state.status === "closed") return <Note tone="warn">{state.message}</Note>;
  return null;
}

/**
 * The guest countdown: counts down from `seconds` while `enabled`, then calls `onFire` once. `stop()` cancels
 * it for good (the user took over).
 */
export function useCountdown(enabled: boolean, seconds: number, onFire: () => void) {
  const [left, setLeft] = useState(seconds);
  const [stopped, setStopped] = useState(false);
  const fire = useRef(onFire);
  useEffect(() => {
    fire.current = onFire;
  });
  const active = enabled && !stopped;

  useEffect(() => {
    if (!active) return;
    let remaining = seconds;
    setLeft(remaining);
    const timer = setInterval(() => {
      remaining -= 1;
      setLeft(remaining);
      if (remaining <= 0) {
        clearInterval(timer);
        fire.current();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [active, seconds]);

  return { left: active ? Math.max(0, left) : null, stop: () => setStopped(true) };
}

export function Countdown({ left, onStop, what }: { left: number | null; onStop: () => void; what: string }) {
  if (left === null) return null;
  return (
    <span data-countdown className="num inline-flex items-center gap-2 text-[12.5px] text-muted" role="timer" aria-live="off">
      Demo: {what} in {left}s
      <button type="button" className="underline hover:text-ink" onClick={onStop}>
        Stop
      </button>
    </span>
  );
}
