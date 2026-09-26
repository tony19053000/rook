"use client";

// One Bob agent call in the chat column (04 §1.3). Working: `[sprite] Name  Verb… (3.2s)` / `⎿ detail`.
// On agent.finished it collapses to `● Name ✓ summary` (✗ if the call failed or its verdict is a rejection).
// Only engine rows carry verdicts about the app; this ✓/✗ is just how the agent call went.

import { useState } from "react";
import { AgentSprite } from "./AgentSprite";
import { agentInfo } from "@/lib/agents";
import { useFrame, useReducedMotion } from "@/lib/motion";
import type { AgentItem } from "@/lib/runStore";
import { clean } from "@/lib/safeText";
import { newSeed, shimmerLevels, type ShimmerLevel } from "@/lib/sprite";

export interface AgentRowProps {
  item: AgentItem;
  /** Overrides for tests and the dev gallery. */
  reducedMotion?: boolean;
  frame?: number;
  seed?: number;
  /** Clock in ms; `startedAt` is when this row first appeared (the server ts may be skewed or replayed). */
  now?: number;
  startedAt?: number;
}

/** Whether a finished call counts as a success: ok and not a rejection verdict (the TUI rule). */
export function agentSucceeded(item: Pick<AgentItem, "status" | "summary">): boolean {
  return item.status === "done" && !(item.summary ?? "").trim().toLowerCase().startsWith("reject");
}

export function Mark({ ok }: { ok: boolean }) {
  return (
    <span className={ok ? "text-good" : "text-bad"}>
      {ok ? "✓" : "✗"}
      <span className="sr-only">{ok ? " done" : " failed"}</span>
    </span>
  );
}

const SHIMMER_STYLE: Record<ShimmerLevel, (color: string) => { color: string; fontWeight?: number }> = {
  peak: (color) => ({ color, fontWeight: 600 }),
  near: (color) => ({ color }),
  base: () => ({ color: "var(--muted)" }),
};

function Verb({ text, color, frame, reduced }: { text: string; color: string; frame: number; reduced: boolean }) {
  if (reduced) return <span style={{ color }}>{text}</span>;
  const chars = Array.from(text);
  const levels = shimmerLevels(chars.length, frame);
  return (
    <span aria-label={text}>
      {chars.map((ch, i) => (
        <span key={i} aria-hidden style={SHIMMER_STYLE[levels[i]!](color)}>
          {ch}
        </span>
      ))}
    </span>
  );
}

export function AgentRow({ item, reducedMotion, frame, seed, now, startedAt }: AgentRowProps) {
  const info = agentInfo(item.agent);
  const mediaReduced = useReducedMotion();
  const reduced = reducedMotion ?? mediaReduced;
  const working = item.status === "working";
  // One ticker for the sprite, the shimmer and the timer. With reduced motion it still ticks (slowly) so the
  // elapsed time stays live, but the sprite and verb are static.
  const tick = useFrame(working && frame === undefined, reduced ? 2 : undefined);
  const [mountedAt] = useState(() => Date.now());
  const [ownSeed] = useState(newSeed);

  if (!working) {
    const ok = agentSucceeded(item);
    return (
      <div className="flex min-w-0 items-baseline gap-2" data-row="agent" data-status={item.status}>
        <span aria-hidden className="size-2 flex-none -translate-y-px rounded-full" style={{ background: info.color }} />
        <span className="min-w-0 truncate">
          <span className="font-semibold" style={{ color: info.color }}>
            {info.name}
          </span>{" "}
          <Mark ok={ok} /> {clean(item.summary ?? "")}
          {item.recorded && <span className="ml-2 rounded bg-sunk px-1.5 text-[11px] italic text-faint">recorded</span>}
        </span>
      </div>
    );
  }

  const f = reduced ? 0 : (frame ?? tick);
  const elapsed = Math.max(0, ((now ?? Date.now()) - (startedAt ?? mountedAt)) / 1000);
  return (
    <div className="flex min-w-0 items-center gap-2.5" data-row="agent" data-status="working">
      <AgentSprite look={info} px={3} frame={f} seed={seed ?? ownSeed} reducedMotion={reduced} />
      <div className="flex min-w-0 flex-col">
        <div className="truncate">
          <span className="font-semibold" style={{ color: info.color }}>
            {info.name}
          </span>{" "}
          <Verb text={`${info.verb}…`} color={info.color} frame={f} reduced={reduced} />{" "}
          <span className="num text-xs text-faint" suppressHydrationWarning>
            ({elapsed.toFixed(1)}s)
          </span>
        </div>
        <div className="truncate font-mono text-xs text-muted">⎿ {clean(item.detail)}</div>
      </div>
    </div>
  );
}
