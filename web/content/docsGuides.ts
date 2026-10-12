// The docs guides, in reading order (06 §1, ROOK-055): one list for the docs navigation, the index on /docs, the
// previous/next links, the footer and the sitemap.

import { counterexamplesGuide } from "./docsCounterexamples";
import { dataGuide } from "./docsData";
import { gettingStartedGuide } from "./docsGettingStarted";
import { githubActionGuide } from "./docsGithubAction";
import { installGuide } from "./docsInstall";
import type { DocGuide } from "./docsModel";
import { rulesGuide } from "./docsRules";
import type { NavLink } from "./site";

export const DOCS_PATH = "/docs";

export const guides: DocGuide[] = [gettingStartedGuide, installGuide, rulesGuide, counterexamplesGuide, githubActionGuide, dataGuide];

export const guidesCopy = {
  eyebrow: "Docs",
  /** The docs navigation on every guide. */
  navLabel: "Docs",
  overview: "Overview",
  tocLabel: "On this page",
  pagerLabel: "Previous and next guide",
  previous: "Previous",
  next: "Next",
  /** Above the verbatim rook.yaml on /docs/rules. */
  repoFileNote: "Unchanged from the Roook repo",
} as const;

/** The docs navigation: the overview, then every guide. */
export const docsNav: NavLink[] = [{ label: guidesCopy.overview, href: DOCS_PATH }, ...guides.map((g) => ({ label: g.navLabel, href: g.path }))];

/** The guides before and after `path` in reading order (the overview comes before the first). */
export function guideNeighbours(path: string): { previous: NavLink | null; next: NavLink | null } {
  const i = docsNav.findIndex((link) => link.href === path);
  return { previous: docsNav[i - 1] ?? null, next: i === -1 ? null : (docsNav[i + 1] ?? null) };
}
