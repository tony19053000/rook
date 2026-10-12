// @vitest-environment jsdom
// ROOK-053: the new pages (/about, /contact, /roadmap), pricing as "Early access and open source", the header and
// footer links, the sitemap, robots and metadataBase.
import { readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Metadata } from "next";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SiteLayout from "@/app/(site)/layout";
import AboutPage from "@/app/(site)/about/page";
import ContactPage from "@/app/(site)/contact/page";
import PricingPage from "@/app/(site)/pricing/page";
import RoadmapPage from "@/app/(site)/roadmap/page";
import HomePage from "@/app/(site)/page";
import { metadata as rootMetadata } from "@/app/layout";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { DOCS_OVERVIEW, GUIDE_PAGES } from "./docs/testPages";
import { aboutCopy, aboutLinks } from "@/content/about";
import { contactChannels } from "@/content/contact";
import { docsNav, guides } from "@/content/docsGuides";
import { PRICING_PENDING_NOTICE, pricingCopy, useWays } from "@/content/pricing";
import { roadmapLists } from "@/content/roadmap";
import { loginCopy } from "@/content/login";
import { CONTACT_EMAIL, cta, footerColumns, headerNav, ISSUES_URL, notFoundCopy, operator, REPO_URL, SITE_URL } from "@/content/site";
import { ROBOTS_DISALLOW, SITEMAP_PATHS } from "@/lib/seo";

const router = { replace: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));
// app/layout.tsx loads its fonts through next/font (app/fonts.ts), which only works inside the Next build.
vi.mock("next/font/local", () => ({ default: () => ({ variable: "font" }) }));

afterEach(cleanup);

const inSite = (page: ReactElement) => render(<SiteLayout>{page}</SiteLayout>);
const APP_DIR = resolve(process.cwd(), "app");

/** Every route an app/**\/page.tsx serves, with route groups like "(site)" dropped (they add no URL segment). */
function pageRoutes(dir = APP_DIR, segments: string[] = []): string[] {
  const routes: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      routes.push(...pageRoutes(full, /^\(.+\)$/.test(name) ? segments : [...segments, name]));
    } else if (name === "page.tsx") {
      routes.push(`/${segments.join("/")}`);
    }
  }
  return routes;
}

/** The route a site href points at, or null for an external link. */
function internalPath(href: string): string | null {
  if (!href.startsWith("/")) return null;
  return href.split(/[?#]/)[0]!;
}

describe("every header, footer and CTA link resolves (ROOK-053)", () => {
  const routes = new Set(pageRoutes());

  it("finds the routes, route groups included", () => {
    for (const route of ["/", "/app", "/docs", "/about", "/contact", "/roadmap", "/pricing", "/login", "/runs/[id]"]) expect(routes, route).toContain(route);
  });

  it("each internal href is an existing app/**/page.tsx route", () => {
    const links = [...headerNav, ...footerColumns.flatMap((c) => c.links), ...Object.values(cta), ...aboutLinks, ...useWays.map((w) => w.link), pricingCopy.interest.link, loginCopy.cliLink, notFoundCopy.home, notFoundCopy.docs];
    const internal = links.flatMap((l) => (internalPath(l.href) === null ? [] : [l.href]));
    expect(internal.length).toBeGreaterThan(15);
    for (const href of internal) expect(routes, href).toContain(internalPath(href));
  });

  it("each internal href in the rendered header and footer resolves too", () => {
    const { container } = inSite(<HomePage />);
    const hrefs = [...container.querySelectorAll("header a[href], footer a[href]")].map((a) => a.getAttribute("href")!);
    for (const href of hrefs) {
      const path = internalPath(href);
      if (path !== null && !href.startsWith("#")) expect(routes, href).toContain(path);
    }
  });

  // ROOK-055: every link on every docs page, the ones written in the guides' copy included.
  const docsPages = [DOCS_OVERVIEW, ...GUIDE_PAGES];

  it("finds the docs guides among the routes", () => {
    for (const [path] of docsPages) expect(routes, path).toContain(path);
    expect(docsPages).toHaveLength(7);
  });

  it("each internal href in the docs copy is an existing route", () => {
    const blocks = guides.flatMap((g) => g.sections.flatMap((s) => [...s.blocks, ...(s.subsections ?? []).flatMap((sub) => sub.blocks)]));
    const links = [...docsNav, ...blocks.flatMap((b) => (b.kind === "links" ? b.items : []))];
    const internal = links.flatMap((l) => (internalPath(l.href) === null ? [] : [l.href]));
    expect(internal.length).toBeGreaterThan(15);
    for (const href of internal) expect(routes, href).toContain(internalPath(href));
    for (const l of links) expect(l.external === true, l.href).toBe(internalPath(l.href) === null);
  });

  it("each href on each rendered docs page resolves: the route exists, and so does the anchor on its page", () => {
    // The ids of every page an anchor may point at: the docs pages, each rendered once.
    const idsByPath = new Map<string, Set<string>>();
    const hrefsByPath = new Map<string, string[]>();
    for (const [path, page] of docsPages) {
      const { container } = inSite(page());
      idsByPath.set(path, new Set([...container.querySelectorAll("[id]")].map((el) => el.id)));
      hrefsByPath.set(path, [...container.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")!));
      cleanup();
    }
    let anchors = 0;
    for (const [path, hrefs] of hrefsByPath) {
      expect(hrefs.length, path).toBeGreaterThan(20);
      for (const href of hrefs) {
        const target = href.startsWith("#") ? path : internalPath(href);
        if (target === null) {
          expect(href, `${path}: an external link`).toMatch(/^(https:\/\/|mailto:)/);
          continue;
        }
        expect(routes, `${path}: ${href}`).toContain(target);
        const hash = href.split("#")[1];
        if (hash === undefined) continue;
        const ids = idsByPath.get(target);
        expect(ids, `${path}: ${href} points into a page this test does not render`).toBeDefined();
        expect(ids!.has(hash), `${path}: ${href}`).toBe(true);
        anchors += 1;
      }
    }
    expect(anchors).toBeGreaterThan(40);
  });

  it("the header and footer follow 06 §8 (footer: Product, Docs, Company, Legal)", () => {
    expect(headerNav.map((l) => l.label)).toEqual(["Docs", "Security", "Pricing", "Roadmap", "GitHub"]);
    const columns = Object.fromEntries(footerColumns.map((c) => [c.heading, c.links.map((l) => l.label)]));
    expect(columns).toEqual({
      Product: ["Overview", "Try Rook", "Pricing", "Roadmap", "Sign in"],
      Docs: ["Getting started", "Install", "Rules", "GitHub Action", "Data and IBM Bob"],
      Company: ["About", "Contact", "GitHub"],
      Legal: ["Privacy", "Terms", "Security"],
    });
  });

  it('the CTAs: "Try Rook" → /app and "Read the docs" → the getting-started docs', () => {
    expect(cta.demo).toEqual({ label: "Try Rook", href: "/app" });
    expect(cta.docs).toEqual({ label: "Read the docs", href: "/docs/getting-started" });
    inSite(<HomePage />);
    const hero = document.querySelector("[data-hero]") as HTMLElement;
    expect(within(hero).getByRole("link", { name: "Read the docs" }).getAttribute("href")).toBe(cta.docs.href);
  });
});

describe("sitemap, robots and metadataBase (06 §1, §8)", () => {
  const sitePages = pageRoutes(join(APP_DIR, "(site)")).filter((r) => r !== "/login");

  it("the sitemap lists exactly the site pages, on SITE_URL", () => {
    const urls = sitemap().map((entry) => entry.url);
    expect(urls.every((u) => u.startsWith(`${SITE_URL}/`))).toBe(true);
    expect(urls.map((u) => new URL(u).pathname).sort()).toEqual([...sitePages].sort());
    expect([...SITEMAP_PATHS].sort()).toEqual([...sitePages].sort());
  });

  it("robots allows the site, disallows the app routes, /dev and /api, and points at the sitemap", () => {
    const { rules, sitemap: map } = robots();
    const rule = Array.isArray(rules) ? rules[0]! : rules;
    expect(rule.userAgent).toBe("*");
    expect(rule.allow).toBe("/");
    const disallow = [rule.disallow].flat();
    for (const path of ["/app", "/runs", "/rules", "/counterexamples", "/repositories", "/github", "/dev", "/api"]) expect(disallow).toContain(path);
    expect(disallow).toEqual([...ROBOTS_DISALLOW]);
    for (const page of sitePages) {
      for (const blocked of disallow) expect(page === blocked || page.startsWith(`${blocked}/`), `${page} vs ${blocked}`).toBe(false);
    }
    expect(map).toBe(`${SITE_URL}/sitemap.xml`);
  });

  it("every app route is disallowed", () => {
    const appRoutes = pageRoutes().filter((r) => !sitePages.includes(r) && r !== "/login");
    expect(appRoutes.length).toBeGreaterThan(5);
    for (const route of appRoutes) expect(ROBOTS_DISALLOW.some((d) => route === d || route.startsWith(`${d}/`)), route).toBe(true);
  });

  it("every site page has its own title, description, canonical path and matching OG/Twitter cards", async () => {
    for (const path of SITEMAP_PATHS.filter((p) => p !== "/")) {
      const mod = (await import(`@/app/(site)${path}/page`)) as { metadata: Metadata };
      const { title, description, alternates, openGraph, twitter } = mod.metadata;
      expect(typeof title === "string" && title.length > 0, path).toBe(true);
      expect(String(description).length, path).toBeGreaterThan(20);
      expect(alternates?.canonical, path).toBe(path);
      expect(openGraph?.title, path).toBe(`${String(title)} · Rook`);
      expect(openGraph?.description, path).toBe(description);
      expect((twitter as { card?: string } | undefined)?.card, path).toBe("summary_large_image");
      expect(JSON.stringify(openGraph?.images), path).toContain('"url":"/opengraph-image"');
      expect(JSON.stringify(twitter?.images), path).toContain('"url":"/twitter-image"');
      expect(`${String(title)} ${String(description)}`, path).not.toMatch(/hackathon|\bdemo\b/i);
    }
  });

  it("metadataBase is SITE_URL", () => {
    expect(SITE_URL).toBe("https://rook-weld-six.vercel.app");
    expect(rootMetadata.metadataBase?.toString()).toBe(`${SITE_URL}/`);
    expect(String(rootMetadata.description)).not.toMatch(/hackathon/i);
  });
});

describe("/contact (06 §5.9)", () => {
  it("has mailto: links with prefilled subjects for general, early access and privacy, plus GitHub Issues, and no form", () => {
    const { container } = inSite(<ContactPage />);
    const main = screen.getByRole("main");
    expect(main.textContent).toContain(CONTACT_EMAIL);
    const subjects: Record<string, string> = {};
    for (const id of ["general", "early-access", "privacy"]) {
      const href = main.querySelector(`a[data-channel="${id}"]`)?.getAttribute("href") ?? "";
      const url = new URL(href);
      expect(url.protocol, id).toBe("mailto:");
      expect(url.pathname, id).toBe(CONTACT_EMAIL);
      subjects[id] = url.searchParams.get("subject") ?? "";
    }
    expect(subjects).toEqual({ general: "Rook: question", "early-access": "Rook: early access", privacy: "Rook: privacy request" });
    expect(main.querySelector('a[data-channel="issues"]')?.getAttribute("href")).toBe(`${REPO_URL}/issues`);
    expect(ISSUES_URL).toBe(`${REPO_URL}/issues`);
    expect(container.querySelector("form")).toBeNull();
    expect(contactChannels).toHaveLength(4);
    expect(main.textContent).toMatch(/no promised response time/i);
  });
});

describe("/about (06 §5.7)", () => {
  it("names the operator, India, the hackathon story and what Rook is not", () => {
    inSite(<AboutPage />);
    const main = screen.getByRole("main");
    const text = main.textContent ?? "";
    expect(operator).toEqual({ name: "Aayush Kumar", location: "India" });
    expect(text).toContain("Aayush Kumar");
    expect(text).toContain("India");
    expect(text).toContain("Rook started at the IBM Bob 2.0 Hackathon in September 2026.");
    expect(text).toMatch(/early-access, open-source/);
    expect(text).toMatch(/Not a company: there is no incorporation, no employees and no outside funding\./);
    expect(screen.getByRole("heading", { level: 1, name: aboutCopy.heading })).toBeTruthy();
  });
});

describe("/roadmap (06 §5.8)", () => {
  it("has Shipped, Limited and Planned, in that order, and no dates on the plans", () => {
    const { container } = inSite(<RoadmapPage />);
    const h2s = [...container.querySelectorAll("main h2")].map((h) => h.textContent);
    expect(h2s).toEqual(["Shipped", "Limited", "Planned"]);
    for (const list of roadmapLists) {
      const ul = container.querySelector(`[data-roadmap="${list.id}"]`)!;
      expect(ul.querySelectorAll("li")).toHaveLength(list.items.length);
    }
    const planned = roadmapLists.find((l) => l.id === "planned")!.items.join("\n");
    expect(planned).not.toMatch(/\b(19|20)\d\d\b|\bQ[1-4]\b|\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sept?(ember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b|\bsoon\b|\bnext (week|month|quarter|year)\b/i);
  });

  it("says hosted runs of your own repos are off (run them with the CLI)", () => {
    const limited = roadmapLists.find((l) => l.id === "limited")!.items.join("\n");
    expect(limited).toMatch(/Hosted runs of your own repos are turned off/);
    expect(limited).toMatch(/with the CLI/);
  });
});

describe("/pricing: early access and open source (06 §5.4)", () => {
  it("shows the three ways in words, the notice and the hosted-interest link to /contact", () => {
    inSite(<PricingPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Early access and open source" })).toBeTruthy();
    expect(useWays.map((w) => w.name)).toEqual(["Try Rook on this site", "The CLI on your machine", "Hosted runs of your own repos"]);
    for (const way of useWays) {
      const card = screen.getByRole("heading", { level: 3, name: way.name }).closest("article") as HTMLElement;
      expect(within(card).getByText(way.cost)).toBeTruthy();
    }
    expect(screen.getByText(PRICING_PENDING_NOTICE)).toBeTruthy();
    const interest = screen.getByRole("heading", { level: 2, name: pricingCopy.interest.title }).closest("section") as HTMLElement;
    expect(within(interest).getByRole("link", { name: "Contact" }).getAttribute("href")).toBe("/contact");
  });
});
