// @vitest-environment jsdom
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { cleanup, render } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SiteHeader } from "./SiteHeader";
import { AUTH_STORAGE_KEY, hasStoredSession } from "@/lib/authStorage";

// 06 §5: "Open workspace" for a browser that remembers a sign-in, read from localStorage without auth-js.

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

const SESSION = JSON.stringify({ access_token: "a.b.c", refresh_token: "r-1", expires_at: 1, user: { id: "u" } });

function header() {
  const { container } = render(<SiteHeader />);
  const banner = container.querySelector("header") as HTMLElement;
  const group = (name: string) => banner.querySelector(`[data-account="${name}"]`) as HTMLElement;
  const mobile = banner.querySelector("details nav") as HTMLElement;
  return { banner, signedOut: group("signed-out"), signedIn: group("signed-in"), mobile };
}

function expectSignedOut() {
  const { signedOut, signedIn, mobile } = header();
  expect(signedOut.hasAttribute("inert")).toBe(false);
  expect(signedOut.className).not.toContain("invisible");
  expect(signedOut.querySelector('a[href="/login"]')?.textContent).toBe("Sign in");
  expect(signedIn.hasAttribute("inert")).toBe(true);
  expect(signedIn.className).toContain("invisible");
  expect(mobile.querySelector('a[href="/login"]')?.textContent).toBe("Sign in");
}

describe("hasStoredSession", () => {
  const store = (value: string | null) => ({ getItem: (k: string) => (k === AUTH_STORAGE_KEY ? value : null) });

  it("is true only for a parsable session with a non-empty refresh token", () => {
    expect(hasStoredSession(store(SESSION))).toBe(true);
    expect(hasStoredSession(store(null))).toBe(false);
    expect(hasStoredSession(store(""))).toBe(false);
    expect(hasStoredSession(store("{not json"))).toBe(false);
    expect(hasStoredSession(store("null"))).toBe(false);
    expect(hasStoredSession(store('"r-1"'))).toBe(false);
    expect(hasStoredSession(store(JSON.stringify({ refresh_token: "" })))).toBe(false);
    expect(hasStoredSession(store(JSON.stringify({ refresh_token: 42 })))).toBe(false);
    expect(hasStoredSession(null)).toBe(false);
  });

  it("never throws when storage does", () => {
    expect(hasStoredSession({ getItem: () => { throw new Error("SecurityError"); } })).toBe(false);
  });
});

describe("the header's Open workspace hint", () => {
  it("a stored session: Open workspace → /app, desktop and mobile; the signed-out CTAs are hidden", () => {
    localStorage.setItem(AUTH_STORAGE_KEY, SESSION);
    const { signedOut, signedIn, mobile } = header();
    const link = signedIn.querySelector("a") as HTMLAnchorElement;
    expect(link.textContent).toBe("Open workspace");
    expect(link.getAttribute("href")).toBe("/app");
    expect(signedIn.hasAttribute("inert")).toBe(false);
    expect(signedIn.className).not.toContain("invisible");
    expect(signedOut.hasAttribute("inert")).toBe(true);
    expect(signedOut.className).toContain("invisible");
    expect(mobile.querySelector('a[href="/app"]')?.textContent).toBe("Open workspace");
    expect(mobile.querySelector('a[href="/login"]')).toBeNull();
  });

  it("no stored session: the signed-out CTAs", () => {
    expectSignedOut();
  });

  it("malformed JSON or an empty refresh token: the signed-out CTAs", () => {
    localStorage.setItem(AUTH_STORAGE_KEY, "{oops");
    expectSignedOut();
    cleanup();
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ refresh_token: "" }));
    expectSignedOut();
  });

  it("storage that throws (blocked, private mode): the signed-out CTAs", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    expectSignedOut();
  });

  it("a localStorage getter that throws: the signed-out CTAs", () => {
    const original = Object.getOwnPropertyDescriptor(window, "localStorage")!;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("SecurityError");
      },
    });
    try {
      expectSignedOut();
    } finally {
      Object.defineProperty(window, "localStorage", original);
    }
  });

  it("the server render is always the signed-out CTAs (no hint before hydration)", () => {
    localStorage.setItem(AUTH_STORAGE_KEY, SESSION);
    const html = renderToString(<SiteHeader />);
    expect(html).toMatch(/data-account="signed-in"[^>]*inert=""/);
    expect(html).toMatch(/<a [^>]*href="\/login"[^>]*>Sign in<\/a>/);
    expect(html).not.toMatch(/<details[\s\S]*href="\/app"[^>]*>Open workspace/);
  });

  it("the hint's import graph reaches neither auth-js nor lib/session.ts", () => {
    const root = process.cwd();
    const seen = new Set<string>();
    const queue = [resolve(root, "components/site/AccountHint.tsx")];
    const bare: string[] = [];
    while (queue.length > 0) {
      const file = queue.pop()!;
      if (seen.has(file)) continue;
      seen.add(file);
      const source = readFileSync(file, "utf8");
      for (const [, fromSpec, dynamicSpec, bareSpec] of source.matchAll(/(?:import|export)[^"']*?from\s*["']([^"']+)["']|import\s*\(\s*["']([^"']+)["']\s*\)|import\s+["']([^"']+)["']/g)) {
        const spec = fromSpec ?? dynamicSpec ?? bareSpec;
        if (spec === undefined) continue;
        const base = spec.startsWith("@/") ? resolve(root, spec.slice(2)) : spec.startsWith(".") ? resolve(dirname(file), spec) : null;
        if (base === null) {
          bare.push(spec);
          continue;
        }
        const target = [".ts", ".tsx", "/index.ts", "/index.tsx"].map((ext) => base + ext).find(existsSync);
        if (target) queue.push(target);
      }
    }
    const files = [...seen].map((f) => f.slice(root.length + 1));
    expect(files).toContain("lib/authStorage.ts");
    expect(files).not.toContain("lib/session.ts");
    expect(bare.filter((s) => s.startsWith("@supabase"))).toEqual([]);
    expect(new Set(bare)).toEqual(new Set(["next/link", "react"]));
  });
});
