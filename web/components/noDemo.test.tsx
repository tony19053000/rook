// @vitest-environment jsdom
// ROOK-048: people never see the word "demo" in the web app. The views are rendered with fixtures and only what a
// person sees or hears is checked (text plus aria-label, alt, title and placeholder), not data attributes or
// API values such as `kind: "demo"`.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ErrorCard } from "./ErrorCard";
import { GithubSetupView } from "./GithubSetupView";
import { HomeView } from "./HomeView";
import { RepositoriesView } from "./SimpleViews";
import { RulesCard } from "./cards/RulesCard";
import { RunActionsContext, type RunActions } from "./cards/ui";
import { ApiError, type RepoOption } from "@/lib/api";
import { NO_DEMO_WORD } from "@/lib/copyRules";
import { minishopRun } from "@/lib/fixtures/minishop";
import { cliHint, errorView, newRunBody } from "@/lib/pages";
import { reduceEvents, type QuestionItem, type RulesItem } from "@/lib/runStore";
import { GUEST, type Session } from "@/lib/session";

const EXAMPLE: RepoOption = { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app", private: false, language: "Node.js" };
const GH: RepoOption = { kind: "github", ref: "aayush/billing", name: "aayush/billing", private: true, language: "Python" };
const USER_NO_GH: Session = { kind: "user", name: "Aayush", email: "a@example.com", githubConnected: false };
const USER: Session = { ...USER_NO_GH, githubConnected: true };
const noRuns = { runs: [], loading: false, error: null };
const fakeApi = { createRun: async () => ({ run_id: "r_new" }), answer: async () => ({ ok: true }), chat: async () => ({ ok: true }) };
const repos = (list: RepoOption[]) => ({ repos: list, loading: false, error: null, retry: () => {} });
const OLD_LIMIT = "Demo limit reached for today. Install the CLI to run on your own repos: uv tool install git+https://github.com/tony19053000/rook";
const NEW_LIMIT = "Guest limit reached for today. Install the CLI to run on your own repos: uv tool install git+https://github.com/tony19053000/rook";

/** What a person sees or hears in the markup. */
function visibleText(node: React.ReactElement): string {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(node);
  const attrs = [...root.querySelectorAll("[aria-label], [alt], [title], [placeholder]")].flatMap((el) =>
    ["aria-label", "alt", "title", "placeholder"].map((name) => el.getAttribute(name) ?? ""),
  );
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: string[] = [];
  for (let n = walker.nextNode(); n !== null; n = walker.nextNode()) texts.push(n.textContent ?? "");
  return [...texts, ...attrs].join("\n");
}

function expectNoDemo(text: string) {
  expect(text.match(new RegExp(NO_DEMO_WORD.pattern.source, "gi")) ?? [], text).toEqual([]);
}

/** The recorded run, stopped at the rules question, with one rule flagged as the featured one. */
function featuredRules() {
  const i = minishopRun.findIndex((e) => e.type === "question.answered");
  const state = reduceEvents(minishopRun.slice(0, i));
  const rules = state.items.find((x): x is RulesItem => x.kind === "rules")!;
  const q = state.items.find((x): x is QuestionItem => x.kind === "question")!;
  const payload = q.payload as { rules: Array<Record<string, unknown>> };
  const question = { ...q, payload: { rules: payload.rules.map((r) => ({ ...r, featured: r.id === "refunded_total_le_paid" })) } };
  return { rules, question };
}

describe('no "demo" in the web app (ROOK-048)', () => {
  it("the check itself catches the word in visible text but not in attributes", () => {
    expect(() => expectNoDemo(visibleText(<button>Try the demo</button>))).toThrow();
    expectNoDemo(visibleText(<button data-try-demo="">Try Rook</button>));
  });

  it("home, for a guest, a user without GitHub and a user with GitHub", () => {
    for (const session of [GUEST, USER_NO_GH, USER]) {
      for (const list of [[], [EXAMPLE], [GH, EXAMPLE]]) {
        expectNoDemo(visibleText(<HomeView api={fakeApi} session={session} runs={noRuns} repos={repos(list)} navigate={() => {}} />));
      }
    }
    expectNoDemo(visibleText(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([EXAMPLE])} navigate={() => {}} defaultSelected={EXAMPLE} />));
  });

  it("repositories, with and without example repos", () => {
    for (const session of [GUEST, USER_NO_GH, USER]) {
      for (const list of [[], [EXAMPLE], [GH, EXAMPLE]]) {
        const out = visibleText(
          <RepositoriesView session={session} runs={noRuns} repos={list} loading={false} error={null} connectGithub={async () => null} />,
        );
        expectNoDemo(out);
      }
    }
    const empty = visibleText(<RepositoriesView session={GUEST} runs={noRuns} repos={[]} loading={false} error={null} />);
    expect(empty).toContain("No example repositories on this server.");
  });

  it("the GitHub setup page", () => {
    for (const status of [{ kind: "working" }, { kind: "done" }, { kind: "error", message: "nope" }] as const) {
      expectNoDemo(visibleText(<GithubSetupView session={USER} runs={noRuns} status={status} connectGithub={async () => null} />));
    }
  });

  it("the rules card for a guest: the featured-rule pill and the countdown", () => {
    const { rules, question } = featuredRules();
    const actions: RunActions = { answer: async () => ({ status: "sent" }), guest: true, autoSeconds: 6 };
    const out = visibleText(
      <RunActionsContext.Provider value={actions}>
        <RulesCard item={rules} question={question} />
      </RunActionsContext.Provider>,
    );
    expect(out).toContain("Featured rule");
    expect(out).toContain("in 6s");
    expectNoDemo(out);
  });

  it("the guest-limit card, for the old and the new server message", () => {
    for (const message of [OLD_LIMIT, NEW_LIMIT]) {
      const view = errorView(new ApiError(429, message, 3600), "create");
      expect(view.kind).toBe("limit");
      const out = visibleText(<ErrorCard view={view} onRetry={() => {}} />);
      expect(out).toContain("Guest limit reached for today");
      expectNoDemo(out);
    }
  });

  it("the other messages the app writes itself", () => {
    expectNoDemo(cliHint("alice/shop"));
    expectNoDemo(JSON.stringify(newRunBody({ kind: "github", ref: "alice/shop" }, "find bugs", false)));
    for (const status of [503, 501, 401, 403, 404, 422, 500]) {
      for (const action of ["create", "run"] as const) {
        const view = errorView(new ApiError(status, `HTTP ${status}`), action);
        expectNoDemo(`${view.title}\n${view.message}`);
      }
    }
  });
});
