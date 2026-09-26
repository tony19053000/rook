// Question and answer logic for the web cards, the twin of src/rook/cli/tui/widgets/prompts.py and the
// RulesCard selection in cards.py. Pure functions, so the rules (never "all", never a pre-ticked
// already_broken rule, one answer per question) are unit-tested without a DOM.

import { ApiError, type ApiClient } from "./api";
import { compact, short } from "./cardText";
import type { ProposedRule, QuestionOption } from "./events";
import type { QuestionItem, RulesItem, TranscriptItem } from "./runStore";
import { clean } from "./safeText";

export const CHAT_MAX = 2000;
/** 04 §3.4: in guest demo mode an open question auto-answers "yes" after this many seconds. */
export const GUEST_AUTO_SECONDS = 6;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---------------------------------------------------------------------------
// Options and answers
// ---------------------------------------------------------------------------

export function cleanOptions(options: readonly QuestionOption[] | unknown): QuestionOption[] {
  if (!Array.isArray(options)) return [];
  const out: QuestionOption[] = [];
  for (const item of options) {
    if (isRecord(item) && item.id !== undefined && item.id !== null) {
      const id = clean(String(item.id));
      out.push({ id, label: short(item.label || id, 120) });
    }
  }
  return out;
}

/** How an answer reads once collapsed: the option label, `Approve r1, r2`, `NAME provided`… */
export function describeAnswer(answer: unknown, options: readonly QuestionOption[] = []): string {
  const labels = new Map(cleanOptions(options).map((o) => [o.id, o.label]));
  if (typeof answer === "boolean") return answer ? "Yes" : "No";
  if (typeof answer === "string") return short(labels.get(clean(answer)) ?? answer, 120);
  if (Array.isArray(answer)) {
    return answer.length ? short(`Approve ${answer.map((i) => clean(String(i))).join(", ")}`, 200) : "Reject all";
  }
  if (isRecord(answer) && "name" in answer) {
    const name = short(answer.name, 80);
    return answer.provided ? `${name} provided` : `${name} not provided`;
  }
  return compact(answer);
}

export type QuestionUi = "rules" | "confirm" | "menu" | "value";

export function payloadRules(question: Pick<QuestionItem, "payload">): unknown[] | null {
  const payload = question.payload;
  const rules = isRecord(payload) ? payload.rules : undefined;
  return Array.isArray(rules) && rules.length > 0 ? rules : null;
}

/**
 * Which prompt a question gets, as prompts.make_prompt, except that approve_rules is always the RulesCard
 * prompt: its "all" option is never offered, the approval is always an explicit id list.
 */
export function questionUi(question: Pick<QuestionItem, "questionKind" | "options" | "payload">): QuestionUi {
  const options = cleanOptions(question.options);
  if (question.questionKind === "approve_rules") return "rules";
  if ((question.questionKind === "fix" || question.questionKind === "pr") && options.length > 0 && options.length <= 2) {
    return "confirm";
  }
  if (options.length > 0) return "menu";
  return "value";
}

/** The yes/no pair of a confirm question: its first and second options, else yes/no. */
export function confirmChoices(question: Pick<QuestionItem, "options">): [QuestionOption, QuestionOption] {
  const options = cleanOptions(question.options);
  return [options[0] ?? { id: "yes", label: "Yes" }, options[1] ?? { id: "no", label: "No" }];
}

/** A setup value question: the variable name, and whether to mask it (always, unless `secret: false`). */
export function valueQuestion(question: Pick<QuestionItem, "payload">): { name: string; secret: boolean } {
  const payload = isRecord(question.payload) ? question.payload : {};
  return { name: short(payload.name ?? "", 80), secret: payload.secret !== false };
}

/**
 * The guest auto-answer ("yes" after the countdown), or null when this question must wait for a person:
 * a setup value (a secret is never made up) or a menu. approve_rules is auto-answered by the RulesCard with
 * its default selection (see `guestRulesAnswer`).
 */
export function guestAutoAnswer(question: Pick<QuestionItem, "questionKind" | "options" | "payload">): string | null {
  if (questionUi(question) !== "confirm") return null;
  return confirmChoices(question)[0].id;
}

// ---------------------------------------------------------------------------
// Rules approval
// ---------------------------------------------------------------------------

export type RuleStatus = "proposed" | "accepted" | "rejected";

export interface RuleRow {
  id: string;
  text: string;
  sources: string[];
  status: RuleStatus;
  reason: string;
  alreadyBroken: boolean;
  /** Set once the approval is known (rules.approved, or the question's answer). */
  approved: boolean | null;
}

function ruleFields(item: unknown, index: number): { id: string; text: string; sources: string[] } {
  if (isRecord(item)) {
    const id = clean(String(item.id || `rule_${index}`));
    const text = clean(String(item.text || item.check || id));
    const sources = Array.isArray(item.evidence) ? item.evidence.map((s) => short(s, 80)) : [];
    return { id, text, sources };
  }
  return { id: `rule_${index}`, text: clean(String(item)), sources: [] };
}

function approvedFrom(answer: unknown, rows: RuleRow[]): Set<string> {
  if (answer === "all") return new Set(rows.filter((r) => r.status === "accepted").map((r) => r.id));
  if (Array.isArray(answer)) return new Set(answer.map((i) => clean(String(i))));
  return new Set();
}

/**
 * The rows of a RulesCard: the proposed rules, then the engine/critic verdicts in order (the last decides;
 * `already_broken` sticks), then the approve_rules payload as the final word, then the approval.
 */
export function ruleRows(item: Pick<RulesItem, "rules" | "verdicts" | "approvedIds">, question: QuestionItem | null): RuleRow[] {
  const rows: RuleRow[] = [];
  const byId = new Map<string, RuleRow>();
  const add = (row: RuleRow) => {
    rows.push(row);
    byId.set(row.id, row);
  };
  (item.rules as ProposedRule[]).forEach((rule, i) => {
    const f = ruleFields(rule, i + 1);
    if (!byId.has(f.id)) add({ ...f, status: "proposed", reason: "", alreadyBroken: false, approved: null });
  });
  for (const [ruleId, verdicts] of Object.entries(item.verdicts)) {
    const row = byId.get(clean(ruleId));
    if (row === undefined) continue;
    for (const v of verdicts) {
      const by = clean(String(v.by ?? ""));
      const reason = clean(String(v.reason ?? ""));
      row.reason = by && reason ? `${by}: ${reason}` : reason;
      row.status = v.verdict === "reject" ? "rejected" : "accepted";
      if (v.verdict === "revise" && isRecord(v.revised) && v.revised.text) row.text = clean(String(v.revised.text));
      row.alreadyBroken = row.alreadyBroken || v.already_broken === true;
    }
  }
  const final = question !== null ? payloadRules(question) : null;
  final?.forEach((rule, i) => {
    if (!isRecord(rule)) return;
    const f = ruleFields(rule, i + 1);
    let row = byId.get(f.id);
    if (row === undefined) {
      row = { ...f, status: "proposed", reason: "", alreadyBroken: false, approved: null };
      add(row);
    }
    row.text = f.text;
    row.status = rule.accepted === true ? "accepted" : "rejected";
    row.reason = rule.reason ? clean(String(rule.reason)) : row.reason;
    row.alreadyBroken = rule.already_broken === true;
  });
  let approved: Set<string> | null = null;
  if (item.approvedIds !== null) approved = new Set(item.approvedIds.map((i) => clean(String(i))));
  else if (question?.answered) approved = approvedFrom(question.answer, rows);
  if (approved !== null) for (const row of rows) row.approved = row.status !== "rejected" && approved.has(row.id);
  return rows;
}

/** A rule the user may tick: accepted by the checks (a flagged one too, but only by an explicit tick). */
export function choosable(row: RuleRow): boolean {
  return row.status === "accepted";
}

/** The pre-selection: every accepted rule except one flagged `already_broken`. */
export function initialSelection(rows: readonly RuleRow[]): string[] {
  return rows.filter((r) => choosable(r) && !r.alreadyBroken).map((r) => r.id);
}

/** The approve_rules answer: always the explicit id list (in card order), never "all". */
export function rulesApproval(rows: readonly RuleRow[], selected: Iterable<string>): string[] {
  const picked = new Set(selected);
  return rows.filter((r) => choosable(r) && picked.has(r.id)).map((r) => r.id);
}

/**
 * The guest auto-answer for approve_rules: the default selection as an explicit list (so a flagged rule is
 * never auto-approved), or null when nothing would be approved (a person decides then).
 */
export function guestRulesAnswer(rows: readonly RuleRow[]): string[] | null {
  const ids = rulesApproval(rows, initialSelection(rows));
  return ids.length > 0 ? ids : null;
}

/** How a rules answer reads once collapsed. */
export function describeRulesAnswer(answer: unknown): string {
  if (Array.isArray(answer)) {
    if (answer.length === 0) return "Rejected all rules";
    return answer.length === 1 ? "Approved 1 rule" : `Approved ${answer.length} rules`;
  }
  if (answer === "all") return "Approved all accepted rules";
  if (answer === "none") return "Rejected all rules";
  return describeAnswer(answer);
}

// ---------------------------------------------------------------------------
// Which card holds which question
// ---------------------------------------------------------------------------

function cxIdOf(question: QuestionItem): string | null {
  const payload = question.payload;
  return isRecord(payload) && typeof payload.cx_id === "string" ? payload.cx_id : null;
}

/**
 * 04 §4: a question gets "buttons on the related card" when there is one: approve_rules (with rules) on the
 * latest RulesCard before it, fix on the FixCard of its cx, pr on the latest VerifyCard of its cx. Other
 * questions render as their own QuestionCard.
 */
export function attachQuestions(items: readonly TranscriptItem[]): {
  byCard: Map<string, QuestionItem>;
  attached: Set<string>;
} {
  const byCard = new Map<string, QuestionItem>();
  const attached = new Set<string>();
  items.forEach((item, index) => {
    if (item.kind !== "question") return;
    const cxId = cxIdOf(item);
    let target: TranscriptItem | undefined;
    for (let i = index - 1; i >= 0 && target === undefined; i--) {
      const prev = items[i]!;
      if (item.questionKind === "approve_rules" && prev.kind === "rules") target = prev;
      else if (item.questionKind === "fix" && prev.kind === "fix" && prev.cxId === cxId) target = prev;
      else if (item.questionKind === "pr" && prev.kind === "verify" && prev.cxId === cxId) target = prev;
    }
    // A later question of the same kind replaces the earlier one on the card (a retry asks again).
    const ui = questionUi(item);
    if (target !== undefined && (ui === "rules" || ui === "confirm")) {
      byCard.set(target.key, item);
      attached.add(item.key);
    }
  });
  return { byCard, attached };
}

// ---------------------------------------------------------------------------
// Sending (POST answers / chat), with every failure turned into a plain message
// ---------------------------------------------------------------------------

export type SendOutcome =
  | { status: "sent" }
  /** The question is closed for good (already answered, gone): don't offer a retry. */
  | { status: "closed"; message: string }
  /** Worth another try. */
  | { status: "error"; message: string };

export type SendKind = "answer" | "chat";

export function failureOutcome(error: unknown, kind: SendKind = "answer"): SendOutcome {
  if (!(error instanceof ApiError)) {
    return { status: "error", message: "Couldn't reach the server. Check your connection and try again." };
  }
  const what = kind === "answer" ? "answer" : "message";
  switch (error.status) {
    case 409:
      return kind === "answer"
        ? { status: "closed", message: "Already answered." }
        : { status: "closed", message: "The run isn't live any more, so the Guide can't answer." };
    case 404:
      return { status: "closed", message: "This run is no longer available." };
    case 400:
      return { status: "error", message: `The server didn't accept this ${what}.` };
    case 401:
      return { status: "error", message: "Your session expired. Sign in again." };
    case 403:
      return { status: "error", message: "You don't have access to this run." };
    case 413:
      return { status: "error", message: `That ${what} is too long.` };
    case 429:
      return { status: "error", message: "Too many requests. Wait a moment and try again." };
    case 501:
      return { status: "closed", message: "The server can't do this yet." };
    default:
      return { status: "error", message: `The server had a problem (HTTP ${error.status}). Try again.` };
  }
}

export async function sendAnswer(
  api: Pick<ApiClient, "answer">,
  runId: string,
  questionId: string,
  answer: unknown,
): Promise<SendOutcome> {
  try {
    const result = await api.answer(runId, questionId, answer);
    if (result.ok) return { status: "sent" };
    return { status: "closed", message: "This question is no longer open (already answered, or the run moved on)." };
  } catch (error) {
    return failureOutcome(error, "answer");
  }
}

/** The chat text to send (trimmed), or the reason it can't be sent. */
export function chatText(text: string): { text: string } | { error: string } {
  const value = text.trim();
  if (value === "") return { error: "Type a message first." };
  if (value.length > CHAT_MAX) return { error: `Messages are at most ${CHAT_MAX.toLocaleString("en-US")} characters.` };
  return { text: value };
}

export async function sendChat(api: Pick<ApiClient, "chat">, runId: string, text: string): Promise<SendOutcome> {
  const checked = chatText(text);
  if ("error" in checked) return { status: "error", message: checked.error };
  try {
    const result = await api.chat(runId, checked.text);
    if (result.ok) return { status: "sent" };
    return { status: "closed", message: "The run isn't live any more, so the Guide can't answer." };
  } catch (error) {
    return failureOutcome(error, "chat");
  }
}
