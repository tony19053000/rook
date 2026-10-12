// Display names, colors, verbs and sprite shapes of the agents (04 §1.3, CONTRACT).

import { MIN_TEXT_CONTRAST, readableColor } from "./contrast";
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

/** The background agent rows sit on in the app (`--app` in app/globals.css), per theme. */
export const APP_ROW_BG = { dark: "#262624", light: "#faf9f5" } as const;

/**
 * An agent's name colour as text in the app, one per theme, each at least 4.5:1 on that theme's `--app`: the
 * agent's own colour where it already reads, else the nearest lighter (dark theme) or darker (light theme) mix.
 * The sprite and the dot keep the true colour.
 */
export function agentTextColors(color: string): { dark: string; light: string } {
  return {
    dark: readableColor(color, APP_ROW_BG.dark),
    light: readableColor(color, APP_ROW_BG.light, MIN_TEXT_CONTRAST, "#000000"),
  };
}

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
