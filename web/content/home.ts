// The home hero (06 §5.1). ROOK-044 adds the walkthrough and the sections below it.

import { site } from "./site";

export const homeHero = {
  eyebrow: site.builtOn.replace(/\.$/, ""),
  heading: "Find the smallest sequence that breaks your software, before your users do.",
  lead: site.oneLiner,
} as const;
