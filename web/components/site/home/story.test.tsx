// @vitest-environment jsdom
// ROOK-054: the refund story's values match the recorded run they come from (lib/fixtures/minishop-run.json), and
// the story section, the 6-step diagram and the product screenshots render complete in the server render.
import { cleanup, render, screen, within } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { FlowDiagram } from "./FlowDiagram";
import { RefundStory } from "./RefundStory";
import { RunScreenshot } from "./RunScreenshot";
import SiteLayout from "@/app/(site)/layout";
import HomePage from "@/app/(site)/page";
import { flowSteps, type FlowStep } from "@/content/flow";
import { flowDiagram, runScreenshot } from "@/content/home";
import {
  refundChecks,
  refundCounterexample,
  refundDiagnosis,
  refundFix,
  refundFound,
  refundOutcome,
  refundRule,
  storyCopy,
} from "@/content/story";
import { stepText } from "@/lib/cardText";
import { copyViolations } from "@/lib/copyRules";
import { isRecordedData, RECORDED_LINES, RUN_DATA_ATTR, scannableText } from "@/lib/recordedData";
import { walkthroughFrames } from "@/content/walkthrough";
import raw from "@/lib/fixtures/minishop-run.json";

afterEach(cleanup);

interface RawEvent {
  type: string;
  data: Record<string, unknown>;
}
const events = raw as RawEvent[];
const all = (type: string) => events.filter((e) => e.type === type).map((e) => e.data);
const one = (type: string) => {
  const found = all(type);
  expect(found, type).toHaveLength(1);
  return found[0]!;
};
const engineSummary = (worker: string, pattern: RegExp) =>
  all("engine.finished").find((d) => d.worker === worker && pattern.test(String(d.summary)))?.summary as string | undefined;

describe("the refund story matches the recorded run (lib/fixtures/minishop-run.json)", () => {
  const saved = all("counterexample.saved").at(-1)!;

  it("the rule: approved, with its text and check", () => {
    expect(one("rules.approved").rule_ids).toEqual([refundRule.id]);
    expect(saved.rule_id).toBe(refundRule.id);
    expect(saved.rule_text).toBe(refundRule.text);
    expect(saved.expected).toBe(refundRule.check);
  });

  it("the first failing sequence, before the shrinker", () => {
    const found = one("violation.found");
    expect(found.rule_id).toBe(refundRule.id);
    expect(found.steps_count).toBe(refundFound.steps);
    expect(found.observed).toMatchObject({ paid: refundFound.paid, refunded_total: refundFound.refundedTotal });
  });

  it("the minimal counterexample: its steps and values, the replay, the test and the shrinker", () => {
    expect(saved.cx_id).toBe(refundCounterexample.id);
    const steps = (saved.steps as { actor: string; action: string; params: unknown }[]).map(({ actor, action, params }) => ({ actor, action, params }));
    expect(steps).toEqual(refundCounterexample.steps);
    expect(saved.observed).toEqual(refundCounterexample.observed);
    expect(saved.reproduced).toBe(refundCounterexample.reproduced);
    expect(saved.flaky).toBe(false);
    expect(saved.test_path).toBe(refundCounterexample.testPath);
    expect(engineSummary("shrinker", /steps/)).toBe(refundCounterexample.shrinkSummary);
    expect(engineSummary("testrunner", /exit 1/)).toBe(`regression test ${refundCounterexample.testPath}: ${refundCounterexample.testBeforeFix}`);
  });

  it("the diagnosis: file, line, the first sentence verbatim, reviewed", () => {
    const d = one("diagnosis.ready");
    expect(d).toMatchObject({ cx_id: refundCounterexample.id, file: refundDiagnosis.file, line: refundDiagnosis.line, reviewed: true });
    expect(d.explanation).toBe(refundDiagnosis.explanation);
    expect(String(d.explanation).startsWith(refundDiagnosis.sentence)).toBe(true);
  });

  it("the fix: the reviewed diff, verbatim but for its @@ hunk header", () => {
    const f = one("fix.ready");
    expect(f.files).toEqual(refundFix.files);
    expect(f.reviewed).toBe(true);
    const withoutHunk = String(f.diff)
      .split("\n")
      .filter((line) => !line.startsWith("@@"))
      .join("\n");
    expect(refundFix.diff).toBe(withoutHunk);
  });

  it("the four checks: each passed with the engine's own detail, then 4/4 and the branch", () => {
    const passed = all("verify.step").filter((d) => d.status === "passed");
    expect(passed.map((d) => d.check)).toEqual(refundChecks.map((c) => c.id));
    for (const check of refundChecks) expect(passed.find((d) => d.check === check.id)?.detail).toBe(check.detail);
    expect(one("verify.done")).toMatchObject({ verified: true, summary: refundOutcome.summary });
    expect(one("fix.committed").branch).toBe(refundOutcome.branch);
    expect(String(one("fix.committed").files)).toContain(refundCounterexample.testPath);
  });

  it("states the fresh-search budget it actually ran, not the CLI default as if it were", () => {
    const fresh = refundChecks.find((c) => c.id === "fresh_search")!;
    expect(fresh.detail).toContain("1500 sequences");
    expect(fresh.meaning).toContain("1,500");
    expect(fresh.meaning).toContain("the CLI default is 20,000");
  });

  it("the walkthrough draws the same case (no other numbers, no 20,000-sequence claim)", () => {
    const items = walkthroughFrames.flatMap((f) => f.items);
    const cx = items.find((i) => i.kind === "counterexample");
    const fix = items.find((i) => i.kind === "fix");
    const verify = items.find((i) => i.kind === "verify");
    expect(cx?.kind === "counterexample" && cx.saved?.observed).toEqual(refundCounterexample.observed);
    expect(cx?.kind === "counterexample" && cx.saved?.expected).toBe(refundRule.check);
    expect(fix?.kind === "fix" && fix.fix?.diff).toBe(refundFix.diff);
    expect(fix?.kind === "fix" && fix.diagnosis?.line).toBe(refundDiagnosis.line);
    expect(verify?.kind === "verify" && verify.checks.fresh_search?.detail).toBe(refundChecks[3]!.detail);
    expect(JSON.stringify(walkthroughFrames)).not.toMatch(/20,?000/);
  });
});

describe("the refund story section", () => {
  it("shows the rule, every step, the values, the replay, the diagnosis, the diff and the four checks", () => {
    const { container } = render(<RefundStory />);
    expect(screen.getByText(refundRule.text)).toBeTruthy();
    expect(container.textContent).toContain(refundRule.check);
    const steps = within(container.querySelector("[data-story-steps]") as HTMLElement).getAllByRole("listitem");
    expect(steps.map((li) => li.textContent?.replace(/^\d+/, ""))).toEqual(refundCounterexample.steps.map(stepText));
    expect(container.querySelector("[data-story-observed]")?.textContent).toBe("paid1refunded_total2");
    expect(container.querySelector("[data-story-replayed]")?.textContent).toBe("10/10");
    expect(container.querySelector("[data-story-diagnosis]")?.textContent).toBe("app.py:214");
    const diff = [...container.querySelectorAll<HTMLElement>("[data-story-diff] [data-diff]")];
    expect(diff.map((l) => l.textContent)).toEqual(refundFix.diff.split("\n").filter((line) => line !== ""));
    expect(diff.filter((l) => l.dataset.diff === "added").map((l) => l.textContent)).toEqual(["+        already = order.refunded_total"]);
    const checks = within(container.querySelector("[data-story-checks]") as HTMLElement).getAllByRole("listitem");
    expect(checks).toHaveLength(4);
    for (const check of refundChecks) expect(container.textContent).toContain(check.detail);
    expect(container.textContent).toContain(refundOutcome.branch);
  });

  it("is labelled a recorded example run, and says where the values come from", () => {
    const { container } = render(<RefundStory />);
    expect(screen.getByText(runScreenshot.label)).toBeTruthy();
    expect(container.textContent).toContain(storyCopy.source);
  });

  it("has an h3 per stage, under the section's h2", () => {
    render(
      <SiteLayout>
        <HomePage />
      </SiteLayout>,
    );
    const section = screen.getByRole("region", { name: storyCopy.title });
    const h3s = within(section).getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(h3s).toEqual(Object.values(storyCopy.stages).map((s) => s.title));
  });
});

describe("run data on the page is exempt from the copy rules by identity only (lib/recordedData.ts)", () => {
  const home = () =>
    render(
      <SiteLayout>
        <HomePage />
      </SiteLayout>,
    ).container;
  const marked = (root: Element) => [...root.querySelectorAll(`[${RUN_DATA_ATTR}]`)];

  it("every marked node on the home page is exactly one step line or diff line of the recording", () => {
    const nodes = marked(home());
    // The story's 4 steps and its diff lines, plus the same in the walkthrough's counterexample and fix cards.
    expect(nodes.length).toBeGreaterThanOrEqual(2 * refundCounterexample.steps.length + 2);
    for (const node of nodes) expect(RECORDED_LINES.has(node.textContent ?? ""), node.textContent ?? "").toBe(true);
  });

  it("those lines would break the strict rules, which is why they are exempt, and the page scan is clean", () => {
    const root = home();
    const lines = marked(root).map((n) => n.textContent ?? "");
    expect(lines.some((line) => copyViolations(line).includes("customers"))).toBe(true);
    expect(copyViolations(lines.join("\n"))).toContain("count with a plus (1,000+)");
    expect(copyViolations(scannableText(root))).toEqual([]);
  });

  it("a mark cannot hide prose: any other text in a marked node is still scanned", () => {
    for (const prose of [
      "happy customer: refund(amount=1) feedback",
      "our customer: love(it)",
      "Built for every customer",
      "customer",
      "500\n+ runs",
      "1,000\n+ teams",
      "1,000\n+ bugs found",
    ]) {
      const { container, unmount } = render(
        <p>
          Rook: <span {...{ [RUN_DATA_ATTR]: "" }}>{prose}</span>
        </p>,
      );
      expect(isRecordedData(container.querySelector("span")!), prose).toBe(false);
      expect(copyViolations(scannableText(container)), prose).not.toEqual([]);
      unmount();
    }
  });

  it("a real line is skipped only when it is the node's whole text, and only in a marked node", () => {
    const line = stepText(refundCounterexample.steps[2]!);
    const whole = render(<span {...{ [RUN_DATA_ATTR]: "" }}>{line}</span>);
    expect(copyViolations(scannableText(whole.container))).toEqual([]);
    whole.unmount();
    const padded = render(<span {...{ [RUN_DATA_ATTR]: "" }}>{`happy ${line} feedback`}</span>);
    expect(copyViolations(scannableText(padded.container))).toContain("customers");
    padded.unmount();
    const unmarked = render(<span>{line}</span>);
    expect(copyViolations(scannableText(unmarked.container))).toContain("customers");
  });
});

describe("the 6-step diagram (content/flow.ts)", () => {
  it("is a real ordered list of every step, with its title, summary and who does it", () => {
    render(<FlowDiagram />);
    const list = screen.getByRole("list", { name: flowDiagram.listLabel });
    expect(list.tagName).toBe("OL");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(flowSteps.length);
    flowSteps.forEach((step, i) => {
      expect(within(items[i]!).getByRole("heading", { level: 3 }).textContent).toBe(`Step ${i + 1}: ${step.title}`);
      expect(items[i]!.textContent).toContain(step.summary);
      for (const actor of flowDiagram.actors[step.id]!) expect(items[i]!.textContent).toContain(actor);
    });
  });

  it("says who does every step", () => {
    for (const step of flowSteps) expect(flowDiagram.actors[step.id]?.length, step.id).toBeGreaterThan(0);
  });

  it("follows the list: a step added there shows up", () => {
    const extra: FlowStep = { id: "extra", title: "An extra step", summary: "Added in a test copy.", details: [] };
    render(<FlowDiagram steps={[...flowSteps, extra]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(flowSteps.length + 1);
    expect(screen.getByText("An extra step")).toBeTruthy();
  });

  it("is in the server render (no JS needed), connectors hidden from screen readers", () => {
    const doc = new DOMParser().parseFromString(renderToStaticMarkup(<FlowDiagram />), "text/html");
    expect(doc.querySelectorAll("ol[data-flow-diagram] > li")).toHaveLength(flowSteps.length);
    for (const span of doc.querySelectorAll("li > span.absolute")) expect(span.getAttribute("aria-hidden")).toBe("true");
  });
});

/** Width and height of a WebP file (lossy VP8, lossless VP8L or extended VP8X). */
function webpSize(file: string): { width: number; height: number } {
  const b = readFileSync(file);
  expect(b.toString("ascii", 0, 4)).toBe("RIFF");
  expect(b.toString("ascii", 8, 12)).toBe("WEBP");
  const chunk = b.toString("ascii", 12, 16);
  if (chunk === "VP8 ") return { width: b.readUInt16LE(26) & 0x3fff, height: b.readUInt16LE(28) & 0x3fff };
  if (chunk === "VP8L") {
    const bits = b.readUInt32LE(21);
    return { width: (bits & 0x3fff) + 1, height: ((bits >> 14) & 0x3fff) + 1 };
  }
  expect(chunk).toBe("VP8X");
  return { width: b.readUIntLE(24, 3) + 1, height: b.readUIntLE(27, 3) + 1 };
}

describe("the product screenshots (a recorded example run)", () => {
  const shots = [runScreenshot.desktop, runScreenshot.mobile];

  it("are files in web/public, of the size the page declares, and small", () => {
    for (const shot of shots) {
      const file = resolve(process.cwd(), "public", shot.src.replace(/^\//, ""));
      expect(existsSync(file), file).toBe(true);
      expect(webpSize(file)).toEqual({ width: shot.width, height: shot.height });
      expect(readFileSync(file).length).toBeLessThan(200 * 1024);
    }
  });

  it("have alt text that names what they show, and the visible label 'Recorded example run'", () => {
    const { container } = render(<RunScreenshot />);
    const imgs = [...container.querySelectorAll("img")];
    expect(imgs.map((img) => img.getAttribute("alt"))).toEqual(shots.map((s) => s.alt));
    for (const shot of shots) {
      expect(shot.alt.length).toBeGreaterThan(80);
      expect(shot.alt).toMatch(/paid 1/);
    }
    const caption = container.querySelector("figcaption")!;
    expect(within(caption).getByText("Recorded example run")).toBeTruthy();
    expect(caption.textContent).toContain(runScreenshot.explanation);
    expect(runScreenshot.label).toBe("Recorded example run");
  });

  it("is the hero's figure, in the server render with its label", () => {
    const html = renderToStaticMarkup(
      <SiteLayout>
        <HomePage />
      </SiteLayout>,
    );
    const doc = new DOMParser().parseFromString(html, "text/html");
    const figure = doc.querySelector('[data-hero] [data-layer="figure"] [data-screenshot]')!;
    expect(figure).not.toBeNull();
    expect(figure.querySelectorAll("img[alt]")).toHaveLength(2);
    expect(figure.querySelector("figcaption")?.textContent).toContain("Recorded example run");
  });
});
