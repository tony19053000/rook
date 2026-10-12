// ROOK-054: the copy rules (lib/copyRules.ts) stay strict; the only text exempt from them is verbatim data of the
// recorded minishop run (lib/fixtures/minishop-run.json), matched by identity, never by pattern. A counterexample
// step reads "customer: refund(amount=1)" and two diff lines in a row read "... else 0" then "+ ...", which the
// social-proof and "1,000+" rules would otherwise flag. Used by the tests only (it loads the whole fixture).

import { stepText } from "./cardText";
import raw from "./fixtures/minishop-run.json";
import { isRepoFile, REPO_FILE_ATTR } from "./verbatim";

interface RawEvent {
  type: string;
  data: Record<string, unknown>;
}

/** Marks an element whose whole text is one step line or one diff line of a run. */
export const RUN_DATA_ATTR = "data-run-data";

const events = raw as RawEvent[];
const saved = events.filter((e) => e.type === "counterexample.saved").at(-1)?.data;
const steps = (Array.isArray(saved?.steps) ? saved.steps : []) as { actor: string; action: string }[];
const diff = String(events.find((e) => e.type === "fix.ready")?.data.diff ?? "");
const withoutHunk = diff
  .split("\n")
  .filter((line) => !line.startsWith("@@"))
  .join("\n");

/** What a page may show in a marked element: one step line or one diff line of the run, whole. */
export const RECORDED_LINES: ReadonlySet<string> = new Set([...steps.map(stepText), ...diff.split("\n").filter((line) => line.trim() !== "")]);

/**
 * What a content module (web/content/*.ts) may hold as a whole string value: those lines, the run's actor names
 * and its fix diff (with or without the @@ hunk header).
 */
export const RECORDED_STRINGS: ReadonlySet<string> = new Set([...RECORDED_LINES, ...steps.map((step) => step.actor), diff, withoutHunk]);

/** True only for an element marked as run data whose whole text is exactly one recorded line. */
export function isRecordedData(el: Element): boolean {
  return el.hasAttribute(RUN_DATA_ATTR) && RECORDED_LINES.has(el.textContent ?? "");
}

/**
 * The text a copy scan reads from a rendered page: every text node (and aria-label, alt and title), one per line,
 * except the text inside an element for which `isRecordedData` holds, or `isRepoFile` (lib/verbatim.ts: a whole
 * repo file shown unchanged). A marked element with any other text is read like the rest, so a mark cannot hide
 * prose.
 */
export function scannableText(root: Element): string {
  const attrs = [...root.querySelectorAll("[aria-label], [alt], [title]")].flatMap((el) =>
    ["aria-label", "alt", "title"].map((name) => el.getAttribute(name) ?? ""),
  );
  const walker = root.ownerDocument.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */);
  const texts: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    const marked = node.parentElement?.closest(`[${RUN_DATA_ATTR}]`);
    if (marked && isRecordedData(marked)) continue;
    const file = node.parentElement?.closest(`[${REPO_FILE_ATTR}]`);
    if (file && isRepoFile(file)) continue;
    texts.push(node.textContent ?? "");
  }
  return [...texts, ...attrs].join("\n");
}
