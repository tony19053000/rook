// ROOK-055: the one file of the Rook repo a site page shows whole (tests/fixtures/minishop/rook.yaml, on
// /docs/rules). Like the recorded run's lines (lib/recordedData.ts), it is exempt from the copy rules by identity
// only: an element marked with REPO_FILE_ATTR is skipped by the copy scan only when its whole text is exactly that
// file, so the mark cannot hide prose. The file names an actor "customer" and a seeded login at a ".local" test
// address, which the strict rules would otherwise flag.

import { MINISHOP_ROOK_YAML } from "./fixtures/minishopRookYaml";

/** Marks the element whose whole text is a repo file, unchanged. */
export const REPO_FILE_ATTR = "data-repo-file";

export const REPO_FILES: ReadonlySet<string> = new Set([MINISHOP_ROOK_YAML]);

/** True only for an element marked as a repo file whose whole text is exactly one of those files. */
export function isRepoFile(el: Element): boolean {
  return el.hasAttribute(REPO_FILE_ATTR) && REPO_FILES.has(el.textContent ?? "");
}
