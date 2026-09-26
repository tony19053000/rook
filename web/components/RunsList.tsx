// The runs list (04 §3.2, `/runs`): newest first, each with its status (a dot plus a word, never colour
// alone), the headline, the repo and when it started. Also used by /counterexamples (only runs with a result).

import Link from "next/link";
import { ErrorCard } from "./ErrorCard";
import type { RunSummary } from "@/lib/api";
import { errorView, formatWhen, recentStatus, runHref, runStatusText } from "@/lib/pages";
import { clean } from "@/lib/safeText";

const DOT = {
  running: "bg-accent animate-pulse-dot",
  ok: "bg-good",
  broken: "bg-bad",
  idle: "bg-faint",
} as const;

export interface RunsListProps {
  runs: readonly RunSummary[];
  loading: boolean;
  error: unknown;
  onRetry?: () => void;
  now?: number;
  /** The empty-state line. */
  empty?: string;
}

export function RunsList({ runs, loading, error, onRetry, now, empty = "No runs yet. Pick a repository to start." }: RunsListProps) {
  if (loading && runs.length === 0) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true" data-skeleton="runs">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-xl border border-line bg-surface" />
        ))}
      </div>
    );
  }
  if (error !== null && error !== undefined && runs.length === 0) return <ErrorCard view={errorView(error, "runs")} onRetry={onRetry} />;
  if (runs.length === 0) {
    return (
      <p className="text-muted" data-empty>
        {empty}{" "}
        <Link href="/" className="text-link underline-offset-2 hover:underline">
          New run
        </Link>
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-2" data-runs>
      {runs.map((run) => {
        const dot = recentStatus(run);
        return (
          <li key={run.id}>
            <Link href={runHref(run.id)} className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-hover">
              <span aria-hidden data-dot={dot} className={`size-2 flex-none rounded-full ${DOT[dot]}`} />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="overflow-hidden text-ellipsis whitespace-nowrap font-medium">{clean(run.headline || run.repo.name)}</span>
                <span className="text-[12.5px] text-muted">
                  {clean(run.repo.name)} · {runStatusText(run)}
                </span>
              </span>
              <span className="num flex-none text-[12.5px] text-faint">{formatWhen(run.created_at, now)}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
