"use client";

// The repo picker (04 §3.3): a pill chip above the composer ("Select repository…", then the picked repo) that
// opens a popover with a search box, "Your repositories" (GitHub, once connected), the "Examples" (the demo
// repos, last), and a footer: "Connect GitHub" (signed in, not linked), "Add repositories" (linked; the App's
// install page) or "Sign in to use your repositories" (a guest). Keyboard: the search box keeps the focus;
// ↑/↓ move, Enter picks, Esc closes.

import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { RepoIcon } from "./Composer";
import type { RepoOption } from "@/lib/api";
import { filterGroups, moveIndex, pickerOptions, repoKey, repoMeta, type PickerGroups } from "@/lib/pages";
import { clean } from "@/lib/safeText";

export interface RepoPickerProps {
  groups: PickerGroups;
  selected: RepoOption | null;
  onSelect: (repo: RepoOption) => void;
  /** "Connect GitHub" / "Add repositories": goes to the GitHub App's install page (ROOK-031). */
  onConnectGithub?: () => void;
  loading?: boolean;
  /** Shown in the popover when the repos couldn't load. */
  error?: string | null;
  onRetry?: () => void;
  defaultOpen?: boolean;
}

export function RepoPicker({ groups, selected, onSelect, onConnectGithub, loading = false, error = null, onRetry, defaultOpen = false }: RepoPickerProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [query, setQuery] = useState("");
  const shown = filterGroups(groups, query);
  const options = pickerOptions(shown);
  const selectedKey = selected === null ? null : repoKey(selected);
  const [active, setActive] = useState(-1);
  const searchRef = useRef<HTMLInputElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const listId = `${id}-list`;
  // pickerGroups leaves both GitHub fields empty only for a guest.
  const guest = groups.github === null && !groups.connectGithub;

  useEffect(() => {
    if (open) searchRef.current?.focus();
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
    setQuery("");
    buttonRef.current?.focus();
  };
  const pick = (repo: RepoOption) => {
    onSelect(repo);
    close();
  };
  const openMenu = () => {
    const all = pickerOptions(groups);
    const at = selectedKey === null ? -1 : all.findIndex((o) => repoKey(o) === selectedKey);
    setActive(at >= 0 ? at : all.length > 0 ? 0 : -1);
    setOpen(true);
  };

  const onButtonKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      openMenu();
    }
  };
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => moveIndex(i, e.key === "ArrowDown" ? 1 : -1, options.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const repo = options[active];
      if (repo !== undefined) pick(repo);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "Tab") {
      close();
    }
  };

  const optionId = (index: number) => `${id}-opt-${index}`;
  let index = -1;
  const item = (repo: RepoOption) => {
    index += 1;
    const i = index;
    const isSelected = repoKey(repo) === selectedKey;
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
        className={`flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13.5px] ${i === active ? "bg-hover" : ""}`}
      >
        <RepoIcon />
        <span className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap">{clean(repo.name)}</span>
        <span className="flex-none text-[12px] text-faint">{repoMeta(repo)}</span>
        <span aria-hidden className={`w-3 flex-none text-accent ${isSelected ? "" : "invisible"}`}>
          ✓
        </span>
      </div>
    );
  };

  const group = (label: string, body: ReactNode) => (
    <div role="group" aria-label={label} className="flex flex-col">
      <div role="presentation" className="px-2.5 pb-1 pt-2 text-[11px] font-medium text-faint">
        {label}
      </div>
      {body}
    </div>
  );
  const note = (text: string) => <p className="px-2.5 py-1.5 text-[13px] text-muted">{text}</p>;
  const footerButton = "w-full rounded-lg px-2.5 py-1.5 text-left text-[13.5px] hover:bg-hover disabled:cursor-not-allowed disabled:text-muted";

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={onButtonKey}
        className="inline-flex max-w-[70vw] items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-[12.5px] text-ink hover:bg-hover"
      >
        {selected !== null && <RepoIcon />}
        <span className="overflow-hidden text-ellipsis whitespace-nowrap">{selected !== null ? clean(selected.name) : "Select repository…"}</span>
        <svg aria-hidden viewBox="0 0 16 16" className="size-3 flex-none text-faint" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="m4 6 4 4 4-4" />
        </svg>
      </button>
      {open && (
        <div
          data-repo-popover
          className="absolute bottom-full left-0 z-10 mb-1.5 flex w-[min(400px,calc(100vw-32px))] flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-lg"
        >
          <div className="border-b border-line p-1.5">
            <input
              ref={searchRef}
              type="text"
              role="combobox"
              aria-expanded
              aria-controls={listId}
              aria-autocomplete="list"
              aria-activedescendant={active >= 0 && active < options.length ? optionId(active) : undefined}
              aria-label="Search repositories"
              placeholder="Search repositories"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={onSearchKey}
              className="w-full rounded-lg bg-transparent px-2 py-1.5 text-[13.5px] text-ink outline-none placeholder:text-faint"
            />
          </div>
          <div id={listId} role="listbox" aria-label="Repositories" className="flex max-h-[280px] flex-col overflow-y-auto p-1.5">
            {loading ? (
              note("Loading…")
            ) : error !== null ? (
              <p role="alert" className="flex items-center gap-2 px-2.5 py-1.5 text-[13px] text-bad">
                {clean(error)}
                {onRetry && (
                  <button type="button" onClick={onRetry} className="text-link underline">
                    Retry
                  </button>
                )}
              </p>
            ) : (
              <>
                {shown.github !== null &&
                  group(
                    "Your repositories",
                    shown.github.length > 0 ? shown.github.map(item) : note(query.trim() ? "No matches." : "No repositories shared with Rook yet."),
                  )}
                {shown.demo.length > 0 && group("Examples", shown.demo.map(item))}
                {options.length === 0 && shown.github === null && note(query.trim() ? "No matches." : "No repositories on this server yet.")}
              </>
            )}
          </div>
          <div className="border-t border-line p-1.5" data-picker-footer>
            {guest ? (
              <Link href="/login" className={`${footerButton} block text-link`}>
                Sign in to use your repositories
              </Link>
            ) : (
              <button type="button" onClick={onConnectGithub} disabled={!onConnectGithub} className={`${footerButton} text-link`}>
                {groups.connectGithub ? "Connect GitHub" : "Add repositories"}
                {!onConnectGithub && " (coming soon)"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
