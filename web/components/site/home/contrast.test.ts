import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { FRAME_ROW_BG, FRAME_TOKEN_OVERRIDES } from "./frameTheme";
import { AGENTS } from "@/lib/agents";
import { MIN_TEXT_CONTRAST, contrastRatio, readableColor } from "@/lib/contrast";

// 06 §3: text in the walkthrough frames is at least 4.5:1. The values come from their sources: the dark app
// tokens declared for `.app-dark` in app/globals.css, the `.wt-frame` overrides in ./frameTheme.ts, and the
// agent colours in lib/agents.ts through the same derivation AgentRow uses (readableColor).

const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

function darkAppTokens(): Record<string, string> {
  const block = css.match(/:root,\s*\.app-dark\s*\{([\s\S]*?)\}/)?.[1] ?? "";
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [m[1]!, m[2]!]));
}

const app = darkAppTokens();
const frame: Record<string, string> = { ...app, ...FRAME_TOKEN_OVERRIDES };
const v = (name: string) => {
  const value = frame[`--${name}`];
  if (!value) throw new Error(`--${name} is not declared`);
  return value;
};

/** Every text colour → the backgrounds it is drawn on inside the frames (rows, cards, pills, diff, title bar). */
const PAIRS: [string, string[]][] = [
  ["ink", ["app", "surface", "sunk", "side", "good-soft"]],
  ["muted", ["app", "surface", "sunk", "side"]],
  ["faint", ["app", "surface", "sunk", "side", "bad-soft", "good-soft"]],
  ["good", ["app", "surface", "sunk", "good-soft"]],
  ["bad", ["app", "surface", "sunk", "bad-soft"]],
  ["warn", ["surface", "warn-soft"]],
  ["link", ["sunk"]],
  // Accent text (FixCard's root cause) is drawn with --frame-accent-text (globals.css `.wt-frame .text-accent`).
  ["frame-accent-text", ["app", "surface"]],
  // Accent as a background: a primary button's label (cards/ui.tsx) on --accent.
  ["accent-ink", ["accent"]],
  // The current shrink chip: --page text on a --bad chip (globals.css `.wt-frame [data-shrink] [data-current]`).
  ["page", ["bad"]],
];

describe("walkthrough frame contrast (06 §3)", () => {
  it("reads the dark app tokens from globals.css", () => {
    expect(Object.keys(app).length).toBeGreaterThanOrEqual(19);
    expect(FRAME_ROW_BG).toBe(app["--app"]);
  });

  it.each(PAIRS)("--%s text reaches 4.5:1 on each of its backgrounds", (text, backgrounds) => {
    for (const bg of backgrounds) {
      expect(contrastRatio(v(text), v(bg)), `--${text} on --${bg}`).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
    }
  });

  it("the shrink-chip fixes are in globals.css", () => {
    expect(css).toMatch(/\.wt-frame \[data-shrink\] \[data-current\]\s*\{\s*color:\s*var\(--page\);/);
    expect(css).toMatch(/\.wt-frame \[data-shrink\] \.opacity-40\s*\{\s*opacity:\s*1;\s*color:\s*var\(--faint\);/);
  });

  it.each(Object.entries(AGENTS))("agent %s: its derived text colour reaches 4.5:1 on the row background", (_id, info) => {
    expect(contrastRatio(readableColor(info.color, FRAME_ROW_BG), FRAME_ROW_BG)).toBeGreaterThanOrEqual(MIN_TEXT_CONTRAST);
  });

  it("accent text in a frame uses the lifted colour, and --accent itself is never overridden", () => {
    expect(css).toMatch(/\.wt-frame \.text-accent\s*\{\s*color:\s*var\(--frame-accent-text\);/);
    expect(Object.keys(FRAME_TOKEN_OVERRIDES)).not.toContain("--accent");
  });

  it("leaves the app's own token values alone", () => {
    expect(app["--faint"]).toBe("#9d9c96"); // raised for the app pages in ROOK-052 (lib/appContrast.test.ts)
    expect(app["--accent"]).toBe("#e0563f");
  });
});

describe("contrast helpers", () => {
  it("compute the WCAG ratio", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#777777")).toBe(1);
  });

  it("readableColor keeps a colour that already reads and lifts one that doesn't", () => {
    expect(readableColor("#ffffff", "#262624")).toBe("#ffffff");
    const lifted = readableColor("#9B1FE8", "#262624");
    expect(lifted).not.toBe("#9B1FE8");
    expect(contrastRatio(lifted, "#262624")).toBeGreaterThanOrEqual(4.5);
  });
});
