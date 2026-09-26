// The sidebar (04 §3.1). Navigation targets arrive with ROOK-036.

import { AgentSprite } from "./AgentSprite";
import { MASCOT } from "@/lib/agents";

export type RecentStatus = "running" | "ok" | "broken" | "idle";

export interface RecentRun {
  id: string;
  label: string;
  status: RecentStatus;
}

const DOT: Record<RecentStatus, string> = {
  running: "bg-accent animate-pulse-dot",
  ok: "bg-good",
  broken: "bg-bad",
  idle: "bg-faint",
};

const NAV = ["Counterexamples", "Rules", "Repositories"] as const;

export function Sidebar({ recents, coins, userName }: { recents: RecentRun[]; coins: number; userName: string }) {
  return (
    <aside className="flex min-h-0 w-full flex-col gap-1 border-r border-line bg-side px-2.5 py-3" aria-label="Sidebar">
      <div className="flex items-center gap-2 px-2 pb-2.5 pt-1">
        <AgentSprite look={MASCOT} px={2} animate={false} />
        <span className="font-serif text-[21px] tracking-tight">Rook</span>
      </div>
      <div className="mb-2 grid grid-cols-2 rounded-lg bg-sunk p-[3px]" role="group" aria-label="View">
        <button type="button" className="rounded-md p-1 text-[13px] text-muted">
          Home
        </button>
        <button type="button" className="rounded-md bg-hover p-1 text-[13px]" aria-pressed="true">
          Runs
        </button>
      </div>
      <button type="button" className="flex w-full items-center gap-2.5 rounded-lg bg-hover px-2.5 py-[7px] text-left">
        <span aria-hidden>+</span>New run
      </button>
      {NAV.map((label) => (
        <button key={label} type="button" className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-[7px] text-left hover:bg-hover">
          {label}
        </button>
      ))}

      <div className="px-2.5 pb-1.5 pt-4 text-[12.5px] text-faint">Recents</div>
      {recents.length === 0 ? (
        <p className="px-2.5 text-[13px] text-muted">No runs yet. Pick a repository to start.</p>
      ) : (
        <ul className="flex flex-col">
          {recents.map((run) => (
            <li key={run.id} className="flex items-center gap-2 overflow-hidden whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13.5px]">
              <span aria-hidden className={`size-1.5 flex-none rounded-full ${DOT[run.status]}`} />
              <span className="overflow-hidden text-ellipsis">{run.label}</span>
              <span className="sr-only">({run.status})</span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex-1" />
      <div className="flex flex-col gap-0.5 rounded-lg border border-line px-2.5 py-2 text-[12.5px] text-muted">
        <b className="font-semibold text-ink">Add to CI</b>Run on every pull request
      </div>
      <div className="mt-2 flex items-center gap-2 border-t border-line px-1.5 pt-2.5 text-[13.5px]">
        <span aria-hidden className="grid size-6 place-items-center rounded-full bg-hover text-[11px] font-semibold">
          {userName.slice(0, 1).toUpperCase()}
        </span>
        <span>{userName}</span>
        <span className="text-faint">
          · <span className="num">{coins.toFixed(2)}</span> coins used
        </span>
      </div>
    </aside>
  );
}
