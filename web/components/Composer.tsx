"use client";

// The composer (04 §3.1): a row of chips (the IBM Bob environment and the repo picker, or a fixed repo label on a
// run page), the input with the send arrow, and a thin row under it (the "Auto" switch when the page offers one,
// and the Bob mode on the right). Enter sends, Shift+Enter adds a new line.

import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

/** The tooltip that explains the "Auto" switch. */
export const AUTO_TOOLTIP = "Auto: Rook answers its own questions (approves the rules and the fix) instead of waiting for you.";

export interface ComposerProps {
  onSend?: (text: string) => void | boolean;
  disabled?: boolean;
  /** False keeps the send arrow (and Enter) off, e.g. until a repository is picked. */
  canSend?: boolean;
  placeholder?: string;
  repoLabel?: string;
  /** Replaces the repo label chip, e.g. the RepoPicker on the home page. */
  picker?: ReactNode;
  /** The "Auto" switch; shown only when `onAutoChange` is given. */
  auto?: boolean;
  onAutoChange?: (auto: boolean) => void;
  /** Allow sending an empty message (the home page falls back to "Find bugs"). */
  allowEmpty?: boolean;
  /** The right side of the row under the input, e.g. "IBM Bob · live". */
  status?: string;
}

const CHIP = "inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[12.5px] text-ink";

export function Composer({
  onSend,
  disabled = false,
  canSend = true,
  placeholder = "Describe what to check, or ask a question",
  repoLabel,
  picker,
  auto = false,
  onAutoChange,
  allowEmpty = false,
  status = "IBM Bob",
}: ComposerProps) {
  const [text, setText] = useState("");
  const blocked = disabled || !canSend || (!allowEmpty && text.trim() === "");

  const send = () => {
    if (blocked) return;
    // A handler that returns false refused the message (e.g. the CLI hint), so the text stays.
    if (onSend?.(text.trim()) === false) return;
    setText("");
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <form className="mx-auto flex w-full max-w-[760px] flex-col gap-2" onSubmit={onSubmit}>
      <div className="flex flex-wrap items-center gap-1.5" data-composer-chips>
        <span className={CHIP} data-env>
          <span aria-hidden className="size-1.5 rounded-full bg-accent" />
          IBM Bob
        </span>
        {picker ?? (
          <span className={CHIP}>
            <RepoIcon />
            {repoLabel ?? "No repository"}
          </span>
        )}
      </div>
      <div className="flex items-end gap-2 rounded-2xl border border-line bg-surface py-2.5 pl-4 pr-2.5 shadow-sm focus-within:border-muted">
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          rows={2}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          className="max-h-[200px] min-h-[44px] flex-1 resize-none self-center bg-transparent py-1 text-[15px] leading-snug text-ink outline-none [field-sizing:content] placeholder:text-faint disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={blocked}
          aria-label="Send"
          title={canSend ? "Send (Enter)" : "Select a repository first"}
          className="grid size-8 flex-none place-items-center rounded-lg bg-accent text-accent-ink hover:opacity-90 disabled:cursor-not-allowed disabled:bg-line disabled:text-faint"
        >
          <svg aria-hidden viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" />
          </svg>
        </button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2.5 px-1 text-[12px] text-muted">
        {onAutoChange ? (
          <button
            type="button"
            role="switch"
            aria-checked={auto}
            title={AUTO_TOOLTIP}
            onClick={() => onAutoChange(!auto)}
            className="inline-flex items-center gap-1.5 rounded-md px-1 py-0.5 hover:bg-hover hover:text-ink"
          >
            <span aria-hidden className={`relative h-3.5 w-6 rounded-full transition-colors ${auto ? "bg-accent" : "bg-line"}`}>
              <span className={`absolute top-0.5 size-2.5 rounded-full bg-ink transition-[left] ${auto ? "left-3" : "left-0.5"}`} />
            </span>
            Auto
          </button>
        ) : (
          <span />
        )}
        <span data-mode>{status}</span>
      </div>
    </form>
  );
}

/** A small repository glyph for the repo chips. */
export function RepoIcon() {
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="size-3.5 flex-none text-muted" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M3.5 2.5h8a1 1 0 0 1 1 1v9h-8.5a1 1 0 0 1-1-1v-8a1 1 0 0 1 .5-1Z" />
      <path d="M3 11.5a1 1 0 0 1 1-1h8.5M6 2.5v5l1.25-1 1.25 1v-5" />
    </svg>
  );
}
