// Display names, colors, verbs and sprite shapes of the agents (04 §1.3, CONTRACT).

import type { AgentId, Worker } from "./events";
import { clean } from "./safeText";
import type { Look, Shape } from "./sprite";

export interface AgentInfo extends Look {
  name: string;
  verb: string;
}

const EYE_WHITE = "#FFFFFF";

function agent(name: string, shape: Shape, color: string, verb: string): AgentInfo {
  return { name, shape, color, eye: EYE_WHITE, verb };
}

export const AGENTS: Record<AgentId, AgentInfo> = {
  coordinator: agent("Coordinator", "circle", "#F5B400", "Planning"),
  scout: agent("Scout", "roundsq", "#10B99A", "Scouting"),
  mechanic: agent("Mechanic", "cloud", "#FF8A00", "Building"),
  mapper: agent("Mapper", "blob", "#1FA8E0", "Mapping"),
  lawmaker: agent("Lawmaker", "tilted", "#9B1FE8", "Drafting rules"),
  rule_critic: agent("Rule Critic", "triangle", "#FF1493", "Reviewing rules"),
  test_designer: agent("Test Designer", "blob", "#FF5A1F", "Designing tests"),
  strategist: agent("Strategist", "circle", "#A86B3C", "Strategizing"),
  detective: agent("Detective", "roundsq", "#4F63FF", "Investigating"),
  diag_reviewer: agent("Diagnosis Reviewer", "triangle", "#F05FAA", "Checking evidence"),
  surgeon: agent("Surgeon", "tilted", "#22B868", "Operating"),
  fix_reviewer: agent("Fix Reviewer", "triangle", "#D6247A", "Reviewing fix"),
  guide: agent("Guide", "small", "#8E99A6", "Answering"),
};

export const BRAND_COLOR = "#E0563F";

/** The brand mascot: a cloud in the brand color, no name or verb. */
export const MASCOT: AgentInfo = agent("Rook", "cloud", BRAND_COLOR, "");

function titleCase(id: string): string {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Info for an agent id from an event; an unknown id still gets a readable row (a neutral circle). */
export function agentInfo(id: string): AgentInfo {
  const known = (AGENTS as Record<string, AgentInfo | undefined>)[id];
  return known ?? agent(titleCase(clean(id)) || "Agent", "circle", "#8E99A6", "Working");
}

export const WORKER_NAMES: Record<Worker, string> = {
  runner: "Runner",
  judge: "Judge",
  shrinker: "Shrinker",
  replayer: "Replayer",
  testrunner: "Test Runner",
  verifier: "Verifier",
};

/** The display name of an engine worker; an unknown worker id is cleaned and title-cased. */
export function workerName(worker: string): string {
  return (WORKER_NAMES as Record<string, string | undefined>)[worker] ?? (titleCase(clean(worker)) || "Engine");
}
