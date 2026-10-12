// ROOK-054: the fonts are self-hosted from files in the repo's dependencies, so `next build` downloads nothing.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB = process.cwd();
const FONTS = resolve(WEB, "app", "fonts.ts");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "node_modules" || name.startsWith(".") ? [] : sourceFiles(full);
    return /\.(ts|tsx|mjs|css)$/.test(name) && !/\.test\./.test(name) ? [full] : [];
  });
}

describe("fonts (no network at build time)", () => {
  const source = readFileSync(FONTS, "utf8");
  const paths = [...source.matchAll(/path: "([^"]+)"/g)].map((m) => m[1]!);

  it("load every face from a local woff2 file that exists, with its OFL licence beside it", () => {
    expect(paths).toHaveLength(9); // Plex Sans 400-700, Plex Mono 400-600, Newsreader 400 and 500
    for (const path of paths) {
      const file = resolve(dirname(FONTS), path);
      expect(existsSync(file), file).toBe(true);
      expect(file.endsWith(".woff2")).toBe(true);
      expect(existsSync(resolve(dirname(file), "..", "LICENSE")), `licence of ${path}`).toBe(true);
    }
  });

  it("keep the same families and CSS variables, and nothing loads next/font/google", () => {
    for (const family of ["ibm-plex-sans", "ibm-plex-mono", "newsreader"]) expect(source).toContain(`@fontsource/${family}/`);
    for (const variable of ["--font-plex-sans", "--font-plex-mono", "--font-newsreader"]) expect(source).toContain(variable);
    for (const file of sourceFiles(WEB)) expect(readFileSync(file, "utf8"), file).not.toMatch(/next\/font\/google|fonts\.googleapis|fonts\.gstatic/);
  });
});
