// Text helpers for the inline cards, the web twin of the helpers in src/rook/cli/tui/widgets/cards.py.
// Every string that comes from an event goes through clean()/cleanMultiline() here, so the cards only ever
// render plain, control-free React text.

import { clean, cleanMultiline } from "./safeText";

export const MAX_VALUE_CHARS = 200;
export const MAX_SOURCE_CHARS = 80;
export const MAX_STEPS = 30;
export const MAX_DIFF_LINES = 200;

export const CHECK_NAMES: Record<string, string> = {
  replay: "Replay",
  project_tests: "Project tests",
  regression_test: "Regression test",
  fresh_search: "Fresh search",
};

/** One cleaned line, cut to `limit` characters with an ellipsis. */
export function short(text: unknown, limit: number): string {
  const line = clean(String(text ?? ""));
  const chars = Array.from(line);
  return chars.length <= limit ? line : chars.slice(0, Math.max(limit - 1, 0)).join("") + "…";
}

/** A value as one short line: strings as-is, everything else as compact JSON. */
export function compact(value: unknown, limit = MAX_VALUE_CHARS): string {
  if (typeof value === "string") return short(value, limit);
  let dumped: string;
  try {
    dumped = JSON.stringify(value) ?? String(value);
  } catch {
    dumped = String(value);
  }
  return short(dumped, limit);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `alice: refund(order=1, amount=60)`; parallel steps are joined with ` | `. */
export function stepText(step: unknown): string {
  if (isRecord(step)) {
    const parallel = step.parallel;
    if (Array.isArray(parallel)) return "at the same time: " + parallel.map(stepText).join(" | ");
    const action = clean(String(step.action ?? "?"));
    const params = step.params;
    const args = isRecord(params)
      ? Object.entries(params)
          .map(([k, v]) => `${clean(k)}=${compact(v, 40)}`)
          .join(", ")
      : "";
    const call = `${action}(${args})`;
    return step.actor ? `${clean(String(step.actor))}: ${call}` : call;
  }
  return compact(step);
}

export type Scalar = string | number | boolean | null;

/** A flat observed dict as `[key, value]` pairs (for the value boxes), or null when it isn't flat. */
export function observedPairs(observed: unknown, limit = 6): Array<[string, string]> | null {
  if (!isRecord(observed)) return null;
  const entries = Object.entries(observed);
  if (entries.length === 0) return null;
  const flat = entries.every(([, v]) => v === null || ["string", "number", "boolean"].includes(typeof v));
  if (!flat) return null;
  return entries.slice(0, limit).map(([k, v]) => [short(k, 40), compact(v as Scalar, 40)]);
}

/** A flat dict reads `paid 100 · refunded 110`; anything else is compact JSON. */
export function observedText(observed: unknown): string {
  const pairs = observedPairs(observed, Infinity);
  if (pairs !== null) return short(pairs.map(([k, v]) => `${k} ${v}`).join(" · "), MAX_VALUE_CHARS);
  return compact(observed);
}

export function cxTitle(cxId: string): string {
  const id = clean(cxId);
  const number = /^cx_?(\d+)$/.exec(id);
  return number ? `Counterexample #${number[1]}` : `Counterexample ${short(id, 40)}`;
}

export type DiffLineKind = "add" | "remove" | "meta" | "hunk" | "context";

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

/** A unified diff split into classified, cleaned lines; long diffs keep the first `limit` lines. */
export function diffLines(diff: string, limit = MAX_DIFF_LINES): { lines: DiffLine[]; more: number } {
  const all = cleanMultiline(String(diff ?? "")).replace(/\n+$/, "").split("\n");
  if (all.length === 1 && all[0] === "") return { lines: [], more: 0 };
  const lines = all.slice(0, limit).map((text): DiffLine => {
    if (/^(\+\+\+|---|diff |index )/.test(text)) return { kind: "meta", text };
    if (text.startsWith("+")) return { kind: "add", text };
    if (text.startsWith("-")) return { kind: "remove", text };
    if (text.startsWith("@@")) return { kind: "hunk", text };
    return { kind: "context", text };
  });
  return { lines, more: Math.max(0, all.length - limit) };
}

export function checkName(check: string): string {
  const name = CHECK_NAMES[check];
  if (name !== undefined) return name;
  const plain = clean(check).replace(/_/g, " ");
  return plain.charAt(0).toUpperCase() + plain.slice(1);
}

/**
 * The PR URL as a link target, only when it is an https://github.com/ URL with no credentials or odd port.
 * Anything else (javascript:, http:, another host) returns null and is shown as plain text.
 */
export function safeGithubUrl(url: unknown): string | null {
  if (typeof url !== "string") return null;
  const raw = url.trim();
  if (raw !== clean(raw) || !raw.startsWith("https://github.com/")) return null;
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" || parsed.hostname !== "github.com" || parsed.port !== "") return null;
  if (parsed.username !== "" || parsed.password !== "") return null;
  return parsed.href;
}
