// @vitest-environment jsdom
// ROOK-055: the docs guides. Each renders with one h1, a table of contents whose anchors resolve, the docs
// navigation and previous/next links; what they state is compared with the repo's own files (the example
// rook.yaml, action.yml, pyproject.toml, the evaluator, the recorded run).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GUIDE_PAGES } from "./testPages";
import SiteLayout from "@/app/(site)/layout";
import sitemap from "@/app/sitemap";
import { actionInputs, actionOutputs, actionWorkflow } from "@/content/docsGithubAction";
import { docsNav, guideNeighbours, guides } from "@/content/docsGuides";
import { PACKAGE_NAME, PYTHON_MINIMUM } from "@/content/docsInstall";
import type { DocBlock, DocGuide } from "@/content/docsModel";
import { CHECK_FUNCTIONS, CHECK_MAX_CHARS } from "@/content/docsRules";
import { runScreenshot } from "@/content/home";
import { CONTACT_EMAIL, cta, footerColumns, INSTALL_COMMAND, site, SITE_URL } from "@/content/site";
import { stepText } from "@/lib/cardText";
import { copyViolations } from "@/lib/copyRules";
import raw from "@/lib/fixtures/minishop-run.json";
import { MINISHOP_ROOK_YAML, MINISHOP_ROOK_YAML_PATH } from "@/lib/fixtures/minishopRookYaml";
import { RECORDED_LINES, RUN_DATA_ATTR, scannableText } from "@/lib/recordedData";
import { isRepoFile, REPO_FILE_ATTR } from "@/lib/verbatim";

const router = { replace: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

afterEach(cleanup);

const REPO = resolve(process.cwd(), "..");
const repoFile = (path: string) => readFileSync(resolve(REPO, path), "utf8");
const inSite = (page: ReactElement) => render(<SiteLayout>{page}</SiteLayout>);
const guideAt = (path: string): DocGuide => guides.find((g) => g.path === path)!;
const pageAt = (path: string): ReactElement => GUIDE_PAGES.find(([p]) => p === path)![1]();
const blocksOf = (guide: DocGuide): DocBlock[] => guide.sections.flatMap((s) => [...s.blocks, ...(s.subsections ?? []).flatMap((sub) => sub.blocks)]);
const mainText = (path: string): string => inSite(pageAt(path)).container.querySelector("main")!.textContent ?? "";

describe("the guides list (06 §1)", () => {
  it("is the six guides of 06 §1, in reading order, each with a page", () => {
    expect(guides.map((g) => g.path)).toEqual([
      "/docs/getting-started",
      "/docs/install",
      "/docs/rules",
      "/docs/counterexamples",
      "/docs/github-action",
      "/docs/data",
    ]);
    expect(GUIDE_PAGES.map(([path]) => path)).toEqual(guides.map((g) => g.path));
    expect(docsNav.map((l) => l.href)).toEqual(["/docs", ...guides.map((g) => g.path)]);
  });

  it("the footer's Docs column and the docs CTA point at the guides, under their own names (06 §8)", () => {
    const column = footerColumns.find((c) => c.heading === "Docs")!;
    expect(column.links.map((l) => l.label)).toEqual(["Getting started", "Install", "Rules", "GitHub Action", "Data and IBM Bob"]);
    for (const link of column.links) expect(guides.find((g) => g.path === link.href)?.navLabel, link.href).toBe(link.label);
    expect(cta.docs).toEqual({ label: "Read the docs", href: "/docs/getting-started" });
  });

  it("the sitemap lists every guide", () => {
    const urls = sitemap().map((entry) => entry.url);
    for (const guide of guides) expect(urls).toContain(`${SITE_URL}${guide.path}`);
  });
});

describe.each(GUIDE_PAGES)("guide %s (06 §5.10)", (path, page) => {
  const guide = guideAt(path);

  it("has its one h1, inside the article in main", () => {
    const { container } = inSite(page());
    const h1s = container.querySelectorAll("h1");
    expect(h1s).toHaveLength(1);
    expect(h1s[0]!.textContent).toBe(guide.heading);
    expect(h1s[0]!.closest("main article")).not.toBeNull();
    expect(container.querySelector("main")!.textContent).toContain(guide.lead);
  });

  it("is long-form: every section is an h2, every subsection an h3", () => {
    const { container } = inSite(page());
    const article = container.querySelector("main article") as HTMLElement;
    expect(guide.sections.length).toBeGreaterThanOrEqual(5);
    const h2s = [...article.querySelectorAll("h2")].map((h) => h.textContent);
    expect(h2s).toEqual(guide.sections.map((s) => s.title));
    for (const section of guide.sections) {
      const region = within(article).getByRole("region", { name: section.title });
      expect(region.id).toBe(section.id);
      for (const sub of section.subsections ?? []) {
        expect(within(region).getByRole("heading", { level: 3, name: sub.title }).parentElement?.id).toBe(sub.id);
      }
    }
  });

  it("has a table of contents whose anchors all resolve to ids on the page, in order", () => {
    const { container } = inSite(page());
    const toc = screen.getByRole("navigation", { name: "On this page" });
    const hrefs = within(toc).getAllByRole("link").map((a) => a.getAttribute("href")!);
    const expected = guide.sections.flatMap((s) => [s.id, ...(s.subsections ?? []).map((sub) => sub.id)]);
    expect(hrefs).toEqual(expected.map((id) => `#${id}`));
    for (const id of expected) expect(container.querySelector(`main [id="${id}"]`), `#${id}`).not.toBeNull();
    const ids = [...container.querySelectorAll("[id]")].map((el) => el.id);
    expect(ids.filter((id, i) => ids.indexOf(id) !== i), "duplicate ids").toEqual([]);
  });

  it("the table of contents and every section are in the server render (no JS needed)", () => {
    const doc = new DOMParser().parseFromString(renderToStaticMarkup(page()), "text/html");
    const links = [...doc.querySelectorAll('[data-toc] a[href^="#"]')];
    expect(links.length).toBeGreaterThanOrEqual(guide.sections.length);
    for (const a of links) expect(doc.getElementById(a.getAttribute("href")!.slice(1)), a.getAttribute("href")!).not.toBeNull();
    expect(doc.querySelectorAll("script")).toHaveLength(0);
  });

  it("has the docs navigation with this page marked current, and previous/next links", () => {
    inSite(page());
    const nav = screen.getByRole("navigation", { name: "Docs" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(docsNav.map((l) => l.href));
    expect(links.filter((a) => a.getAttribute("aria-current") === "page").map((a) => a.getAttribute("href"))).toEqual([path]);

    const { previous, next } = guideNeighbours(path);
    const pager = screen.getByRole("navigation", { name: "Previous and next guide" });
    expect(pager.querySelector('a[rel="prev"]')?.getAttribute("href")).toBe(previous?.href);
    expect(pager.querySelector('a[rel="next"]')?.getAttribute("href") ?? null).toBe(next?.href ?? null);
    const i = docsNav.findIndex((l) => l.href === path);
    expect(previous?.href).toBe(docsNav[i - 1]!.href);
    expect(next?.href).toBe(docsNav[i + 1]?.href);
  });

  it("fills every slot it names, and its copy has no placeholder left to fill", () => {
    const { container } = inSite(page());
    const slots = blocksOf(guide).flatMap((b) => (b.kind === "slot" ? [b.name] : []));
    for (const name of slots) expect(container.querySelector(`[data-doc-slot="${name}"]`)?.textContent?.length, name).toBeGreaterThan(100);
    expect(container.querySelectorAll("[data-doc-slot]")).toHaveLength(slots.length);
    expect(scannableText(container)).not.toMatch(/\bTODO\b|\bTBD\b|lorem ipsum|coming soon/i);
  });
});

describe("/docs/rules: the example is a real file of the repo", () => {
  const file = repoFile(MINISHOP_ROOK_YAML_PATH);

  it("the copy in web/ equals tests/fixtures/minishop/rook.yaml, byte for byte", () => {
    expect(MINISHOP_ROOK_YAML_PATH).toBe("tests/fixtures/minishop/rook.yaml");
    expect(MINISHOP_ROOK_YAML).toBe(file);
    expect(file).toContain("id: refund_le_paid");
  });

  it("the page shows that file whole, labelled with its path", () => {
    const { container } = inSite(pageAt("/docs/rules"));
    const shown = container.querySelectorAll(`[${REPO_FILE_ATTR}]`);
    expect(shown).toHaveLength(1);
    expect(shown[0]!.textContent).toBe(file);
    expect(shown[0]!.closest("figure")?.querySelector("figcaption")?.textContent).toContain(MINISHOP_ROOK_YAML_PATH);
    expect(shown[0]!.closest("[data-doc-slot]")?.getAttribute("data-doc-slot")).toBe("rook-yaml");
  });

  it("the file is exempt from the copy rules by identity only: a changed or padded copy is scanned", () => {
    expect(copyViolations(file)).toEqual(expect.arrayContaining(["customers", "the word demo"]));
    const { container } = inSite(pageAt("/docs/rules"));
    expect(copyViolations(scannableText(container))).toEqual([]);
    cleanup();
    for (const text of [`${file}our customers love it\n`, file.replace("version: 1", "version: 2"), "Trusted by customers"]) {
      const { container: c, unmount } = render(<code {...{ [REPO_FILE_ATTR]: "" }}>{text}</code>);
      expect(isRepoFile(c.querySelector("code")!), text.slice(-30)).toBe(false);
      expect(copyViolations(scannableText(c))).toContain("customers");
      unmount();
    }
    const unmarked = render(<code>{file}</code>);
    expect(copyViolations(scannableText(unmarked.container))).toContain("customers");
  });

  it("describes the evaluator as the code has it: the allowed calls and the length cap", () => {
    const expr = repoFile("src/rook/model/expr.py");
    const block = expr.match(/_FUNCTIONS: dict\[[^\]]*\]\] = \{([\s\S]*?)\n\}/)?.[1] ?? "";
    const allowed = [...block.matchAll(/"(\w+)":/g)].map((m) => m[1]!);
    expect(allowed.length).toBeGreaterThanOrEqual(8);
    expect([...CHECK_FUNCTIONS]).toEqual(allowed);
    expect(repoFile("src/rook/model/schema.py")).toContain(`MAX_CHECK_LEN = ${CHECK_MAX_CHARS}`);
    expect(expr).toContain(`MAX_SOURCE_LENGTH = ${CHECK_MAX_CHARS}`);
    const text = mainText("/docs/rules");
    expect(text).toContain(CHECK_FUNCTIONS.join(", "));
    expect(text).toMatch(/Python's own eval and exec are never used/);
    expect(text).toContain("already_broken");
  });

  it("names the rule kinds and statuses the schema allows", () => {
    const schema = repoFile("src/rook/model/schema.py");
    expect(schema).toContain('kind: Literal["state", "response"]');
    expect(schema).toContain('status: Literal["proposed", "approved", "rejected"] = "proposed"');
    const text = mainText("/docs/rules");
    for (const word of ["kind: state", "kind: response", "proposed, approved or rejected", "fresh_entities"]) expect(text).toContain(word);
  });
});

describe("/docs/counterexamples: the recorded refund case", () => {
  interface RawEvent {
    type: string;
    data: Record<string, unknown>;
  }
  const saved = (raw as RawEvent[]).filter((e) => e.type === "counterexample.saved").at(-1)!.data;

  it("shows the recorded run's steps, values and replay count, labelled as a recorded example run", () => {
    const { container } = inSite(pageAt("/docs/counterexamples"));
    const story = container.querySelector('[data-doc-slot="refund-story"]') as HTMLElement;
    const steps = within(story.querySelector("[data-story-steps]") as HTMLElement).getAllByRole("listitem");
    expect(steps.map((li) => li.querySelector(`[${RUN_DATA_ATTR}]`)?.textContent)).toEqual((saved.steps as { actor: string; action: string }[]).map(stepText));
    expect(story.querySelector("[data-story-replayed]")?.textContent).toBe(saved.reproduced);
    expect(story.textContent).toContain(String(saved.expected));
    expect(within(story).getByText(runScreenshot.label)).toBeTruthy();
    expect(runScreenshot.label).toBe("Recorded example run");
  });

  it("marks only verbatim lines of the recording as run data, and the page passes the copy rules", () => {
    const { container } = inSite(pageAt("/docs/counterexamples"));
    const marked = [...container.querySelectorAll(`[${RUN_DATA_ATTR}]`)];
    expect(marked.length).toBeGreaterThanOrEqual(6);
    for (const node of marked) expect(RECORDED_LINES.has(node.textContent ?? ""), node.textContent ?? "").toBe(true);
    expect(copyViolations(scannableText(container))).toEqual([]);
  });

  it("states the defaults the code has: 10 replays, 20,000 sequences or 120 seconds, and verify's own", () => {
    expect(repoFile("src/rook/engine/replayer.py")).toContain("DEFAULT_REPLAYS = 10");
    const verifier = repoFile("src/rook/engine/verifier.py");
    expect(verifier).toContain("budget_sequences: int = 20_000");
    expect(verifier).toContain("budget_seconds: float = 120.0");
    const cli = repoFile("src/rook/cli/main.py");
    expect(cli).toMatch(/"--sequences", min=1, help="Fresh search budget in sequences\."\)\] = 2_000/);
    expect(cli).toMatch(/"--seconds", min=1, help="Fresh search budget in seconds\."\)\] = 60\.0/);
    const text = mainText("/docs/counterexamples");
    expect(text).toContain("10 times by default");
    expect(text).toContain("20,000 sequences or 120 seconds");
    expect(text).toContain("2,000 sequences or 60 seconds");
  });
});

describe("/docs/github-action: from action.yml", () => {
  const action = repoFile("action.yml");
  const part = (from: string, to: string) => action.slice(action.indexOf(`\n${from}:\n`), action.indexOf(`\n${to}:\n`));
  const keys = (text: string) => [...text.matchAll(/^ {2}([a-z-]+):$/gm)].map((m) => m[1]!);

  it("lists exactly the action's inputs and outputs, in order", () => {
    expect(actionInputs.map((i) => i.term)).toEqual(keys(part("inputs", "outputs")));
    expect(actionOutputs.map((o) => o.term)).toEqual(keys(part("outputs", "runs")));
    expect(actionInputs.length).toBeGreaterThanOrEqual(12);
  });

  it("states the defaults action.yml has", () => {
    const inputs = part("inputs", "outputs");
    const defaultOf = (name: string) => inputs.match(new RegExp(`^ {2}${name}:\\n(?: {4}.*\\n)*? {4}default: (.*)$`, "m"))?.[1]?.replace(/^"|"$/g, "");
    const text = (name: string) => actionInputs.find((i) => i.term === name)!.text;
    expect(defaultOf("bob-mode")).toBe("replay");
    expect(text("bob-mode")).toMatch(/^replay \(the default\)/);
    for (const name of ["request", "budget", "seconds", "report-dir"]) expect(text(name), name).toContain(`Default: ${defaultOf(name)}.`);
    for (const name of ["auto", "comment"]) {
      expect(defaultOf(name)).toBe("true");
      expect(text(name)).toMatch(/^true \(the default\)/);
    }
  });

  it("the workflow is safe to copy: pull_request only, least permissions, pins by commit SHA, the key from a secret", () => {
    expect(actionWorkflow).toMatch(/^on:\n {2}pull_request:$/m);
    expect(actionWorkflow).not.toContain("pull_request_target");
    expect(actionWorkflow).toContain("permissions:\n  contents: read\n  pull-requests: write");
    const uses = [...actionWorkflow.matchAll(/uses: (\S+)/g)].map((m) => m[1]!);
    expect(uses).toHaveLength(2);
    expect(uses[0]).toMatch(/^actions\/checkout@[0-9a-f]{40}$/);
    expect(uses[1]).toBe("tony19053000/rook@<full-commit-sha>");
    expect(actionWorkflow).toContain("bob-api-key: ${{ secrets.BOB_API_KEY }}");
    // Live mode stops without bob-package (action.yml "Install Bob Shell"), so the example names it.
    expect(action).toContain("bob-mode live needs bob-package");
    expect(actionWorkflow).toContain("bob-mode: live");
    expect(actionWorkflow).toMatch(/bob-package: <[a-z-]+>/);
    const { container } = inSite(pageAt("/docs/github-action"));
    expect(container.querySelector("#workflow pre")?.textContent).toBe(actionWorkflow);
  });

  it("says what the action runs and what the exit codes mean, as action.yml and the CLI have them", () => {
    expect(action).toContain("args=(run --ci ");
    expect(action).toContain('if [ "$AUTO" = "true" ]; then args+=(--auto); fi');
    const ci = repoFile("src/rook/cli/ci.py");
    expect(ci).toContain("EXIT_HELD, EXIT_BROKEN, EXIT_ERROR = 0, 1, 2");
    const text = mainText("/docs/github-action");
    expect(text).toContain("rook run --ci --auto");
    expect(text).toMatch(/pull_request,\s*never pull_request_target/);
    expect(text).toContain("An approved rule is broken");
    expect(text).toContain("The run did not finish");
  });

  it("states its limitations plainly", () => {
    const { container } = inSite(pageAt("/docs/github-action"));
    const limits = container.querySelector("#limitations")?.textContent ?? "";
    expect(limits).toMatch(/has not yet been run on a GitHub-hosted runner/);
    expect(limits).toMatch(/Roook does not host or redistribute Bob Shell/);
    expect(limits).toMatch(/Replay mode only fits code that has not changed/);
    const prs = container.querySelector("#fix-pull-requests")?.textContent ?? "";
    expect(prs).toMatch(/has not yet been run from start to finish against GitHub/);
    expect(prs).toMatch(/Hosted runs of your own repos are turned off/);
    expect(prs).toMatch(/never pushes to your default branch/);
  });
});

describe("/docs/install and /docs/getting-started: from pyproject.toml", () => {
  const pyproject = repoFile("pyproject.toml");

  it("names the package and the Python version pyproject.toml has", () => {
    expect(pyproject).toContain(`name = "${PACKAGE_NAME}"`);
    expect(pyproject).toContain(`requires-python = ">=${PYTHON_MINIMUM}"`);
    expect(pyproject).toContain('rook = "rook.cli.main:app"');
    expect(pyproject).toContain('rook-pr-comment = "rook.github.pr_comment:main"');
    const text = mainText("/docs/install");
    expect(text).toContain(`${PYTHON_MINIMUM} or newer`);
    expect(text).toContain(`uv tool upgrade ${PACKAGE_NAME}`);
    expect(text).toContain(`uv tool uninstall ${PACKAGE_NAME}`);
    expect(text).toContain("rook-pr-comment");
  });

  it("both show the one install command, and say Roook is not on PyPI", () => {
    expect(INSTALL_COMMAND).toBe("uv tool install git+https://github.com/tony19053000/rook");
    for (const path of ["/docs/install", "/docs/getting-started"]) {
      const text = mainText(path);
      expect(text, path).toContain(INSTALL_COMMAND);
      expect(text, path).toMatch(/not on PyPI yet/);
      cleanup();
    }
  });

  it("never shows a real key: only the <your-key> stand-in", () => {
    for (const [path] of GUIDE_PAGES) {
      // One text node per line: textContent would glue the next block's text to the value.
      const text = scannableText(inSite(pageAt(path)).container);
      expect(text, path).not.toMatch(/bob_prod_|gh[ps]_[A-Za-z0-9]|eyJ[A-Za-z0-9_-]{8,}|-----BEGIN/);
      for (const m of text.matchAll(/BOB_API_KEY=(\S*)/g)) expect(m[1], path).toBe("<your-key>");
      cleanup();
    }
  });

  it("states the limitations of 06 §4 and where Bob Shell is looked for", () => {
    const { container } = inSite(pageAt("/docs/install"));
    const limits = container.querySelector("#limitations")?.textContent ?? "";
    for (const fact of ["HTTP APIs only", "Not on PyPI", "your own IBM Bob key", "Tested on Linux only", "hosted runs of your own repos are turned off"]) expect(limits).toContain(fact);
    expect(container.querySelector("#troubleshooting dl")?.querySelectorAll("dt").length).toBeGreaterThanOrEqual(8);
    const bob = repoFile("src/rook/agents/bob.py");
    expect(bob).toContain('os.environ.get("ROOK_BOB_BIN")');
    expect(bob).toContain('NODE24_BIN = Path.home() / ".nvm" / "versions" / "node" / "v24.21.0" / "bin"');
    expect(container.querySelector("#ibm-bob")?.textContent).toContain("~/.nvm/versions/node/v24.21.0/bin/bob");
  });

  it("getting started covers the site example, the CLI, the six steps and where results land", () => {
    const { container } = inSite(pageAt("/docs/getting-started"));
    for (const id of ["what-you-need", "try-on-the-site", "install", "first-run", "what-you-see", "where-results-land"]) expect(container.querySelector(`#${id}`), id).not.toBeNull();
    expect(container.querySelector('#try-on-the-site a[href="/app"]')?.textContent).toBe("Try Roook");
    expect(container.querySelectorAll("#what-you-see dt")).toHaveLength(6);
    const results = container.querySelector("#where-results-land")?.textContent ?? "";
    for (const item of ["rook/rook.yaml", "rook/counterexamples/cx_001.json", "regression test", "rook/fix-", "~/.rook/workspaces/"]) expect(results).toContain(item);
    expect(repoFile("src/rook/core/workspace.py")).toContain('DEFAULT_ROOT = Path.home() / ".rook" / "workspaces"');
  });
});

describe("/docs/data: what goes to IBM Bob", () => {
  it("says recorded runs send nothing, live runs send repo content, and the site never asks for the key", () => {
    const text = mainText("/docs/data");
    expect(text).toMatch(/A Recorded example run on this site sends nothing to IBM Bob/);
    expect(text).toMatch(/A Live run, with the CLI on your machine and your own key, sends repo content and run data to IBM Bob as prompts/);
    expect(text).toMatch(/Your IBM Bob key stays on your machine\. The hosted site never asks for it/);
    expect(text).toMatch(/Roook does not scan your files for secrets/);
  });

  it("states the limits the code has for what a prompt carries, and what the copy leaves out", () => {
    const understand = repoFile("src/rook/agents/understand.py");
    for (const line of ["DIGEST_MAX_FILES = 400", "FILE_MAX_CHARS = 20_000", "FILES_MAX_TOTAL = 120_000"]) expect(understand).toContain(line);
    expect(repoFile("src/rook/agents/diagnose.py")).toContain("RELATED_MAX_FILES = 4");
    const workspace = repoFile("src/rook/core/workspace.py");
    for (const name of [".git", ".venv", "venv", "node_modules"]) expect(workspace.match(/COPY_IGNORE = \(([\s\S]*?)\)/)?.[1]).toContain(`"${name}"`);
    const text = mainText("/docs/data");
    for (const fact of ["up to 400 files", "20,000 characters", "120,000 characters", "up to 4 source files", ".git, .venv, venv, node_modules"]) expect(text).toContain(fact);
  });

  it("covers the key, the GitHub App's permissions, retention and deletion", () => {
    const { container } = inSite(pageAt("/docs/data"));
    const github = container.querySelector("#github")?.textContent ?? "";
    for (const permission of ["Contents: read and write.", "Pull requests: read and write.", "Metadata: read."]) expect(github).toContain(permission);
    const hosted = container.querySelector("#hosted") as HTMLElement;
    expect(hosted.textContent).toMatch(/Runs older than 30 days are deleted automatically/);
    expect(hosted.textContent).toMatch(/older than 2 days/);
    // ROOK-052 built the buttons: the guide names them as the app labels them, and no longer says "ask by email".
    expect(repoFile("web/components/RunPage.tsx")).toContain('label="Delete run"');
    expect(repoFile("web/components/Sidebar.tsx")).toContain('label="Delete my data"');
    expect(hosted.textContent).toMatch(/use Delete run\. Its events and counterexamples go with it/);
    expect(hosted.textContent).toMatch(/with Delete my data in the account menu/);
    expect(hosted.textContent).not.toMatch(/not in the web app yet/);
    expect(hosted.textContent).toMatch(/The Roook server cannot delete it, so it is deleted on request by email/);
    const mail = new URL(hosted.querySelector('a[href^="mailto:"]')!.getAttribute("href")!);
    expect(mail.pathname).toBe(CONTACT_EMAIL);
    expect(mail.searchParams.get("subject")).toBe("Roook: privacy request");
    expect(container.querySelector('#key a[href="/docs/install#ibm-bob"]')).not.toBeNull();
  });
});

describe("README.md is in line with the site (ROOK-055)", () => {
  const readme = repoFile("README.md");

  it("opens with the site's one-liner and positions Roook as early access, open source, built on IBM Bob", () => {
    expect(readme).toContain(`**${site.oneLiner}**`);
    expect(readme).toMatch(/Early access, open source \(MIT\)\. Built on IBM Bob\./);
    expect(readme.match(/hackathon/gi) ?? []).toHaveLength(1);
    expect(readme).toContain("Roook started at the IBM Bob 2.0 Hackathon in September 2026.");
  });

  it("has the same install command and workflow, and links every guide on the site", () => {
    expect(readme).toContain(INSTALL_COMMAND);
    expect(readme).toContain(actionWorkflow);
    for (const guide of guides) expect(readme, guide.path).toContain(`(${SITE_URL}${guide.path})`);
    expect(readme).toContain(`${SITE_URL}/app`);
  });

  it("makes no stale claim: hosted own-repo runs are off, nothing is promised on PyPI, no unfilled links", () => {
    expect(readme).toMatch(/hosted runs of your own repos are turned off/);
    expect(readme).not.toMatch(/can also run their own GitHub repo on the hosted server|When the server enables it/);
    expect(readme).not.toMatch(/Docker socket/i);
    expect(readme).not.toMatch(/coming soon|<VIDEO_URL>|<DECK_URL>|Try the demo/i);
    expect(readme).not.toMatch(/\bdemos?\b/i);
    expect(readme).toMatch(/Not on PyPI yet/);
    expect(readme).toMatch(/has not yet been run on a GitHub-hosted runner/);
  });
});
