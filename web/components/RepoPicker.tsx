"use client";

// The repo picker (04 §3.3): a dropdown above the composer with "Your GitHub repositories" (once connected)
// and "Demo repositories" (always; the only group for a guest). Each item shows its name, private/public and
// the language. Keyboard: Enter/Space/↓ open it, ↑/↓ move, Enter picks, Esc closes.

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { RepoOption } from "@/lib/api";
import { moveIndex, pickerOptions, repoKey, repoMeta, type PickerGroups } from "@/lib/pages";
import { clean } from "@/lib/safeText";

export interface RepoPickerProps {
  groups: PickerGroups;
  selected: RepoOption | null;
  onSelect: (repo: RepoOption) => void;
  /** "Connect GitHub" (ROOK-031 wires the install URL). */
  onConnectGithub?: () => void;
  loading?: boolean;
  /** Shown in the menu when the repos couldn't load. */
  error?: string | null;
  onRetry?: () => void;
  defaultOpen?: boolean;
}

export function RepoPicker({ groups, selected, onSelect, onConnectGithub, loading = false, error = null, onRetry, defaultOpen = false }: RepoPickerProps) {
  const [open, setOpen] = useState(defaultOpen);
  const options = pickerOptions(groups);
  const selectedIndex = selected === null ? -1 : options.findIndex((o) => repoKey(o) === repoKey(selected));
  const [active, setActive] = useState(selectedIndex);
  const listRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (open) listRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  const pick = (repo: RepoOption) => {
    onSelect(repo);
    close();
  };
  const openMenu = () => {
    setActive(selectedIndex >= 0 ? selectedIndex : options.length > 0 ? 0 : -1);
    setOpen(true);
  };

  const onButtonKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      openMenu();
    }
  };
  const onListKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => moveIndex(i, e.key === "ArrowDown" ? 1 : -1, options.length));
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setActive(options.length === 0 ? -1 : e.key === "Home" ? 0 : options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const repo = options[active];
      if (repo !== undefined) pick(repo);
    } else if (e.key === "Escape" || e.key === "Tab") {
      if (e.key === "Escape") e.preventDefault();
      close();
    }
  };

  const optionId = (index: number) => `${id}-opt-${index}`;
  let index = -1;
  const item = (repo: RepoOption) => {
    index += 1;
    const i = index;
    const isSelected = i === selectedIndex;
    return (
      <div
        key={repoKey(repo)}
        id={optionId(i)}
        role="option"
        aria-selected={isSelected}
        data-repo={repoKey(repo)}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => pick(repo)}
        onMouseEnter={() => setActive(i)}
        className={`flex cursor-pointer items-center justify-between gap-3 rounded-md px-2.5 py-1.5 text-[13.5px] ${i === active ? "bg-hover" : ""}`}
      >
        <span className="flex items-center gap-1.5 overflow-hidden text-ellipsis whitespace-nowrap">
          {isSelected && <span aria-hidden>✓</span>}
          {clean(repo.name)}
        </span>
        <span className="flex-none text-[12px] text-muted">{repoMeta(repo)}</span>
      </div>
    );
  };

  const heading = (text: string) => (
    <div role="presentation" className="px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[.08em] text-faint">
      {text}
    </div>
  );

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={onButtonKey}
        className={`inline-flex items-center gap-1.5 rounded-lg border bg-app px-2.5 py-1 text-[13px] hover:bg-hover ${selected ? "border-accent" : "border-line"}`}
      >
        <span aria-hidden>{selected ? "▢" : "+"}</span>
        {selected ? clean(selected.name) : "Select repository…"}
        <span aria-hidden className="text-faint">
          ⌄
        </span>
      </button>
      {open && (
        <div
          ref={listRef}
          id={`${id}-list`}
          role="listbox"
          tabIndex={-1}
          aria-label="Repositories"
          aria-activedescendant={active >= 0 ? optionId(active) : undefined}
          onKeyDown={onListKey}
          className="absolute bottom-full left-0 z-10 mb-1.5 flex max-h-[320px] w-[min(420px,85vw)] flex-col overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-lg outline-none"
        >
          {groups.github !== null && (
            <>
              {heading("Your GitHub repositories")}
              {groups.github.length === 0 ? <p className="px-2.5 py-1 text-[13px] text-muted">No repositories shared with Rook yet.</p> : groups.github.map(item)}
            </>
          )}
          {groups.connectGithub && (
            <>
              {heading("Your GitHub repositories")}
              <button type="button" onClick={onConnectGithub} disabled={!onConnectGithub} className="rounded-md px-2.5 py-1.5 text-left text-[13.5px] text-link hover:bg-hover disabled:text-muted">
                Connect GitHub{!onConnectGithub && " (coming soon)"}
              </button>
            </>
          )}
          {heading("Demo repositories")}
          {loading ? (
            <p className="px-2.5 py-1 text-[13px] text-muted">Loading…</p>
          ) : error !== null ? (
            <p role="alert" className="flex items-center gap-2 px-2.5 py-1 text-[13px] text-bad">
              {clean(error)}
              {onRetry && (
                <button type="button" onClick={onRetry} className="text-link underline">
                  Retry
                </button>
              )}
            </p>
          ) : groups.demo.length === 0 ? (
            <p className="px-2.5 py-1 text-[13px] text-muted">No demo repositories on this server.</p>
          ) : (
            groups.demo.map(item)
          )}
        </div>
      )}
    </div>
  );
}
