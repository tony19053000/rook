// The shape of a docs guide (06 §5.10, ROOK-055): a long-form page of sections, each a list of blocks. The copy
// lives in content/docs*.ts and components/site/docs/GuideView.tsx renders it. In any text, a `code span` is
// written between backticks; a `rook …` command is always written that way (or in a code block), which is what
// tests/unit/test_docs_cli_commands.py reads to check every quoted command against the real CLI.

import type { NavLink } from "./site";

/** A page-specific part a guide page fills in (the verbatim rook.yaml, the recorded refund case). */
export type DocSlot = "rook-yaml" | "refund-story";

export type DocBlock =
  | { kind: "p"; text: string }
  | { kind: "list"; items: string[]; ordered?: boolean }
  | { kind: "code"; code: string; label?: string; prompt?: boolean }
  | { kind: "note"; title: string; text: string }
  | { kind: "terms"; items: { term: string; text: string }[] }
  | { kind: "links"; items: NavLink[] }
  /** A mailto: link to the contact address; the page builds the href (an encoded subject is not copy). */
  | { kind: "email"; label: string; subject: string }
  | { kind: "slot"; name: DocSlot };

export interface DocSubsection {
  /** The anchor (unique on the page). */
  id: string;
  title: string;
  blocks: DocBlock[];
}

export interface DocSection extends DocSubsection {
  subsections?: DocSubsection[];
}

export interface DocGuide {
  /** The route, e.g. "/docs/install". */
  path: string;
  /** The short name in the docs navigation and the footer. */
  navLabel: string;
  /** The page title and meta description. */
  title: string;
  description: string;
  heading: string;
  lead: string;
  /** One line for the index on /docs. */
  summary: string;
  sections: DocSection[];
}

/** A code sample from its lines. */
export const lines = (...parts: string[]): string => parts.join("\n");
