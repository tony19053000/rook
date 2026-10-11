// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SiteLayout from "@/app/(site)/layout";
import HomePage from "@/app/(site)/page";
import PricingPage from "@/app/(site)/pricing/page";
import PrivacyPage from "@/app/(site)/privacy/page";
import TermsPage from "@/app/(site)/terms/page";
import NotFound from "@/app/not-found";
import { PricingView } from "./PricingView";
import { LEGAL_DRAFT_BANNER, legalPlaceholders } from "@/content/legal";
import { PRICING_PENDING_NOTICE, pricingStatus, type Plan } from "@/content/pricing";
import { notFoundCopy } from "@/content/site";
import { copyViolations } from "@/lib/copyRules";

afterEach(cleanup);

const inSite = (page: ReactElement) => render(<SiteLayout>{page}</SiteLayout>);

const PAGES: [string, () => ReturnType<typeof render>][] = [
  ["/", () => inSite(<HomePage />)],
  ["/pricing", () => inSite(<PricingPage />)],
  ["/privacy", () => inSite(<PrivacyPage />)],
  ["/terms", () => inSite(<TermsPage />)],
  ["404", () => render(<NotFound />)],
];

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, summary, [tabindex]:not([tabindex="-1"])';

/**
 * The visible text plus the text in attributes people and screen readers get (not class or style values).
 * Text nodes are joined with spaces: textContent glues neighbours ("found1customer") and hides words from \b.
 */
function pageText(root: HTMLElement): string {
  const attrs = [...root.querySelectorAll("[aria-label], [alt], [title]")].flatMap((el) =>
    ["aria-label", "alt", "title"].map((name) => el.getAttribute(name) ?? ""),
  );
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: string[] = [];
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) texts.push(node.textContent ?? "");
  return [...texts, ...attrs].join("\n");
}

function headingLevels(root: HTMLElement): number[] {
  return [...root.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((h) => Number(h.tagName[1]));
}

describe.each(PAGES)("site page %s (06 §9)", (path, renderPage) => {
  it("has the landmarks: banner, main#main, contentinfo and navigation", () => {
    renderPage();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("main").id).toBe("main");
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getAllByRole("navigation", { hidden: true }).length).toBeGreaterThanOrEqual(2);
  });

  it("has exactly one h1, first, and no skipped heading levels", () => {
    const { container } = renderPage();
    const levels = headingLevels(container);
    expect(levels.filter((l) => l === 1)).toHaveLength(1);
    expect(levels[0]).toBe(1);
    for (let i = 1; i < levels.length; i += 1) expect(levels[i]!, `heading ${i} on ${path}`).toBeLessThanOrEqual(levels[i - 1]! + 1);
  });

  it("starts with the skip link to #main", () => {
    const { container } = renderPage();
    const first = container.querySelector(FOCUSABLE);
    expect(first?.getAttribute("href")).toBe("#main");
    expect(container.querySelector("#main")).not.toBeNull();
  });

  it("renders no social proof, invented numbers or prices", () => {
    const { container } = renderPage();
    expect(copyViolations(pageText(container), { pricing: path === "/pricing" })).toEqual([]);
  });

  it("header: Sign in, Try the demo, the <details> menu; footer: the four columns", () => {
    renderPage();
    const header = screen.getByRole("banner");
    expect(within(header).getByRole("link", { name: "Try the demo" }).getAttribute("href")).toBe("/app");
    expect(header.querySelector('a[href="/login"]')).not.toBeNull();
    expect(header.querySelector("details > summary")).not.toBeNull();
    const footer = screen.getByRole("contentinfo");
    for (const name of ["Product", "Docs", "Company", "Legal"]) expect(within(footer).getByRole("heading", { name })).toBeTruthy();
  });
});

describe("pricing (06 §5.4)", () => {
  it("shows the launch notice while no plans are set", () => {
    inSite(<PricingPage />);
    expect(screen.getByText(PRICING_PENDING_NOTICE)).toBeTruthy();
    expect(pricingStatus([])).toEqual({ kind: "pending", notice: "Pricing will be published at launch" });
  });

  it("derives the status from plans: with a plan the notice goes", () => {
    const plan: Plan = { name: "Team", price: "$1", summary: "s", features: ["f"] };
    expect(pricingStatus([plan]).kind).toBe("published");
    render(<PricingView plans={[plan]} />);
    expect(screen.queryByText(PRICING_PENDING_NOTICE)).toBeNull();
    expect(screen.getByRole("heading", { name: "Team" })).toBeTruthy();
  });

  it("the page reads the plans export (a plan there replaces the notice)", async () => {
    vi.resetModules();
    vi.doMock("@/content/pricing", async (original) => ({
      ...(await original<typeof import("@/content/pricing")>()),
      plans: [{ name: "Team", price: "$1", summary: "s", features: [] }],
    }));
    try {
      const { default: MockedPricingPage } = await import("@/app/(site)/pricing/page");
      render(<MockedPricingPage />);
      expect(screen.queryByText(PRICING_PENDING_NOTICE)).toBeNull();
    } finally {
      vi.doUnmock("@/content/pricing");
      vi.resetModules();
    }
  });
});

describe.each([
  ["/privacy", () => inSite(<PrivacyPage />)],
  ["/terms", () => inSite(<TermsPage />)],
])("legal draft %s (06 §5.5)", (_path, renderPage) => {
  it("shows the draft banner and the three placeholders", () => {
    const { container } = renderPage();
    expect(screen.getByText(LEGAL_DRAFT_BANNER)).toBeTruthy();
    expect(LEGAL_DRAFT_BANNER).toBe("Draft — pending legal review, not yet in effect");
    const text = container.textContent ?? "";
    for (const placeholder of Object.values(legalPlaceholders)) expect(text).toContain(placeholder);
    expect(Object.values(legalPlaceholders)).toEqual(["[Company legal name]", "[contact email]", "[jurisdiction]"]);
  });
});

describe("404 (06 §1)", () => {
  it("renders its heading and links home and to /docs", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1, name: notFoundCopy.heading })).toBeTruthy();
    const main = screen.getByRole("main");
    expect(within(main).getByRole("link", { name: notFoundCopy.home.label }).getAttribute("href")).toBe("/");
    expect(within(main).getByRole("link", { name: notFoundCopy.docs.label }).getAttribute("href")).toBe("/docs");
  });
});

describe("reduced motion (06 §3)", () => {
  it("globals.css stops animation, transition and smooth scrolling for everything", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");
    const block = css.match(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{([\s\S]*?\})\s*\}/)?.[1] ?? "";
    expect(block).toMatch(/\*\s*,\s*\*::before\s*,\s*\*::after\s*\{/);
    expect(block).toMatch(/animation:\s*none\s*!important/);
    expect(block).toMatch(/transition:\s*none\s*!important/);
    expect(block).toMatch(/scroll-behavior:\s*auto\s*!important/);
  });
});
