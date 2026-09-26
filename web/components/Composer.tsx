"use client";

// The composer (04 §3.1). The repo picker (ROOK-036) and the auto-approve toggle are placeholders here.

import { useState, type FormEvent, type KeyboardEvent } from "react";

export interface ComposerProps {
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
  repoLabel?: string;
}

export function Composer({ onSend, disabled = false, placeholder = 'Describe what to check, or "find bugs"', repoLabel }: ComposerProps) {
  const [text, setText] = useState("");

  const send = () => {
    const value = text.trim();
    if (value === "" || disabled) return;
    onSend?.(value);
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
    <form className="mx-auto flex max-w-[760px] flex-col gap-2" onSubmit={onSubmit}>
      <div className="flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-app px-2.5 py-1 text-[13px]">Sandbox</span>
        <button
          type="button"
          className={`inline-flex items-center gap-1.5 rounded-lg border bg-app px-2.5 py-1 text-[13px] ${repoLabel ? "border-accent" : "border-line"}`}
        >
          <span aria-hidden>+</span>
          {repoLabel ?? "Select repository…"}
        </button>
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
        <button type="submit" disabled={disabled || text.trim() === ""} aria-label="Send" className="text-[15px] text-faint disabled:opacity-40">
          ↵
        </button>
      </div>
      <div className="flex flex-wrap justify-between gap-2.5 px-1 text-[12.5px] text-muted">
        <span>+ Auto-approve: off</span>
        <span>Bob · 13 agents</span>
      </div>
    </form>
  );
}
