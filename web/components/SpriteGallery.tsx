"use client";

// The sprite + row story: every agent character, a working and a finished row for each, and engine rows in
// each state. `reducedMotion` forces the static variant (the reduced-motion story); undefined follows the
// media query. Used by /dev/sprites and the component tests.

import { AgentRow } from "./AgentRow";
import { AgentSprite } from "./AgentSprite";
import { EngineRow } from "./EngineRow";
import { AGENTS, MASCOT } from "@/lib/agents";
import type { AgentId } from "@/lib/events";
import type { AgentItem, EngineItem } from "@/lib/runStore";

const TS = "2026-09-26T08:00:00.000Z";

function agentItem(agent: string, status: AgentItem["status"], i: number): AgentItem {
  return {
    kind: "agent",
    key: `agent:story-${status}-${i}`,
    agent,
    callId: `story-${status}-${i}`,
    status,
    detail: "reading src/refunds.js",
    summary: status === "working" ? null : status === "done" ? "done in the story" : "the call failed",
    cost: status === "working" ? null : 0.023,
    recorded: i % 2 === 0,
    startedAt: TS,
    finishedAt: status === "working" ? null : TS,
  };
}

export const STORY_ENGINES: EngineItem[] = [
  { kind: "engine", key: "e1", worker: "runner", status: "working", label: "1700 sequences", pct: 42, count: 1700, summary: null },
  { kind: "engine", key: "e2", worker: "replayer", status: "done", label: "", pct: 100, count: null, summary: "10 / 10 reproduced, real bug" },
  { kind: "engine", key: "e3", worker: "judge", status: "failed", label: "", pct: 100, count: null, summary: "Rule broken · refunds ≤ paid · 3,412 sequences" },
];

export function SpriteGallery({ reducedMotion, now }: { reducedMotion?: boolean; now?: number }) {
  const ids = Object.keys(AGENTS) as AgentId[];
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Characters" className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-4">
        {[...ids.map((id) => [id, AGENTS[id]] as const), ["mascot", MASCOT] as const].map(([id, info], i) => (
          <figure key={id} className="flex flex-col items-center gap-1.5" data-character={id}>
            <AgentSprite look={info} px={5} seed={i * 17} reducedMotion={reducedMotion} label={info.name} />
            <figcaption className="text-[13px] font-semibold" style={{ color: info.color }}>
              {info.name}
            </figcaption>
          </figure>
        ))}
      </section>
      <section aria-label="Working rows" className="flex flex-col gap-2.5">
        {ids.map((id, i) => (
          <AgentRow key={id} item={agentItem(id, "working", i)} seed={i * 17} reducedMotion={reducedMotion} now={now} startedAt={now} />
        ))}
      </section>
      <section aria-label="Finished rows" className="flex flex-col gap-1.5">
        {ids.map((id, i) => (
          <AgentRow key={id} item={agentItem(id, i === 5 ? "failed" : "done", i)} reducedMotion={reducedMotion} />
        ))}
      </section>
      <section aria-label="Engine rows" className="flex flex-col gap-1.5">
        {STORY_ENGINES.map((item) => (
          <EngineRow key={item.key} item={item} reducedMotion={reducedMotion} />
        ))}
      </section>
    </div>
  );
}
