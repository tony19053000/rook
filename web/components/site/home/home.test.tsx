// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SiteLayout from "@/app/(site)/layout";
import HomePage from "@/app/(site)/page";
import { FRAME_ROW_BG, FRAME_TOKEN_OVERRIDES } from "./frameTheme";
import { FRAME_MS, Walkthrough } from "./Walkthrough";
import { AGENTS } from "@/lib/agents";
import { readableColor } from "@/lib/contrast";
import { flowSteps, type FlowStep } from "@/content/flow";
import {
  closingCta,
  costAnswer,
  faqSection,
  featuresSection,
  flowDiagram,
  homeFaq,
  homeHero,
  refusalsSection,
  scopeSection,
} from "@/content/home";
import { PRICING_PENDING_NOTICE, plans, pricingStatus, type Plan } from "@/content/pricing";
import { cta, REPO_URL } from "@/content/site";
import { refundCounterexample, refundRule, storyCopy } from "@/content/story";
import { WALKTHROUGH_LABEL, walkthroughCopy, walkthroughFrames } from "@/content/walkthrough";

const REDUCE = "(prefers-reduced-motion: reduce)";

/** window.matchMedia with prefers-reduced-motion set to `reduced` (jsdom has no matchMedia). */
function mockReducedMotion(reduced: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query === REDUCE ? reduced : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })),
  );
}

const SECTION_TITLES = [
  storyCopy.title,
  flowDiagram.title,
  walkthroughCopy.title,
  featuresSection.title,
  refusalsSection.title,
  scopeSection.title,
  faqSection.title,
  closingCta.title,
];

const inSite = (page: ReactElement) => render(<SiteLayout>{page}</SiteLayout>);
const frames = (root: ParentNode) => [...root.querySelectorAll<HTMLElement>('[role="tabpanel"]')];
const visibleFrames = (root: ParentNode) => frames(root).filter((f) => f.getAttribute("aria-hidden") !== "true");
const activeStep = (root: ParentNode) => visibleFrames(root).map((f) => f.dataset.frame);
const tick = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

beforeEach(() => mockReducedMotion(false));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("home: server render (06 §3: complete and still without JS)", () => {
  const html = () => renderToStaticMarkup(<SiteLayout><HomePage /></SiteLayout>);
  const parse = () => new DOMParser().parseFromString(html(), "text/html");

  it("has the hero h1, every section heading, every FAQ question and every step's text", () => {
    const doc = parse();
    expect(doc.querySelector("h1")?.textContent).toBe(homeHero.heading);
    const h2s = [...doc.querySelectorAll("main h2")].map((h) => h.textContent);
    for (const title of SECTION_TITLES) expect(h2s).toContain(title);
    const summaries = [...doc.querySelectorAll("details > summary")].map((s) => s.textContent ?? "");
    for (const item of homeFaq(pricingStatus(plans))) expect(summaries.some((s) => s.includes(item.question))).toBe(true);
    const text = doc.body.textContent ?? "";
    expect(text).toContain(refundRule.check);
    expect(text).toContain(refundCounterexample.reproduced);
    expect(doc.querySelectorAll("ol[data-flow-diagram] > li")).toHaveLength(flowSteps.length);
    expect(doc.querySelectorAll("[data-screenshot] img[alt]")).toHaveLength(2);
    for (const step of flowSteps) {
      expect(text).toContain(step.title);
      expect(text).toContain(step.summary);
    }
  });

  it("shows frame 1 and hides the others (aria-hidden + inert)", () => {
    const doc = parse();
    expect(activeStep(doc)).toEqual([flowSteps[0]!.id]);
    for (const frame of frames(doc).slice(1)) expect(frame.hasAttribute("inert")).toBe(true);
  });

  it("is the still final state: no styles on the hero layers, nothing at opacity 0", () => {
    const doc = parse();
    const layers = [...doc.querySelectorAll("[data-layer]")];
    expect(layers.map((l) => l.getAttribute("data-layer"))).toEqual(["grid", "glow", "figure"]);
    for (const layer of layers) expect(layer.getAttribute("style")).toBeNull();
    expect(html()).not.toMatch(/opacity:\s*0[;"]/);
  });
});

describe("home: hero (06 §5.1)", () => {
  it("keeps the text (eyebrow, h1, lead, CTAs) outside every moving layer", () => {
    const { container } = inSite(<HomePage />);
    const hero = container.querySelector("[data-hero]")!;
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.closest("[data-layer]")).toBeNull();
    expect(h1.closest("[data-hero-text]")).not.toBeNull();
    for (const link of within(hero as HTMLElement).getAllByRole("link")) expect(link.closest("[data-layer]")).toBeNull();
    expect(within(hero as HTMLElement).getByText(homeHero.lead).closest("[data-layer]")).toBeNull();
  });

  it("moves the layers when motion is allowed, and labels the screenshot a recorded example run", () => {
    const { container } = inSite(<HomePage />);
    for (const layer of container.querySelectorAll("[data-layer]")) expect(layer.getAttribute("style") ?? "").toMatch(/transform/);
    const figure = container.querySelector('[data-layer="figure"]') as HTMLElement;
    expect(within(figure).getByText("Recorded example run")).toBeTruthy();
  });

  it("names the problem and the outcome in plain words", () => {
    expect(homeHero.heading).toMatch(/sequence of API calls/);
    expect(homeHero.heading).toMatch(/business rules/);
    expect(homeHero.lead).toMatch(/smallest sequence/);
    expect(homeHero.lead).toMatch(/verifies the fix/);
  });

  it("has the CTAs: Try Roook (/app), Read the docs and the GitHub repo", () => {
    const { container } = inSite(<HomePage />);
    const hero = container.querySelector("[data-hero]") as HTMLElement;
    const links = within(hero).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      [cta.demo.label, "/app"],
      [cta.docs.label, cta.docs.href],
      [`${homeHero.github.label}↗`, REPO_URL],
    ]);
    expect(cta.demo.label).toBe("Try Roook");
    expect(cta.docs.label).toBe("Read the docs");
    expect(links[2]!.getAttribute("rel")).toBe("noopener noreferrer");
  });
});

describe("home: landmarks and headings", () => {
  it("has banner, navigation, main and contentinfo, one h1, and no skipped heading level", () => {
    const { container } = inSite(<HomePage />);
    for (const role of ["banner", "main", "contentinfo"] as const) expect(screen.getAllByRole(role)).toHaveLength(1);
    expect(screen.getAllByRole("navigation").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const levels = [...container.querySelectorAll("main h1, main h2, main h3, main h4, main h5, main h6")].map((h) => Number(h.tagName[1]));
    expect(levels[0]).toBe(1);
    levels.forEach((level, i) => {
      if (i > 0) expect(level - levels[i - 1]!, `heading ${i}`).toBeLessThanOrEqual(1);
    });
  });

  it("puts the story right after the hero, then the diagram and the walkthrough", () => {
    const { container } = inSite(<HomePage />);
    const ids = [...container.querySelectorAll("main > section, main > * > section")].map((s) => s.id || (s.hasAttribute("data-hero") ? "hero" : ""));
    expect(ids.slice(0, 4)).toEqual(["hero", storyCopy.id, flowDiagram.id, walkthroughCopy.id]);
  });
});

describe("walkthrough (06 §6)", () => {
  beforeEach(() => vi.useFakeTimers());

  it("lists the steps of flowSteps as tabs, and has a frame for every step", () => {
    render(<Walkthrough />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.querySelector("span.font-semibold")?.textContent)).toEqual(flowSteps.map((s) => s.title));
    expect(flowSteps.every((s) => walkthroughFrames.some((f) => f.stepId === s.id))).toBe(true);
  });

  it("a step added to the list shows up as a tab and a frame", () => {
    const extra: FlowStep = { id: "extra", title: "An extra step", summary: "Added in a test copy.", details: [] };
    const { container } = render(<Walkthrough steps={[...flowSteps, extra]} />);
    expect(screen.getAllByRole("tab")).toHaveLength(flowSteps.length + 1);
    expect(screen.getByRole("tab", { name: /An extra step/ })).toBeTruthy();
    expect(container.querySelector('[data-frame="extra"]')).not.toBeNull();
  });

  it("exposes exactly one frame; the others are aria-hidden and inert", () => {
    const { container } = render(<Walkthrough />);
    expect(frames(container)).toHaveLength(flowSteps.length);
    expect(visibleFrames(container)).toHaveLength(1);
    for (const frame of frames(container)) {
      const hidden = frame.getAttribute("aria-hidden") === "true";
      expect(frame.hasAttribute("inert")).toBe(hidden);
    }
  });

  it("labels every frame 'Product illustration — not a live run', outside the inert app window", () => {
    const { container } = render(<Walkthrough />);
    for (const frame of frames(container)) {
      const label = within(frame).getByText(WALKTHROUGH_LABEL);
      expect(label.closest(".wt-frame")).toBeNull();
      expect(frame.querySelector(".wt-frame")?.hasAttribute("inert")).toBe(true);
    }
    expect(WALKTHROUGH_LABEL).toBe("Product illustration — not a live run");
  });

  it("draws the frames with the app's real run components", () => {
    const { container } = render(<Walkthrough />);
    const frame = (id: string) => container.querySelector(`[data-frame="${id}"]`)!;
    expect(frame("understand").querySelectorAll('[data-row="agent"]').length).toBeGreaterThan(0);
    expect(frame("understand").querySelector('[data-row="engine"]')).not.toBeNull();
    expect(frame("rules").querySelector('[data-card="rules"]')).not.toBeNull();
    expect(frame("search").querySelector('[data-card="search"]')).not.toBeNull();
    expect(frame("shrink").querySelector('[data-card="counterexample"]')?.textContent).toContain("Reproduced 10/10");
    expect(frame("fix").querySelector('[data-card="fix"]')).not.toBeNull();
    expect(frame("verify").querySelector("[data-verified]")?.textContent).toContain("FIX VERIFIED");
  });

  it("applies the frame contrast fixes: token overrides, and readable agent text colours", () => {
    const { container } = render(<Walkthrough />);
    for (const win of container.querySelectorAll<HTMLElement>(".wt-frame")) {
      for (const [name, value] of Object.entries(FRAME_TOKEN_OVERRIDES)) expect(win.style.getPropertyValue(name)).toBe(value);
    }
    const lawmaker = container.querySelector('[data-frame="rules"] [data-row="agent"] span.font-semibold') as HTMLElement;
    expect(lawmaker.textContent).toBe("Lawmaker");
    const expected = readableColor(AGENTS.lawmaker.color, FRAME_ROW_BG);
    const probe = document.createElement("span");
    probe.style.color = expected;
    expect(lawmaker.style.color).toBe(probe.style.color);
  });

  it("autoplays: the next frame after FRAME_MS, wrapping round at the end", () => {
    const { container } = render(<Walkthrough />);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    tick(FRAME_MS - 10);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    tick(10);
    expect(activeStep(container)).toEqual([flowSteps[1]!.id]);
    expect(screen.getAllByRole("tab")[1]!.getAttribute("aria-selected")).toBe("true");
    for (let i = 2; i <= flowSteps.length; i += 1) {
      tick(FRAME_MS);
      expect(activeStep(container)).toEqual([flowSteps[i % flowSteps.length]!.id]);
    }
  });

  it("clicking a step slides to its frame and stops autoplay", () => {
    const { container } = render(<Walkthrough />);
    fireEvent.click(screen.getAllByRole("tab")[3]!);
    expect(activeStep(container)).toEqual([flowSteps[3]!.id]);
    expect((container.querySelector("[data-track]") as HTMLElement).style.transform).toBe("translateX(-300%)");
    tick(FRAME_MS * 3);
    expect(activeStep(container)).toEqual([flowSteps[3]!.id]);
  });

  it("arrow keys, Home and End move between steps (roving tabindex)", () => {
    const { container } = render(<Walkthrough />);
    const tabs = screen.getAllByRole("tab");
    fireEvent.keyDown(tabs[0]!, { key: "ArrowDown" });
    expect(activeStep(container)).toEqual([flowSteps[1]!.id]);
    expect(document.activeElement).toBe(tabs[1]);
    fireEvent.keyDown(tabs[1]!, { key: "End" });
    expect(activeStep(container)).toEqual([flowSteps.at(-1)!.id]);
    fireEvent.keyDown(tabs.at(-1)!, { key: "ArrowDown" });
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    expect(tabs.map((t) => t.tabIndex)).toEqual(flowSteps.map((_, i) => (i === 0 ? 0 : -1)));
  });

  it("pause stops autoplay and play resumes it", () => {
    const { container } = render(<Walkthrough />);
    fireEvent.click(screen.getByRole("button", { name: /Pause the walkthrough/ }));
    tick(FRAME_MS * 3);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    fireEvent.click(screen.getByRole("button", { name: /Play the walkthrough/ }));
    tick(FRAME_MS);
    expect(activeStep(container)).toEqual([flowSteps[1]!.id]);
  });

  it("pauses while the tab is hidden and resumes when it is visible again", () => {
    let state: DocumentVisibilityState = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => state);
    const { container } = render(<Walkthrough />);
    tick(FRAME_MS / 2);
    state = "hidden";
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    tick(FRAME_MS * 3);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    state = "visible";
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    tick(FRAME_MS / 2);
    expect(activeStep(container)).toEqual([flowSteps[1]!.id]);
  });

  it("pauses while the section is off screen", () => {
    let report: (entries: Partial<IntersectionObserverEntry>[]) => void = () => {};
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(callback: (entries: Partial<IntersectionObserverEntry>[]) => void) {
          report = callback;
        }
        observe() {}
        disconnect() {}
      },
    );
    const { container } = render(<Walkthrough />);
    act(() => report([{ isIntersecting: false }]));
    tick(FRAME_MS * 3);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    act(() => report([{ isIntersecting: true }]));
    tick(FRAME_MS);
    expect(activeStep(container)).toEqual([flowSteps[1]!.id]);
  });

  it("makes no network calls while rendering, autoplaying and clicking steps", () => {
    const used: string[] = [];
    const spy = (name: string) =>
      vi.fn(function () {
        used.push(name);
        throw new Error(`${name} must not be used by the walkthrough`);
      });
    vi.stubGlobal("fetch", spy("fetch"));
    vi.stubGlobal("XMLHttpRequest", spy("XMLHttpRequest"));
    vi.stubGlobal("EventSource", spy("EventSource"));
    vi.stubGlobal("WebSocket", spy("WebSocket"));
    const sendBeacon = vi.fn(() => {
      used.push("sendBeacon");
      return false;
    });
    Object.defineProperty(navigator, "sendBeacon", { value: sendBeacon, configurable: true });
    inSite(<HomePage />);
    tick(FRAME_MS * (flowSteps.length + 1));
    for (const tab of screen.getAllByRole("tab")) fireEvent.click(tab);
    tick(FRAME_MS * 2);
    expect(used).toEqual([]);
  });
});

describe("home under reduced motion (06 §3)", () => {
  beforeEach(() => {
    mockReducedMotion(true);
    vi.useFakeTimers();
  });

  it("does not autoplay, and switches frames instantly (no slide transition)", () => {
    const { container } = inSite(<HomePage />);
    tick(FRAME_MS * 5);
    expect(activeStep(container)).toEqual([flowSteps[0]!.id]);
    expect(screen.getByRole("button", { name: /Play the walkthrough/ })).toBeTruthy();
    const track = container.querySelector("[data-track]")!;
    expect(track.className).not.toMatch(/transition/);
    fireEvent.click(screen.getAllByRole("tab")[2]!);
    expect(activeStep(container)).toEqual([flowSteps[2]!.id]);
  });

  it("puts no transform on the hero layers", () => {
    const { container } = inSite(<HomePage />);
    const layers = [...container.querySelectorAll<HTMLElement>("[data-layer]")];
    expect(layers).toHaveLength(3);
    for (const layer of layers) {
      expect(layer.getAttribute("style")).toBeNull();
      expect(layer.style.transform).toBe("");
    }
  });

  it("keeps agent sprites still (no ticking sprite in any frame)", () => {
    const { container } = inSite(<HomePage />);
    const sprites = [...container.querySelectorAll("[data-agent-sprite]")];
    expect(sprites.length).toBeGreaterThan(0);
    for (const sprite of sprites) expect(sprite.getAttribute("data-motion")).toBe("static");
  });

  it("is complete: every section heading and FAQ question is there", () => {
    inSite(<HomePage />);
    for (const title of SECTION_TITLES) expect(screen.getByRole("heading", { level: 2, name: title })).toBeTruthy();
    for (const item of homeFaq(pricingStatus(plans))) expect(screen.getByText(item.question)).toBeTruthy();
  });
});

describe("FAQ cost answer (06 §5.4: derived from content/pricing.ts)", () => {
  const plan: Plan = { name: "Team", price: "x", summary: "s", features: [] };

  it("follows the pricing status", () => {
    expect(costAnswer(pricingStatus([]))).toContain(PRICING_PENDING_NOTICE);
    const published = costAnswer(pricingStatus([plan]));
    expect(published).toContain("Team");
    expect(published).not.toContain(PRICING_PENDING_NOTICE);
    expect(homeFaq(pricingStatus([])).find((f) => f.question === "What does it cost?")?.answer).toBe(costAnswer(pricingStatus([])));
  });

  it("the page reads the plans export (a plan there changes the answer)", async () => {
    vi.resetModules();
    vi.doMock("@/content/pricing", async (original) => ({
      ...(await original<typeof import("@/content/pricing")>()),
      plans: [plan],
    }));
    try {
      const { default: MockedHome } = await import("@/app/(site)/page");
      render(<MockedHome />);
      const cost = screen.getByText("What does it cost?").closest("details")!;
      expect(cost.textContent).toContain("Team");
      expect(cost.textContent).not.toContain(PRICING_PENDING_NOTICE);
    } finally {
      vi.doUnmock("@/content/pricing");
      vi.resetModules();
    }
  });
});
