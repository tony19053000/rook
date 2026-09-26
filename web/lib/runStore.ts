// The run reducer: events (02 §9) -> UI state, the same logic the TUI uses (02 §13, 04 §4).
// Pure and idempotent over `seq`: an event whose seq was already applied (a replayed tail after a
// reconnect) returns the same state object.

import type {
  EventDataMap,
  EventOf,
  Phase,
  ProposedRule,
  QuestionKind,
  QuestionOption,
  RepoSummary,
  RookEvent,
  RuleVerdict,
  RunStatus,
  VerifyCheck,
  VerifyStatus,
  Worker,
} from "./events";

type Data<T extends keyof EventDataMap> = EventDataMap[T];

// ---------------------------------------------------------------------------
// Transcript items (the chat column, in arrival order)
// ---------------------------------------------------------------------------

export interface AgentItem {
  kind: "agent";
  key: string;
  agent: string;
  callId: string;
  status: "working" | "done" | "failed";
  detail: string;
  summary: string | null;
  cost: number | null;
  recorded: boolean;
  startedAt: string;
  finishedAt: string | null;
}

export interface EngineItem {
  kind: "engine";
  key: string;
  worker: Worker;
  status: "working" | "done" | "failed";
  label: string;
  /** 0-100, as the engine sends it. */
  pct: number;
  count: number | null;
  summary: string | null;
}

export interface QuestionItem {
  kind: "question";
  key: string;
  questionId: string;
  questionKind: QuestionKind;
  text: string;
  options: QuestionOption[];
  payload: unknown;
  answered: boolean;
  answer: unknown;
  answeredBy: "user" | "auto" | null;
}

export interface ChatItem {
  kind: "chat";
  key: string;
  role: "user" | "guide";
  text: string;
}

export interface LogItem {
  kind: "log";
  key: string;
  level: "info" | "warn" | "error";
  text: string;
}

export interface RulesItem {
  kind: "rules";
  key: string;
  rules: ProposedRule[];
  /** Every verdict per rule id, in arrival order (engine first, then the critic). */
  verdicts: Record<string, RuleVerdict[]>;
  approvedIds: string[] | null;
}

export interface SearchItem {
  kind: "search";
  key: string;
  sequences: number;
  perSec: number;
  rules: Record<string, "holding" | "broken">;
}

export interface CounterexampleItem {
  kind: "counterexample";
  key: string;
  violationId: string | null;
  ruleId: string;
  /** The shrink chips: the first length, then each new length (`12 → 8 → 5 → 3`). */
  stepCounts: number[];
  observed: unknown;
  saved: Data<"counterexample.saved"> | null;
}

export interface FixItem {
  kind: "fix";
  key: string;
  cxId: string;
  diagnosis: Data<"diagnosis.ready"> | null;
  fix: Data<"fix.ready"> | null;
}

export interface VerifyItem {
  kind: "verify";
  key: string;
  cxId: string;
  checks: Partial<Record<VerifyCheck, { status: VerifyStatus; detail: string }>>;
  /** search.progress during VERIFY belongs to the fresh-search check, not to the SearchCard. */
  freshSearch: { sequences: number; perSec: number } | null;
  done: { verified: boolean; summary: string } | null;
  committed: Data<"fix.committed"> | null;
  pr: Data<"pr.opened"> | null;
}

export type TranscriptItem =
  | AgentItem
  | EngineItem
  | QuestionItem
  | ChatItem
  | LogItem
  | RulesItem
  | SearchItem
  | CounterexampleItem
  | FixItem
  | VerifyItem;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface RunState {
  runId: string | null;
  lastSeq: number;
  created: Data<"run.created"> | null;
  phase: Phase | null;
  phases: Phase[];
  status: "idle" | "running" | RunStatus;
  summary: string | null;
  coins: number;
  repoSummary: RepoSummary | null;
  sandbox: Data<"sandbox.ready"> | null;
  model: Data<"model.actions"> | null;
  approvedRuleIds: string[];
  pr: Data<"pr.opened"> | null;
  items: TranscriptItem[];
  /** key -> index in `items`. */
  index: Record<string, number>;
  /** Lookups from event ids to item keys. */
  refs: {
    openEngine: Partial<Record<Worker, string>>;
    openRules: string | null;
    search: string | null;
    violations: Record<string, string>;
    cx: Record<string, string>;
    fix: Record<string, string>;
    verify: Record<string, string>;
  };
}

export const initialRunState: RunState = {
  runId: null,
  lastSeq: 0,
  created: null,
  phase: null,
  phases: [],
  status: "idle",
  summary: null,
  coins: 0,
  repoSummary: null,
  sandbox: null,
  model: null,
  approvedRuleIds: [],
  pr: null,
  items: [],
  index: {},
  refs: { openEngine: {}, openRules: null, search: null, violations: {}, cx: {}, fix: {}, verify: {} },
};

// ---------------------------------------------------------------------------
// Helpers (they mutate the fresh copy made in `reduceRun`, never the input state)
// ---------------------------------------------------------------------------

function push(state: RunState, item: TranscriptItem): void {
  state.index = { ...state.index, [item.key]: state.items.length };
  state.items = [...state.items, item];
}

function get<K extends TranscriptItem["kind"]>(
  state: RunState,
  key: string | null | undefined,
  kind: K,
): Extract<TranscriptItem, { kind: K }> | null {
  if (key == null) return null;
  const i = state.index[key];
  const item = i === undefined ? undefined : state.items[i];
  return item !== undefined && item.kind === kind ? (item as Extract<TranscriptItem, { kind: K }>) : null;
}

function update<K extends TranscriptItem["kind"]>(
  state: RunState,
  key: string,
  kind: K,
  patch: (item: Extract<TranscriptItem, { kind: K }>) => Partial<Extract<TranscriptItem, { kind: K }>>,
): void {
  const item = get(state, key, kind);
  if (item === null) return;
  const items = [...state.items];
  items[state.index[key]!] = { ...item, ...patch(item) };
  state.items = items;
}

function agentItem(event: EventOf<"agent.started" | "agent.progress" | "agent.finished">): AgentItem {
  return {
    kind: "agent",
    key: `agent:${event.data.call_id}`,
    agent: event.data.agent,
    callId: event.data.call_id,
    status: "working",
    detail: "",
    summary: null,
    cost: null,
    recorded: false,
    startedAt: event.ts,
    finishedAt: null,
  };
}

/** The agent row for this call, created if the stream started mid-call. */
function ensureAgent(state: RunState, event: EventOf<"agent.started" | "agent.progress" | "agent.finished">): string {
  const key = `agent:${event.data.call_id}`;
  if (get(state, key, "agent") === null) push(state, agentItem(event));
  return key;
}

/** The open engine row for a worker, created if needed (a new row per engine.started). */
function ensureEngine(state: RunState, worker: Worker, seq: number, label: string): string {
  const open = state.refs.openEngine[worker];
  if (open !== undefined && get(state, open, "engine")?.status === "working") return open;
  const key = `engine:${seq}`;
  push(state, { kind: "engine", key, worker, status: "working", label, pct: 0, count: null, summary: null });
  state.refs = { ...state.refs, openEngine: { ...state.refs.openEngine, [worker]: key } };
  return key;
}

function ensureRules(state: RunState, seq: number): string {
  const open = state.refs.openRules;
  if (open !== null && get(state, open, "rules") !== null) return open;
  const key = `rules:${seq}`;
  push(state, { kind: "rules", key, rules: [], verdicts: {}, approvedIds: null });
  state.refs = { ...state.refs, openRules: key };
  return key;
}

function ensureFix(state: RunState, cxId: string): string {
  const existing = state.refs.fix[cxId];
  if (existing !== undefined) return existing;
  const key = `fix:${cxId}`;
  push(state, { kind: "fix", key, cxId, diagnosis: null, fix: null });
  state.refs = { ...state.refs, fix: { ...state.refs.fix, [cxId]: key } };
  return key;
}

function ensureVerify(state: RunState, cxId: string): string {
  const existing = state.refs.verify[cxId];
  if (existing !== undefined) return existing;
  // A retry after a failed verification gets a fresh card.
  const key = `verify:${cxId}:${state.lastSeq}`;
  push(state, { kind: "verify", key, cxId, checks: {}, freshSearch: null, done: null, committed: null, pr: null });
  state.refs = { ...state.refs, verify: { ...state.refs.verify, [cxId]: key } };
  return key;
}

/** The counterexample card a saved cx belongs to: by cx id, else the newest unsaved card of its rule. */
function cxCardFor(state: RunState, cxId: string, ruleId: string): string | null {
  const byId = state.refs.cx[cxId];
  if (byId !== undefined) return byId;
  for (let i = state.items.length - 1; i >= 0; i--) {
    const item = state.items[i]!;
    if (item.kind === "counterexample" && item.saved === null && item.ruleId === ruleId) return item.key;
  }
  return null;
}

function latestVerifyKey(state: RunState): string | null {
  for (let i = state.items.length - 1; i >= 0; i--) {
    const item = state.items[i]!;
    if (item.kind === "verify") return item.key;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export function reduceRun(prev: RunState, event: RookEvent): RunState {
  if (prev.runId !== null && event.run_id !== prev.runId) return prev;
  if (event.seq <= prev.lastSeq) return prev;
  const state: RunState = { ...prev, runId: event.run_id, lastSeq: event.seq };
  if (state.status === "idle") state.status = "running";
  const key = `e:${event.seq}`;

  switch (event.type) {
    case "run.created":
      state.created = event.data;
      break;
    case "run.phase":
      state.phase = event.data.phase;
      state.phases = [...state.phases, event.data.phase];
      if (event.data.phase === "SEARCH") state.refs = { ...state.refs, search: null };
      if (event.data.phase === "VERIFY") state.refs = { ...state.refs, verify: {} };
      break;

    case "agent.started": {
      const k = ensureAgent(state, event);
      update(state, k, "agent", () => ({ detail: event.data.detail }));
      break;
    }
    case "agent.progress": {
      const k = ensureAgent(state, event);
      update(state, k, "agent", () => ({ detail: event.data.detail }));
      break;
    }
    case "agent.finished": {
      const k = ensureAgent(state, event);
      update(state, k, "agent", () => ({
        status: event.data.ok ? "done" : "failed",
        summary: event.data.summary,
        cost: event.data.cost,
        recorded: event.data.recorded,
        finishedAt: event.ts,
      }));
      break;
    }

    case "engine.started": {
      // A new start always opens a new row, even if the worker's previous row never finished.
      state.refs = { ...state.refs, openEngine: { ...state.refs.openEngine, [event.data.worker]: undefined } };
      ensureEngine(state, event.data.worker, event.seq, event.data.label);
      break;
    }
    case "engine.progress": {
      const k = ensureEngine(state, event.data.worker, event.seq, event.data.label);
      update(state, k, "engine", (item) => ({
        pct: event.data.pct,
        label: event.data.label,
        count: event.data.count ?? item.count,
      }));
      break;
    }
    case "engine.finished": {
      const k = ensureEngine(state, event.data.worker, event.seq, "");
      update(state, k, "engine", () => ({
        status: event.data.ok ? "done" : "failed",
        pct: 100,
        summary: event.data.summary,
      }));
      break;
    }

    case "question.asked":
      if (get(state, `q:${event.data.question_id}`, "question") !== null) break;
      push(state, {
        kind: "question",
        key: `q:${event.data.question_id}`,
        questionId: event.data.question_id,
        questionKind: event.data.kind,
        text: event.data.text,
        options: event.data.options,
        payload: event.data.payload ?? null,
        answered: false,
        answer: null,
        answeredBy: null,
      });
      break;
    case "question.answered":
      update(state, `q:${event.data.question_id}`, "question", () => ({
        answered: true,
        answer: event.data.answer,
        answeredBy: event.data.by,
      }));
      break;

    case "repo.summary":
      state.repoSummary = event.data;
      break;
    case "sandbox.ready":
      state.sandbox = event.data;
      break;
    case "model.actions":
      state.model = event.data;
      break;

    case "rules.proposed": {
      const k = ensureRules(state, event.seq);
      update(state, k, "rules", () => ({ rules: event.data.rules }));
      break;
    }
    case "rules.reviewed": {
      const k = ensureRules(state, event.seq);
      update(state, k, "rules", (item) => {
        const verdicts = { ...item.verdicts };
        for (const v of event.data.verdicts) verdicts[v.rule_id] = [...(verdicts[v.rule_id] ?? []), v];
        return { verdicts };
      });
      break;
    }
    case "rules.approved": {
      state.approvedRuleIds = event.data.rule_ids;
      const k = ensureRules(state, event.seq);
      update(state, k, "rules", () => ({ approvedIds: event.data.rule_ids }));
      // Any later proposal starts a new card.
      state.refs = { ...state.refs, openRules: null };
      break;
    }

    case "search.progress": {
      const { sequences, per_sec, rules } = event.data;
      if (state.phase === "VERIFY") {
        const vk = latestVerifyKey(state);
        if (vk !== null) update(state, vk, "verify", () => ({ freshSearch: { sequences, perSec: per_sec } }));
        break;
      }
      let sk = state.refs.search;
      if (sk === null || get(state, sk, "search") === null) {
        sk = `search:${event.seq}`;
        push(state, { kind: "search", key: sk, sequences: 0, perSec: 0, rules: {} });
        state.refs = { ...state.refs, search: sk };
      }
      update(state, sk, "search", () => ({ sequences, perSec: per_sec, rules }));
      break;
    }

    case "violation.found": {
      const k = `cx:${event.data.violation_id}`;
      if (get(state, k, "counterexample") !== null) break;
      push(state, {
        kind: "counterexample",
        key: k,
        violationId: event.data.violation_id,
        ruleId: event.data.rule_id,
        stepCounts: [event.data.steps_count],
        observed: event.data.observed,
        saved: null,
      });
      state.refs = { ...state.refs, violations: { ...state.refs.violations, [event.data.violation_id]: k } };
      break;
    }
    case "shrink.step": {
      const k = state.refs.violations[event.data.violation_id];
      if (k === undefined) break;
      update(state, k, "counterexample", (item) =>
        item.stepCounts[item.stepCounts.length - 1] === event.data.steps_count
          ? {}
          : { stepCounts: [...item.stepCounts, event.data.steps_count] },
      );
      break;
    }
    case "counterexample.saved": {
      // Published again with its test_path once the regression test exists: same card.
      let k = cxCardFor(state, event.data.cx_id, event.data.rule_id);
      if (k === null) {
        k = `cx:${event.data.cx_id}`;
        push(state, {
          kind: "counterexample",
          key: k,
          violationId: null,
          ruleId: event.data.rule_id,
          stepCounts: [event.data.steps.length],
          observed: event.data.observed,
          saved: null,
        });
      }
      update(state, k, "counterexample", (item) => {
        const last = item.stepCounts[item.stepCounts.length - 1];
        const steps = event.data.steps.length;
        return {
          saved: event.data,
          observed: event.data.observed,
          stepCounts: last === steps ? item.stepCounts : [...item.stepCounts, steps],
        };
      });
      state.refs = { ...state.refs, cx: { ...state.refs.cx, [event.data.cx_id]: k } };
      break;
    }

    case "diagnosis.ready": {
      const k = ensureFix(state, event.data.cx_id);
      update(state, k, "fix", () => ({ diagnosis: event.data, fix: null }));
      break;
    }
    case "fix.ready": {
      const k = ensureFix(state, event.data.cx_id);
      update(state, k, "fix", () => ({ fix: event.data }));
      break;
    }

    case "verify.step": {
      const k = ensureVerify(state, event.data.cx_id);
      update(state, k, "verify", (item) => ({
        checks: { ...item.checks, [event.data.check]: { status: event.data.status, detail: event.data.detail } },
      }));
      break;
    }
    case "verify.done": {
      const k = ensureVerify(state, event.data.cx_id);
      update(state, k, "verify", () => ({ done: { verified: event.data.verified, summary: event.data.summary } }));
      break;
    }
    case "fix.committed": {
      const k = ensureVerify(state, event.data.cx_id);
      update(state, k, "verify", () => ({ committed: event.data }));
      break;
    }
    case "pr.opened": {
      state.pr = event.data;
      const k = latestVerifyKey(state);
      if (k !== null) update(state, k, "verify", () => ({ pr: event.data }));
      break;
    }

    case "chat.message":
      push(state, { kind: "chat", key, role: event.data.role, text: event.data.text });
      break;
    case "cost.update":
      state.coins = event.data.coins_total;
      break;
    case "log":
      push(state, { kind: "log", key, level: event.data.level, text: event.data.text });
      break;
    case "run.finished":
      state.status = event.data.status;
      state.summary = event.data.summary;
      break;
  }
  return state;
}

/** Fold a list of events (e.g. a stored log) into a state. */
export function reduceEvents(events: readonly RookEvent[], from: RunState = initialRunState): RunState {
  return events.reduce(reduceRun, from);
}

// ---------------------------------------------------------------------------
// Selectors
// ---------------------------------------------------------------------------

export function pendingQuestions(state: RunState): QuestionItem[] {
  return state.items.filter((i): i is QuestionItem => i.kind === "question" && !i.answered);
}

export function workingAgents(state: RunState): AgentItem[] {
  return state.items.filter((i): i is AgentItem => i.kind === "agent" && i.status === "working");
}

export function brokenRules(state: RunState): string[] {
  const search = get(state, state.refs.search, "search");
  if (search === null) return [];
  return Object.entries(search.rules)
    .filter(([, status]) => status === "broken")
    .map(([id]) => id);
}
