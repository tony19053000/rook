"use client";

// One deterministic engine worker (04 §1.3). Working: `■ Runner  ████░░░░ 1,700 sequences` with a pulsing
// square; finished: `■ Runner ✗ summary`. Engine rows are the only rows that state verdicts.

import { Mark } from "./AgentRow";
import { workerName } from "@/lib/agents";
import { useReducedMotion } from "@/lib/motion";
import type { EngineItem } from "@/lib/runStore";
import { clean } from "@/lib/safeText";

/** Group the leading count in thousands ("1700 sequences" -> "1,700 sequences"), as the TUI does. */
export function progressLabel(label: string, count: number | null): string {
  if (count === null || !Number.isFinite(count)) return label;
  const raw = String(count);
  if (!label.startsWith(raw) || /\w/.test(label.charAt(raw.length))) return label;
  return count.toLocaleString("en-US") + label.slice(raw.length);
}

export function clampPct(pct: number): number {
  return Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0;
}

export function EngineRow({ item, reducedMotion }: { item: EngineItem; reducedMotion?: boolean }) {
  const mediaReduced = useReducedMotion();
  const reduced = reducedMotion ?? mediaReduced;
  const name = workerName(item.worker);

  if (item.status !== "working") {
    return (
      <div className="flex min-w-0 items-center gap-2 font-mono text-[12.5px]" data-row="engine" data-status={item.status}>
        <span aria-hidden className="size-[9px] flex-none bg-ink" />
        <b className="flex-none whitespace-nowrap">{name}</b>
        <span className="min-w-0 truncate">
          <Mark ok={item.status === "done"} /> {clean(item.summary ?? "")}
        </span>
      </div>
    );
  }

  const pct = clampPct(item.pct);
  return (
    <div className="flex min-w-0 items-center gap-2 font-mono text-[12.5px]" data-row="engine" data-status="working">
      <span
        aria-hidden
        data-pulse={reduced ? "off" : "on"}
        className={`size-[9px] flex-none bg-ink ${reduced ? "" : "animate-pulse-dot"}`}
      />
      <b className="flex-none whitespace-nowrap">{name}</b>
      <span
        role="progressbar"
        aria-label={`${name} progress`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className="h-1.5 w-[120px] flex-none overflow-hidden rounded-full bg-line"
      >
        <span className="block h-full bg-good" style={{ width: `${pct}%` }} />
      </span>
      <span className="num min-w-0 truncate text-muted">{clean(progressLabel(item.label, item.count))}</span>
    </div>
  );
}
