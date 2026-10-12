import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { AGENTS, APP_ROW_BG, agentTextColors } from "./agents";
import { MIN_TEXT_CONTRAST, contrastRatio } from "./contrast";

// ROOK-052 (04 §3.7): text in the app is at least 4.5:1 in both themes. The values are read from app/globals.css:
// the dark tokens (`:root, .app-dark`) and both light blocks (the OS preference and [data-theme="light"]).

const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

function tokens(block: string | undefined): Record<string, string> {
  return Object.fromEntries([...(block ?? "").matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1]!, m[2]!.toLowerCase()]));
}

const dark = tokens(css.match(/:root,\s*\.app-dark\s*\{([\s\S]*?)\}/)?.[1]);
const lightByMedia = tokens(css.match(/:root:not\(\[data-theme="dark"\]\)\s*\{([\s\S]*?)\}/)?.[1]);
const lightByAttribute = tokens(css.match(/:root\[data-theme="light"\]\s*\{([\s\S]*?)\}/)?.[1]);

const THEMES: [string, Record<string, string>][] = [
  ["dark", dark],
  ["light (prefers-color-scheme)", { ...dark, ...lightByMedia }],
  ['light ([data-theme="light"])', { ...dark, ...lightByAttribute }],
];

/** Every text colour → the backgrounds it is drawn on in the app (page, cards, pills, sidebar, hover rows). */
const PAIRS: [string, string[]][] = [
  ["ink", ["app", "surface", "sunk", "side", "hover", "good-soft", "bad-soft", "warn-soft"]],
  ["muted", ["app", "surface", "sunk", "side", "hover"]],
  // The known gap: section labels, counters, timestamps, the "recorded" tag, placeholders.
  ["faint", ["app", "surface", "sunk", "side", "hover"]],
  ["good", ["app", "surface", "sunk", "side", "good-soft"]],
  ["bad", ["app", "surface", "sunk", "side", "bad-soft"]],
  ["warn", ["app", "surface", "warn-soft"]],
  ["link", ["app", "surface", "sunk"]],
  // Accent-coloured text (FixCard's root cause, the picker's tick) is drawn with --accent-text.
  ["accent-text", ["app", "surface"]],
  // The known gap: a primary button's label on --accent.
  ["accent-ink", ["accent"]],
  // The outcome card's round mark (--app text on a status colour) and the current shrink chip (--page on --bad).
  ["app", ["ink", "good", "bad", "warn"]],
  ["page", ["bad"]],
];

describe.each(THEMES)("app token contrast, %s theme", (_name, theme) => {
  const v = (name: string) => {
    const value = theme[`--${name}`];
    if (!value) throw new Error(`--${name} is not declared`);
    return value;
  };

  it.each(PAIRS)("--%s text reaches 4.5:1 on each of its backgrounds", (text, backgrounds) => {
    for (const bg of backgrounds) {
      expect(contrastRatio(v(text), v(bg)), `--${text} on --${bg}`).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
    }
  });
});

describe("the two light blocks and the agent colours", () => {
  it("both light blocks declare the same values", () => {
    expect(Object.keys(lightByMedia).length).toBeGreaterThanOrEqual(19);
    expect(lightByAttribute).toEqual(lightByMedia);
  });

  it("accent text uses --accent-text, and the mark keeps the brand colour", () => {
    expect(css).toMatch(/\.text-accent:not\(svg\)\s*\{\s*color:\s*var\(--accent-text\);/);
    expect(dark["--accent"]).toBe("#e0563f");
  });

  it("agent rows sit on --app, and the theme picks the row's colour for it", () => {
    expect(APP_ROW_BG.dark).toBe(dark["--app"]);
    expect(APP_ROW_BG.light).toBe(lightByMedia["--app"]);
    expect(css).toMatch(/\.agent-row\s*\{\s*--agent-text:\s*var\(--agent-on-dark\);/);
    expect(css.match(/\.agent-row:not\(\.app-dark \*\)\s*\{\s*--agent-text:\s*var\(--agent-on-light\);/g)).toHaveLength(2);
  });

  it.each(Object.entries(AGENTS))("agent %s: its name colour reaches 4.5:1 in both themes", (_id, info) => {
    const text = agentTextColors(info.color);
    expect(contrastRatio(text.dark, APP_ROW_BG.dark)).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
    expect(contrastRatio(text.light, APP_ROW_BG.light)).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
  });

  it("an agent colour that already reads is kept as it is", () => {
    expect(agentTextColors(AGENTS.coordinator.color).dark.toLowerCase()).toBe(AGENTS.coordinator.color.toLowerCase());
  });
});
