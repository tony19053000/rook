"use client";

// The composer (04 §3.1): the sandbox chip, the repo picker slot (or a fixed repo label on a run page), the
// input, and the auto-approve toggle when the page offers one.

import { useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

export interface ComposerProps {
  onSend?: (text: string) => void | boolean;
  disabled?: boolean;
  placeholder?: string;
  repoLabel?: string;
  /** Replaces the repo label chip, e.g. the RepoPicker on the home page. */
  picker?: ReactNode;
  /** The auto-approve toggle; shown only when `onAutoChange` is given. */
  auto?: boolean;
  onAutoChange?: (auto: boolean) => void;
  /** Allow sending an empty message (the home page falls back to "Find bugs"). */
  allowEmpty?: boolean;
}

export function Composer({
  onSend,
  disabled = false,
  placeholder = 'Describe what to check, or "find bugs"',
  repoLabel,
  picker,
  auto = false,
  onAutoChange,
  allowEmpty = false,
}: ComposerProps) {
  const [text, setText] = useState("");

  const send = () => {
    const value = text.trim();
    if ((value === "" && !allowEmpty) || disabled) return;
    // A handler that returns false refused the message (e.g. no repo yet), so the text stays.
    if (onSend?.(value) === false) return;
    setText("");
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <form className="mx-auto flex w-full max-w-[760px] flex-col gap-2" onSubmit={onSubmit}>
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-app px-2.5 py-1 text-[13px]">Docker sandbox</span>
        {picker ?? (
          <span className={`inline-flex items-center gap-1.5 rounded-lg border bg-app px-2.5 py-1 text-[13px] ${repoLabel ? "border-accent" : "border-line"}`}>
            <span aria-hidden>▢</span>
            {repoLabel ?? "No repository"}
          </span>
        )}
      </div>
      <div className="flex min-h-[46px] items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 py-2.5">
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          id="composer-input"
          rows={1}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          className="flex-1 resize-none bg-transparent text-ink outline-none placeholder:text-faint disabled:opacity-60"
        />
        <button type="submit" disabled={disabled || (!allowEmpty && text.trim() === "")} aria-label="Send" className="text-[15px] text-faint disabled:opacity-40">
          ↵
        </button>
      </div>
      <div className="flex flex-wrap justify-between gap-2.5 px-1 text-[12.5px] text-muted">
        {onAutoChange ? (
          <label className="inline-flex cursor-pointer items-center gap-1.5">
            <input type="checkbox" checked={auto} onChange={(e) => onAutoChange(e.target.checked)} className="accent-[var(--accent)]" />
            Auto-approve: {auto ? "on" : "off"}
          </label>
        ) : (
          <span />
        )}
        <span>Bob · 13 agents</span>
      </div>
    </form>
  );
}
