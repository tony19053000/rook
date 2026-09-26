// Event stream types. They mirror docs/02_ARCHITECTURE.md §9 (CONTRACT) and src/rook/core/events.py.
// Change them only together with that doc.

export const PHASES = [
  "PREPARE", "SCOUT", "START_APP", "MAP", "RULES", "APPROVE", "DESIGN", "SEARCH", "SHRINK", "REPLAY",
  "SAVE", "DIAGNOSE", "APPROVE_FIX", "FIX", "VERIFY", "APPROVE_PR", "SHIP", "DONE",
] as const;
export type Phase = (typeof PHASES)[number];

export const WORKERS = ["runner", "judge", "shrinker", "replayer", "testrunner", "verifier"] as const;
export type Worker = (typeof WORKERS)[number];

/** Agent ids use underscores (02 §9, 04 §1.3). The Bob mode slug is "rook-" + the id with hyphens. */
export const AGENT_IDS = [
  "coordinator", "scout", "mechanic", "mapper", "lawmaker", "rule_critic", "test_designer", "strategist",
  "detective", "diag_reviewer", "surgeon", "fix_reviewer", "guide",
] as const;
export type AgentId = (typeof AGENT_IDS)[number];

export type QuestionKind = "approve_rules" | "fix" | "pr" | "setup_value" | "menu" | "repo";
export type VerifyCheck = "replay" | "project_tests" | "regression_test" | "fresh_search";
export type VerifyStatus = "running" | "passed" | "failed";
export type RuleVerdictKind = "approve" | "reject" | "revise";
export type RunStatus = "done" | "failed" | "cancelled";

export interface RepoRef {
  kind: string;
  ref: string;
  name: string;
}

export interface QuestionOption {
  id: string;
  label: string;
}

/** 02 §9 lists `rules[]` without fixing the item shape; these are the fields the engine sends today. */
export interface ProposedRule {
  id: string;
  text: string;
  [field: string]: unknown;
}

export interface RuleVerdict {
  rule_id: string;
  verdict: RuleVerdictKind;
  reason: string;
  by: "engine" | "critic";
  revised?: unknown;
  already_broken?: boolean;
}

export interface RepoSummary {
  language: string;
  framework: string;
  entrypoints: string[];
  routes_files: string[];
  models_files: string[];
  test_command: string | null;
  run_hints?: unknown;
  business_summary: string;
}

/** `data` per event type (02 §9). */
export interface EventDataMap {
  "run.created": { repo: RepoRef; request: string; options: { auto: boolean; budget: number } };
  "run.phase": { phase: Phase };
  "agent.started": { agent: string; call_id: string; detail: string };
  "agent.progress": { agent: string; call_id: string; detail: string };
  "agent.finished": { agent: string; call_id: string; ok: boolean; summary: string; cost: number; recorded: boolean };
  "engine.started": { worker: Worker; label: string };
  "engine.progress": { worker: Worker; pct: number; label: string; count?: number | null };
  "engine.finished": { worker: Worker; ok: boolean; summary: string };
  "question.asked": { question_id: string; kind: QuestionKind; text: string; options: QuestionOption[]; payload?: unknown };
  "question.answered": { question_id: string; answer: unknown; by: "user" | "auto" };
  "repo.summary": RepoSummary;
  "sandbox.ready": { base_url_redacted: string; mode: string };
  "model.actions": { actors: unknown[]; actions: unknown[]; state: unknown[] };
  "rules.proposed": { rules: ProposedRule[] };
  "rules.reviewed": { verdicts: RuleVerdict[] };
  "rules.approved": { rule_ids: string[] };
  "search.progress": { sequences: number; per_sec: number; rules: Record<string, "holding" | "broken"> };
  "violation.found": { violation_id: string; rule_id: string; steps_count: number; observed: unknown };
  "shrink.step": { violation_id: string; steps_count: number };
  "counterexample.saved": {
    cx_id: string;
    rule_id: string;
    rule_text: string;
    steps: unknown[];
    observed: unknown;
    expected: unknown;
    reproduced: string;
    flaky: boolean;
    test_path: string | null;
  };
  "diagnosis.ready": { cx_id: string; file: string; line: number | null; explanation: string; reviewed: boolean };
  "fix.ready": { cx_id: string; files: string[]; diff: string; reviewed: boolean };
  "verify.step": { cx_id: string; check: VerifyCheck; status: VerifyStatus; detail: string };
  "verify.done": { cx_id: string; verified: boolean; summary: string };
  "fix.committed": { cx_id: string; branch: string; commit: string; files: string[] };
  "pr.opened": { url: string; number: number; branch: string };
  "chat.message": { role: "user" | "guide"; text: string };
  "cost.update": { coins_total: number };
  log: { level: "info" | "warn" | "error"; text: string };
  "run.finished": { status: RunStatus; summary: string };
}

export type EventType = keyof EventDataMap;

export const EVENT_TYPES: readonly EventType[] = [
  "run.created", "run.phase", "agent.started", "agent.progress", "agent.finished", "engine.started",
  "engine.progress", "engine.finished", "question.asked", "question.answered", "repo.summary",
  "sandbox.ready", "model.actions", "rules.proposed", "rules.reviewed", "rules.approved",
  "search.progress", "violation.found", "shrink.step", "counterexample.saved", "diagnosis.ready",
  "fix.ready", "verify.step", "verify.done", "fix.committed", "pr.opened", "chat.message", "cost.update", "log",
  "run.finished",
];

/** The envelope: `{v, seq, ts, run_id, type, data}`. A discriminated union on `type`. */
export type RookEvent = {
  [T in EventType]: { v: 1; seq: number; ts: string; run_id: string; type: T; data: EventDataMap[T] };
}[EventType];

export type EventOf<T extends EventType> = Extract<RookEvent, { type: T }>;

const KNOWN_TYPES = new Set<string>(EVENT_TYPES);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Check the envelope of a parsed JSON value. Returns the event, or null if it isn't a v1 envelope of a
 * known type. `data` is trusted to match its type (the server validates it with pydantic before sending).
 */
export function parseEvent(value: unknown): RookEvent | null {
  if (!isRecord(value)) return null;
  const { v, seq, ts, run_id, type, data } = value;
  if (v !== 1) return null;
  if (typeof seq !== "number" || !Number.isInteger(seq) || seq < 1) return null;
  if (typeof ts !== "string" || typeof run_id !== "string") return null;
  if (typeof type !== "string" || !KNOWN_TYPES.has(type)) return null;
  if (!isRecord(data)) return null;
  return value as unknown as RookEvent;
}

/** Parse one `data:` payload of the SSE stream. Invalid JSON or a bad envelope gives null. */
export function parseEventJson(text: string): RookEvent | null {
  try {
    return parseEvent(JSON.parse(text));
  } catch {
    return null;
  }
}
