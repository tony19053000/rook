// Display names, colors and verbs of the agents (04 §1.3, CONTRACT). The sprite shapes come with
// AgentSprite (ROOK-034).

import type { AgentId, Worker } from "./events";

export interface AgentInfo {
  name: string;
  color: string;
  verb: string;
}

export const AGENTS: Record<AgentId, AgentInfo> = {
  coordinator: { name: "Coordinator", color: "#F5B400", verb: "Planning" },
  scout: { name: "Scout", color: "#10B99A", verb: "Scouting" },
  mechanic: { name: "Mechanic", color: "#FF8A00", verb: "Building" },
  mapper: { name: "Mapper", color: "#1FA8E0", verb: "Mapping" },
  lawmaker: { name: "Lawmaker", color: "#9B1FE8", verb: "Drafting rules" },
  rule_critic: { name: "Rule Critic", color: "#FF1493", verb: "Reviewing rules" },
  test_designer: { name: "Test Designer", color: "#FF5A1F", verb: "Designing tests" },
  strategist: { name: "Strategist", color: "#A86B3C", verb: "Strategizing" },
  detective: { name: "Detective", color: "#4F63FF", verb: "Investigating" },
  diag_reviewer: { name: "Diagnosis Reviewer", color: "#F05FAA", verb: "Checking evidence" },
  surgeon: { name: "Surgeon", color: "#22B868", verb: "Operating" },
  fix_reviewer: { name: "Fix Reviewer", color: "#D6247A", verb: "Reviewing fix" },
  guide: { name: "Guide", color: "#8E99A6", verb: "Answering" },
};

export const BRAND_COLOR = "#E0563F";

/** Info for an agent id from an event; an unknown id still gets a readable row. */
export function agentInfo(id: string): AgentInfo {
  return (AGENTS as Record<string, AgentInfo | undefined>)[id] ?? { name: id, color: "#8E99A6", verb: "Working" };
}

export const WORKER_NAMES: Record<Worker, string> = {
  runner: "Runner",
  judge: "Judge",
  shrinker: "Shrinker",
  replayer: "Replayer",
  testrunner: "Test Runner",
  verifier: "Verifier",
};
