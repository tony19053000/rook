import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AgentRow, agentSucceeded } from "./AgentRow";
import { AgentSprite } from "./AgentSprite";
import { clampPct, EngineRow, progressLabel } from "./EngineRow";
import { SpriteGallery } from "./SpriteGallery";
import { AGENTS, MASCOT } from "@/lib/agents";
import { AGENT_IDS } from "@/lib/events";
import { minishopRun } from "@/lib/fixtures/minishop";
import { reduceEvents, type AgentItem, type EngineItem } from "@/lib/runStore";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);
const count = (s: string, needle: string) => s.split(needle).length - 1;
// React escapes & in style/text; compare against the escaped name.
const esc = (s: string) => s.replace(/&/g, "&amp;");

function agentItem(patch: Partial<AgentItem> = {}): AgentItem {
  return {
    kind: "agent",
    key: "agent:c1",
    agent: "detective",
    callId: "c1",
    status: "working",
    detail: "reading src/refunds.js",
    summary: null,
    cost: null,
    recorded: false,
    startedAt: "2026-09-26T08:00:00.000Z",
    finishedAt: null,
    ...patch,
  };
}

function engineItem(patch: Partial<EngineItem> = {}): EngineItem {
  return { kind: "engine", key: "e1", worker: "runner", status: "working", label: "1700 sequences", pct: 40, count: 1700, summary: null, ...patch };
}

describe("every agent renders (AC)", () => {
  it("the gallery story has a sprite, a working row and a finished row for every agent plus the mascot", () => {
    const out = html(<SpriteGallery reducedMotion={false} now={0} />);
    for (const id of AGENT_IDS) {
      const info = AGENTS[id];
      expect(out).toContain(`data-character="${id}"`);
      expect(count(out, `>${esc(info.name)}<`)).toBeGreaterThanOrEqual(3); // caption, working row, finished row
      expect(out).toContain(`aria-label="${info.verb}…"`);
    }
    expect(out).toContain('data-character="mascot"');
    // 13 agents + mascot in the sheet, 13 working rows.
    expect(count(out, "<canvas")).toBe(AGENT_IDS.length + 1 + AGENT_IDS.length);
    expect(count(out, 'data-row="agent" data-status="working"')).toBe(AGENT_IDS.length);
    expect(count(out, 'data-row="engine"')).toBe(3);
  });

  it("each character sprite carries its contract shape", () => {
    for (const id of AGENT_IDS) {
      expect(html(<AgentSprite look={AGENTS[id]} reducedMotion />)).toContain(`data-agent-sprite="${AGENTS[id].shape}"`);
    }
    expect(html(<AgentSprite look={MASCOT} animate={false} />)).toContain('data-agent-sprite="cloud"');
  });

  it("the recorded minishop run renders every agent call as a collapsed row", () => {
    const state = reduceEvents(minishopRun);
    const agents = state.items.filter((i): i is AgentItem => i.kind === "agent");
    const engines = state.items.filter((i): i is EngineItem => i.kind === "engine");
    expect(agents.length).toBe(12);
    expect(agents.some((a) => a.status === "failed")).toBe(true); // the rule critic's missing recording
    for (const item of agents) {
      const out = html(<AgentRow item={item} reducedMotion />);
      expect(out).toMatch(item.status === "done" ? /data-status="done".*✓/ : /data-status="failed".*✗/);
      expect(out).toContain(`>${esc(AGENTS[item.agent as keyof typeof AGENTS].name)}<`);
      expect(out).not.toContain("<canvas");
    }
    for (const item of engines) expect(html(<EngineRow item={item} reducedMotion />)).toContain('data-row="engine"');
  });
});

describe("the reduced-motion story is static (AC)", () => {
  it("the gallery has no animated sprite, shimmer, bounce or pulse", () => {
    const out = html(<SpriteGallery reducedMotion now={0} />);
    expect(out).not.toContain('data-motion="animated"');
    expect(out).not.toContain('data-pose="up"');
    expect(out).not.toContain('data-blink="1"');
    expect(out).not.toContain("translateY");
    expect(out).not.toContain("transition");
    expect(out).not.toContain("animate-pulse-dot");
    expect(out).toContain('data-pulse="off"');
    expect(out).not.toContain("font-weight:600"); // no shimmer peak
  });

  it("a working row renders the same at every frame with reduced motion", () => {
    const frames = Array.from({ length: 150 }, (_, f) => html(<AgentRow item={agentItem()} frame={f} seed={5} reducedMotion now={0} startedAt={0} />));
    expect(new Set(frames).size).toBe(1);
  });

  it("without reduced motion the same row does animate", () => {
    const frames = Array.from({ length: 150 }, (_, f) => html(<AgentRow item={agentItem()} frame={f} seed={5} reducedMotion={false} now={0} startedAt={0} />));
    expect(new Set(frames).size).toBeGreaterThan(10);
    expect(frames.some((f) => f.includes('data-pose="up"'))).toBe(true);
    expect(frames.join("")).toContain("font-weight:600");
  });

  it("the server render (no media query) is static", () => {
    expect(html(<AgentSprite look={AGENTS.scout} />)).toContain('data-motion="static"');
  });
});

describe("AgentRow lifecycle", () => {
  it("working: sprite, name, verb, elapsed time and ⎿ detail", () => {
    const out = html(<AgentRow item={agentItem()} reducedMotion now={3200} startedAt={0} />);
    expect(out).toContain("<canvas");
    expect(out).toContain(">Detective<");
    expect(out).toContain("Investigating…");
    expect(out).toContain("(3.2s)");
    expect(out).toContain("⎿ reading src/refunds.js");
  });

  it("collapses to ● Name ✓ summary with a recorded tag", () => {
    const out = html(<AgentRow item={agentItem({ status: "done", summary: "src/refunds.js:42 ignores earlier refunds", recorded: true })} reducedMotion />);
    expect(out).not.toContain("<canvas");
    expect(out).not.toContain("⎿");
    expect(out).toContain("✓");
    expect(out).toContain("src/refunds.js:42 ignores earlier refunds");
    expect(out).toContain(">recorded<");
  });

  it("shows ✗ for a failed call and for a rejection verdict", () => {
    expect(html(<AgentRow item={agentItem({ status: "failed", summary: "timed out" })} reducedMotion />)).toContain("✗");
    const rejected = agentItem({ status: "done", summary: "Rejected: a code check, not a business rule" });
    expect(agentSucceeded(rejected)).toBe(false);
    expect(html(<AgentRow item={rejected} reducedMotion />)).toContain("✗");
    expect(agentSucceeded(agentItem({ status: "done", summary: "ok" }))).toBe(true);
  });

  it("renders event text as text and strips control characters", () => {
    const evil = '<img src=x onerror=alert(1)>\x1b[31mred\x07\nnext';
    const working = html(<AgentRow item={agentItem({ detail: evil, agent: "<b>x</b>" })} reducedMotion now={0} startedAt={0} />);
    const done = html(<AgentRow item={agentItem({ status: "done", summary: evil })} reducedMotion />);
    for (const out of [working, done]) {
      expect(out).not.toContain("<img");
      expect(out).toContain("&lt;img src=x onerror=alert(1)&gt;[31mred next");
      expect(out).not.toMatch(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/);
    }
    expect(working).not.toContain("<b>x</b>");
  });
});

describe("EngineRow", () => {
  it("working: ■ name, a progress bar and a grouped count", () => {
    const out = html(<EngineRow item={engineItem()} reducedMotion={false} />);
    expect(out).toContain(">Runner<");
    expect(out).toContain('aria-valuenow="40"');
    expect(out).toContain("width:40%");
    expect(out).toContain("1,700 sequences");
    expect(out).toContain("animate-pulse-dot");
  });

  it("finished: ✓ or ✗ with the summary, no bar", () => {
    const ok = html(<EngineRow item={engineItem({ worker: "replayer", status: "done", summary: "10 / 10 reproduced" })} />);
    expect(ok).toContain("✓");
    expect(ok).toContain("10 / 10 reproduced");
    expect(ok).not.toContain("progressbar");
    const broken = html(<EngineRow item={engineItem({ status: "failed", summary: "Rule broken \x1b[0m· refunds ≤ paid" })} />);
    expect(broken).toContain("✗");
    expect(broken).toContain("Rule broken [0m· refunds ≤ paid");
  });

  it("progressLabel and clampPct", () => {
    expect(progressLabel("3412 sequences", 3412)).toBe("3,412 sequences");
    expect(progressLabel("34120 sequences", 3412)).toBe("34120 sequences");
    expect(progressLabel("seed 1", 1)).toBe("seed 1");
    expect(progressLabel("12 steps", null)).toBe("12 steps");
    expect([clampPct(-5), clampPct(150), clampPct(Number.NaN), clampPct(42.5)]).toEqual([0, 100, 0, 42.5]);
  });
});
