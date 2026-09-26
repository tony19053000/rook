// The sidebar (04 §3.1): the brand, Home | Runs, New run, the list pages, the recents with status dots, the
// "Add to CI" hint and the account line.

import Link from "next/link";
import { AgentSprite } from "./AgentSprite";
import { MASCOT } from "@/lib/agents";
import { runHref } from "@/lib/pages";
import { clean } from "@/lib/safeText";

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

const NAV: { key: NavKey; label: string; href: string }[] = [
  { key: "counterexamples", label: "Counterexamples", href: "/counterexamples" },
  { key: "rules", label: "Rules", href: "/rules" },
  { key: "repositories", label: "Repositories", href: "/repositories" },
];

const ITEM = "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left hover:bg-hover";

export interface SidebarProps {
  recents: RecentRun[];
  coins: number;
  userName: string;
  active?: NavKey;
  /** The run shown now, highlighted in the recents. */
  currentRunId?: string;
  /** True while the recents are loading for the first time. */
  recentsLoading?: boolean;
  signedIn?: boolean;
}

export function Sidebar({ recents, coins, userName, active, currentRunId, recentsLoading = false, signedIn = false }: SidebarProps) {
  const name = clean(userName);
  const onRuns = active === "runs" || active === "run";
  return (
    <aside className="flex min-h-0 w-full flex-col gap-1 overflow-y-auto border-r border-line bg-side px-2.5 py-3" aria-label="Sidebar">
      <Link href="/" className="flex items-center gap-2 px-2 pb-2.5 pt-1">
        <AgentSprite look={MASCOT} px={2} animate={false} />
        <span className="font-serif text-[21px] tracking-tight">Rook</span>
      </Link>
      <nav className="mb-2 grid grid-cols-2 rounded-lg bg-sunk p-[3px]" aria-label="View">
        <Link href="/" aria-current={active === "home" ? "page" : undefined} className={`rounded-md p-1 text-center text-[13px] ${active === "home" ? "bg-hover" : "text-muted"}`}>
          Home
        </Link>
        <Link href="/runs" aria-current={active === "runs" ? "page" : undefined} className={`rounded-md p-1 text-center text-[13px] ${onRuns ? "bg-hover" : "text-muted"}`}>
          Runs
        </Link>
      </nav>
      <Link href="/" className={`${ITEM} bg-hover`}>
        <span aria-hidden>+</span>New run
      </Link>
      <nav className="flex flex-col gap-1" aria-label="Lists">
        {NAV.map((item) => (
          <Link key={item.key} href={item.href} aria-current={active === item.key ? "page" : undefined} className={`${ITEM} ${active === item.key ? "bg-hover" : ""}`}>
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="px-2.5 pb-1.5 pt-4 text-[12.5px] text-faint">Recents</div>
      {recentsLoading && recents.length === 0 ? (
        <div className="flex flex-col gap-2 px-2.5" aria-hidden data-skeleton="recents">
          <span className="h-3 w-3/4 animate-pulse rounded bg-hover" />
          <span className="h-3 w-1/2 animate-pulse rounded bg-hover" />
        </div>
      ) : recents.length === 0 ? (
        <p className="px-2.5 text-[13px] text-muted">No runs yet. Pick a repository to start.</p>
      ) : (
        <ul className="flex flex-col" data-recents>
          {recents.map((run) => (
            <li key={run.id}>
              <Link
                href={runHref(run.id)}
                aria-current={run.id === currentRunId ? "page" : undefined}
                className={`flex items-center gap-2 overflow-hidden whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13.5px] hover:bg-hover ${
                  run.id === currentRunId ? "bg-hover" : ""
                }`}
              >
                <span aria-hidden data-dot={run.status} className={`size-1.5 flex-none rounded-full ${DOT[run.status]}`} />
                <span className="overflow-hidden text-ellipsis">{clean(run.label)}</span>
                <span className="sr-only">({STATUS_WORD[run.status]})</span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <div className="flex-1" />
      <div className="flex flex-col gap-0.5 rounded-lg border border-line px-2.5 py-2 text-[12.5px] text-muted">
        <b className="font-semibold text-ink">Add to CI</b>Run on every pull request with <code className="font-mono">rook run --ci</code>
      </div>
      <div className="mt-2 flex items-center gap-2 border-t border-line px-1.5 pt-2.5 text-[13.5px]">
        <span aria-hidden className="grid size-6 place-items-center rounded-full bg-hover text-[11px] font-semibold">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span>{name}</span>
        <span className="text-faint">
          · <span className="num">{coins.toFixed(2)}</span> coins
        </span>
        {!signedIn && (
          <Link href="/login" className="ml-auto text-[12.5px] text-link underline-offset-2 hover:underline">
            Sign in
          </Link>
        )}
      </div>
    </aside>
  );
}
