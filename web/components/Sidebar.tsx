"use client";

// The sidebar (04 §3.1): the wordmark and collapse button, New run and the list pages, the recents (signed in)
// and the account row with its menu (signed in) or a Sign in button (signed out). Collapsed, it is a narrow
// icon rail; the collapsed state itself lives in AppShell.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Icon, RookMark, type IconName } from "./icons";
import { startGithubConnect } from "@/lib/github";
import { runHref } from "@/lib/pages";
import { clean } from "@/lib/safeText";
import { signOutAndReload } from "@/lib/session";
import { accountMenuItems, runAccountAction, type AccountMenuKey } from "@/lib/sidebarPrefs";
import { useApi } from "@/lib/useShell";

export type RecentStatus = "running" | "ok" | "broken" | "idle";

export interface RecentRun {
  id: string;
  label: string;
  status: RecentStatus;
}

/** Which sidebar entry the current page is. */
export type NavKey = "home" | "runs" | "counterexamples" | "rules" | "repositories" | "login" | "run";

const DOT: Record<RecentStatus, string> = {
  running: "bg-accent animate-pulse-dot",
  ok: "bg-good",
  broken: "bg-bad",
  idle: "bg-faint",
};

const STATUS_WORD: Record<RecentStatus, string> = { running: "running", ok: "passed", broken: "broken", idle: "stopped" };

const NAV: { key: NavKey; label: string; href: string; icon: IconName }[] = [
  { key: "counterexamples", label: "Counterexamples", href: "/counterexamples", icon: "counterexamples" },
  { key: "rules", label: "Rules", href: "/rules", icon: "rules" },
  { key: "repositories", label: "Repositories", href: "/repositories", icon: "repositories" },
];

const ITEM = "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[14px] transition-colors hover:bg-hover";
const ICON_BUTTON = "grid size-8 flex-none place-items-center rounded-lg text-muted transition-colors hover:bg-hover hover:text-ink";

export interface SidebarProps {
  recents: RecentRun[];
  /** Coins spent today by this viewer's runs. */
  coins: number;
  userName: string;
  email?: string;
  active?: NavKey;
  /** The run shown now, highlighted in the recents. */
  currentRunId?: string;
  /** True while the recents are loading for the first time. */
  recentsLoading?: boolean;
  signedIn?: boolean;
  githubConnected?: boolean;
  /** The icon rail instead of the full sidebar. */
  collapsed?: boolean;
  /** The collapse / expand button (in the mobile drawer it closes the drawer). */
  onToggle?: () => void;
  /** Defaults to signing out of this browser and reloading as a guest. */
  onSignOut?: () => void | Promise<void>;
  /** Defaults to the GitHub App install flow (GET /github/install-url). An error message, or null. */
  onConnectGithub?: () => Promise<string | null>;
  /** Render with the account menu open (tests and stories). */
  defaultMenuOpen?: boolean;
}

function NewRunIcon() {
  return (
    <span aria-hidden className="grid size-[22px] flex-none place-items-center rounded-full bg-accent text-accent-ink">
      <Icon name="plus" size={14} />
    </span>
  );
}

function Avatar({ name }: { name: string }) {
  return (
    <span aria-hidden className="grid size-8 flex-none place-items-center rounded-full bg-ink text-[13px] font-semibold text-app">
      {name.slice(0, 1).toUpperCase() || "?"}
    </span>
  );
}

export function Sidebar(props: SidebarProps) {
  return props.collapsed ? <SidebarRail {...props} /> : <SidebarPanel {...props} />;
}

function SidebarRail({ active, signedIn = false, userName, onToggle }: SidebarProps) {
  const name = clean(userName);
  return (
    <aside className="flex min-h-0 w-full flex-col items-center gap-1 border-r border-line bg-side py-3" aria-label="Sidebar" data-collapsed>
      <button type="button" onClick={onToggle} aria-label="Open sidebar" title="Open sidebar" className={ICON_BUTTON}>
        <Icon name="panel" />
      </button>
      <Link href="/" aria-label="New run" title="New run" className="mt-2 grid size-8 place-items-center rounded-lg hover:bg-hover">
        <NewRunIcon />
      </Link>
      <nav className="flex flex-col items-center gap-1" aria-label="Lists">
        {NAV.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            aria-label={item.label}
            title={item.label}
            aria-current={active === item.key ? "page" : undefined}
            className={`${ICON_BUTTON} ${active === item.key ? "bg-hover text-ink" : ""}`}
          >
            <Icon name={item.icon} />
          </Link>
        ))}
      </nav>
      <div className="flex-1" />
      {signedIn ? (
        <button type="button" onClick={onToggle} aria-label={`Account: ${name}`} title={name} className="rounded-full">
          <Avatar name={name} />
        </button>
      ) : (
        <Link href="/login" aria-label="Sign in" title="Sign in" className={ICON_BUTTON}>
          <Icon name="signin" />
        </Link>
      )}
    </aside>
  );
}

function SidebarPanel({
  recents,
  coins,
  userName,
  email = "",
  active,
  currentRunId,
  recentsLoading = false,
  signedIn = false,
  githubConnected = false,
  onToggle,
  onSignOut,
  onConnectGithub,
  defaultMenuOpen = false,
}: SidebarProps) {
  const name = clean(userName);
  return (
    <aside className="flex min-h-0 w-full flex-col border-r border-line bg-side" aria-label="Sidebar">
      <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
        <Link href="/" className="flex items-center gap-2 rounded-lg px-1.5 py-1" aria-label="Rook home">
          <RookMark />
          <span className="font-serif text-[22px] leading-none tracking-tight">Rook</span>
        </Link>
        {onToggle && (
          <button type="button" onClick={onToggle} aria-label="Close sidebar" title="Close sidebar" className={ICON_BUTTON}>
            <Icon name="panel" />
          </button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
        <nav className="flex flex-col gap-0.5" aria-label="Lists">
          <Link href="/" aria-current={active === "home" ? "page" : undefined} className={`${ITEM} font-medium`}>
            <NewRunIcon />
            New run
          </Link>
          {NAV.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              aria-current={active === item.key ? "page" : undefined}
              className={`${ITEM} ${active === item.key ? "bg-hover text-ink" : "text-ink/90"}`}
            >
              <span className="grid size-[22px] place-items-center text-muted">
                <Icon name={item.icon} />
              </span>
              {item.label}
            </Link>
          ))}
        </nav>

        {signedIn && (
          <section aria-label="Recents" className="mt-5 flex flex-col">
            <div className="flex items-center justify-between px-2.5 pb-1">
              <h2 className="text-[12px] font-medium text-faint">Recents</h2>
              <Link href="/runs" aria-current={active === "runs" ? "page" : undefined} className="text-[12px] text-faint hover:text-ink">
                All runs
              </Link>
            </div>
            {recentsLoading && recents.length === 0 ? (
              <div className="flex flex-col gap-2.5 px-2.5 py-1.5" aria-hidden data-skeleton="recents">
                <span className="h-3 w-3/4 animate-pulse rounded bg-hover" />
                <span className="h-3 w-1/2 animate-pulse rounded bg-hover" />
                <span className="h-3 w-2/3 animate-pulse rounded bg-hover" />
              </div>
            ) : recents.length === 0 ? (
              <p className="px-2.5 py-1 text-[13px] text-muted">No runs yet. Pick a repository to start.</p>
            ) : (
              <ul className="flex flex-col gap-px" data-recents>
                {recents.map((run) => {
                  const current = run.id === currentRunId;
                  const label = clean(run.label);
                  return (
                    <li key={run.id}>
                      <Link
                        href={runHref(run.id)}
                        aria-current={current ? "page" : undefined}
                        title={label}
                        className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13.5px] transition-colors hover:bg-hover ${
                          current ? "bg-hover text-ink" : "text-ink/85"
                        }`}
                      >
                        <span aria-hidden data-dot={run.status} className={`size-1.5 flex-none rounded-full ${DOT[run.status]}`} />
                        <span className="min-w-0 truncate">{label}</span>
                        <span className="sr-only">({STATUS_WORD[run.status]})</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}
      </div>

      <div className="border-t border-line p-2">
        {signedIn ? (
          <AccountRow
            name={name}
            email={clean(email)}
            coins={coins}
            githubConnected={githubConnected}
            onSignOut={onSignOut}
            onConnectGithub={onConnectGithub}
            defaultOpen={defaultMenuOpen}
          />
        ) : (
          <Link
            href="/login"
            aria-current={active === "login" ? "page" : undefined}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-ink px-3 py-2 text-[14px] font-medium text-app transition-opacity hover:opacity-90"
            data-sign-in
          >
            Sign in
          </Link>
        )}
      </div>
    </aside>
  );
}

interface AccountRowProps {
  name: string;
  email: string;
  coins: number;
  githubConnected: boolean;
  onSignOut?: SidebarProps["onSignOut"];
  onConnectGithub?: SidebarProps["onConnectGithub"];
  defaultOpen: boolean;
}

function AccountRow({ name, email, coins, githubConnected, onSignOut, onConnectGithub, defaultOpen }: AccountRowProps) {
  const api = useApi();
  const [open, setOpen] = useState(defaultOpen);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    const onPointer = (e: PointerEvent) => {
      if (box.current && e.target instanceof Node && !box.current.contains(e.target)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const choose = (key: AccountMenuKey) => {
    setError(null);
    void runAccountAction(key, {
      signOut: onSignOut ?? signOutAndReload,
      connectGithub: onConnectGithub ?? (() => startGithubConnect(api, (url) => window.location.assign(url))),
    }).then(setError);
  };

  return (
    <div ref={box} className="relative">
      {open && (
        <div role="menu" aria-label="Account" className="absolute inset-x-0 bottom-full z-40 mb-1.5 flex flex-col gap-0.5 rounded-xl border border-line bg-surface p-1.5 shadow-lg shadow-black/30">
          {email && <p className="truncate px-2.5 pb-1 pt-0.5 text-[12.5px] text-muted">{email}</p>}
          {accountMenuItems(githubConnected).map((item) =>
            item.key === "github-connected" ? (
              <Link key={item.key} role="menuitem" href="/repositories" className={`${ITEM} text-[13.5px]`} data-github-connected>
                <Icon name="github" className="text-muted" />
                {item.label}
                <Icon name="check" className="ml-auto text-good" />
              </Link>
            ) : (
              <button key={item.key} type="button" role="menuitem" onClick={() => choose(item.key)} className={`${ITEM} text-[13.5px]`}>
                <Icon name={item.key === "sign-out" ? "signout" : "github"} className="text-muted" />
                {item.label}
              </button>
            ),
          )}
          {error !== null && (
            <p role="alert" className="px-2.5 pb-1 text-[12.5px] text-bad">
              {clean(error)}
            </p>
          )}
        </div>
      )}
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-hover"
        data-account
      >
        <Avatar name={name} />
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate text-[13.5px] font-medium" title={name}>
            {name}
          </span>
          <span className="text-[12px] text-muted">
            <span className="num">{coins.toFixed(2)}</span> coins today
          </span>
        </span>
        <Icon name="chevrons" className="text-muted" />
      </button>
    </div>
  );
}
