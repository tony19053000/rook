import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { HomeView } from "./HomeView";
import { RepoPicker } from "./RepoPicker";
import { RunPageView } from "./RunPage";
import { RunsList } from "./RunsList";
import { Sidebar } from "./Sidebar";
import { CounterexamplesView, LoginView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { ApiError, type RepoOption, type RunSummary } from "@/lib/api";
import { minishopRun } from "@/lib/fixtures/minishop";
import { CLI_INSTALL, errorView, pickerGroups } from "@/lib/pages";
import { initialRunState, reduceEvents } from "@/lib/runStore";
import { GUEST, type Session } from "@/lib/session";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);

const DEMO: RepoOption = { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app", private: false, language: "Node.js" };
const GH: RepoOption = { kind: "github", ref: "aayush/billing", name: "aayush/billing", private: true, language: "Python" };
const HOSTILE: RepoOption = { kind: "demo", ref: "evil", name: "<img src=x onerror=alert(1)>\x1b[2J", private: false, language: "<b>Go</b>" };
const USER_NO_GH: Session = { kind: "user", name: "Aayush", email: "a@example.com", githubConnected: false };

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  id: "r_1",
  repo: { kind: "demo", ref: DEMO.ref, name: "shop-app" },
  status: "done",
  created_at: "2026-09-26T09:00:00Z",
  finished_at: null,
  headline: "find bugs in refunds",
  result: "broken",
  coins: 0.1,
  last_seq: 10,
  ...patch,
});
const noRuns = { runs: [], loading: false, error: null };
const fakeApi = { createRun: async () => ({ run_id: "r_new" }), answer: async () => ({ ok: true }), chat: async () => ({ ok: true }) };
const repos = (list: RepoOption[], patch: Partial<{ loading: boolean; error: unknown }> = {}) => ({ repos: list, loading: false, error: null, retry: () => {}, ...patch });

describe("home (04 §3.2 /)", () => {
  const out = html(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} />);

  it("shows the greeting, the composer with the picker and the auto-approve toggle", () => {
    expect(out).toContain("What should we try to break today?");
    expect(out).toContain("Select repository…");
    expect(out).toContain('aria-haspopup="listbox"');
    expect(out).toContain("Auto-approve: off");
    expect(out).toContain("Docker sandbox");
  });

  it("offers the guest demo", () => {
    expect(out).toContain("data-guest");
    expect(out).toContain("Try the demo");
    expect(out).toMatch(/Sign in<\/a>/);
  });

  it("shows the empty recents", () => {
    expect(out).toContain("No runs yet. Pick a repository to start.");
  });

  it("a repos failure shows an error card with a retry", () => {
    const failed = html(
      <HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([], { error: new TypeError("offline") })} navigate={() => {}} />,
    );
    expect(failed).toContain('data-card="error"');
    expect(failed).toContain("Couldn&#x27;t load the repositories");
    expect(failed).toContain("Try again");
  });
});

describe("repo picker (04 §3.3)", () => {
  it("a guest sees only 'Demo repositories', with private/public and the language", () => {
    const out = html(<RepoPicker groups={pickerGroups([GH, DEMO], GUEST)} selected={null} onSelect={() => {}} defaultOpen />);
    expect(out).toContain('role="listbox"');
    expect(out).toContain("Demo repositories");
    expect(out).not.toContain("Your GitHub repositories");
    expect(out).not.toContain("aayush/billing");
    expect(out).toContain("shop-app");
    expect(out).toContain("public · Node.js");
    expect(out.match(/role="option"/g)).toHaveLength(1);
  });

  it("a signed-in user without GitHub gets 'Connect GitHub'", () => {
    const out = html(<RepoPicker groups={pickerGroups([DEMO], USER_NO_GH)} selected={null} onSelect={() => {}} defaultOpen />);
    expect(out).toContain("Your GitHub repositories");
    expect(out).toContain("Connect GitHub");
  });

  it("a connected user sees GitHub repos first and the selection is marked", () => {
    const session: Session = { ...USER_NO_GH, githubConnected: true };
    const out = html(<RepoPicker groups={pickerGroups([DEMO, GH], session)} selected={DEMO} onSelect={() => {}} defaultOpen />);
    expect(out.indexOf('data-repo="github:aayush/billing"')).toBeLessThan(out.indexOf('data-repo="demo:tony19053000/shop-app"'));
    expect(out).toContain("private · Python");
    expect(out).toMatch(/aria-selected="true"[^>]*data-repo="demo:tony19053000\/shop-app"/);
  });

  it("shows loading and error states", () => {
    expect(html(<RepoPicker groups={pickerGroups([], GUEST)} selected={null} onSelect={() => {}} loading defaultOpen />)).toContain("Loading…");
    const err = html(<RepoPicker groups={pickerGroups([], GUEST)} selected={null} onSelect={() => {}} error="Server down" onRetry={() => {}} defaultOpen />);
    expect(err).toContain('role="alert"');
    expect(err).toContain("Retry");
  });

  it("renders a hostile repo name as text", () => {
    const out = html(<RepoPicker groups={pickerGroups([HOSTILE], GUEST)} selected={HOSTILE} onSelect={() => {}} defaultOpen />);
    expect(out).not.toContain("<img");
    expect(out).not.toContain("<b>");
    expect(out).not.toContain("\x1b");
    expect(out).toContain("&lt;img");
  });
});

describe("runs list (04 §3.2 /runs)", () => {
  it("links each run with a dot and a status word", () => {
    const out = html(<RunsList runs={[run(), run({ id: "r_2", status: "running", result: null })]} loading={false} error={null} now={Date.parse("2026-09-26T09:05:00Z")} />);
    expect(out).toContain('href="/runs/r_1"');
    expect(out).toContain('href="/runs/r_2"');
    expect(out).toContain("rule broken");
    expect(out).toContain("finding…");
    expect(out).toContain('data-dot="broken"');
    expect(out).toContain('data-dot="running"');
    expect(out).toContain("5 min ago");
  });

  it("skeleton, empty and error states", () => {
    expect(html(<RunsList runs={[]} loading error={null} />)).toContain('data-skeleton="runs"');
    expect(html(<RunsList runs={[]} loading={false} error={null} />)).toContain("No runs yet. Pick a repository to start.");
    expect(html(<RunsList runs={[]} loading={false} error={new ApiError(500, "x")} onRetry={() => {}} />)).toContain("Couldn&#x27;t load your runs");
  });

  it("the pages: runs, counterexamples (only runs with a result), rules", () => {
    const data = { runs: [run(), run({ id: "r_ok", result: null, headline: "all good" })], loading: false, error: null };
    const runsPage = html(<RunsPageView session={GUEST} runs={data} />);
    expect(runsPage).toContain("all good");
    const cx = html(<CounterexamplesView session={GUEST} runs={data} />);
    expect(cx).toContain("find bugs in refunds");
    expect(cx).not.toContain("all good");
    expect(html(<RulesView session={GUEST} runs={data} />)).toContain("rook/rook.yaml");
  });
});

describe("errors and limits (04 §3.6)", () => {
  it("the guest limit card shows the install command", () => {
    const view = errorView(new ApiError(429, "Demo limit reached for today. Install the CLI to run on your own repos: uv tool install rook-cli"), "create");
    const out = html(<ErrorCard view={view} onRetry={() => {}} />);
    expect(out).toContain("Demo limit reached for today");
    expect(out).toContain(`<code class="rounded bg-sunk px-1.5 py-0.5 font-mono text-[13px]">${CLI_INSTALL}</code>`);
    expect(out).not.toContain("Try again");
  });

  it("a busy 429 can retry; a 501 cannot", () => {
    expect(html(<ErrorCard view={errorView(new ApiError(429, "The server is busy; try again in a few minutes"), "create")} onRetry={() => {}} />)).toContain("Try again");
    const na = html(<ErrorCard view={errorView(new ApiError(501, "Not ready"), "create")} onRetry={() => {}} />);
    expect(na).toContain("Not available yet");
    expect(na).not.toContain("Try again");
  });
});

describe("run page (04 §3.2 /runs/[id])", () => {
  const props = { runId: "r_1", api: fakeApi, session: GUEST, runs: noRuns, retry: () => {} };

  it("shows skeleton rows before the first event", () => {
    const out = html(<RunPageView {...props} state={initialRunState} status="connecting" info={{ attempt: 0 }} />);
    expect(out).toContain('data-skeleton="run"');
  });

  it("shows the Reconnecting banner with a retry", () => {
    const state = reduceEvents(minishopRun.slice(0, 20));
    const out = html(<RunPageView {...props} state={state} status="reconnecting" info={{ attempt: 3 }} />);
    expect(out).toMatch(/Reconnecting… \(attempt (<!-- -->)?3(<!-- -->)?\)/);
    expect(out).toContain("Retry now");
    expect(out).not.toContain('data-skeleton="run"');
  });

  it("a refused stream (404) shows an error card, not the run", () => {
    const out = html(<RunPageView {...props} state={initialRunState} status="closed" info={{ attempt: 0, reason: "refused", httpStatus: 404 }} />);
    expect(out).toContain("This run doesn&#x27;t exist, or it belongs to someone else.");
    expect(out).not.toContain("composer-input");
  });

  it("renders the recorded run and marks it current in the recents", () => {
    const state = reduceEvents(minishopRun);
    const out = html(<RunPageView {...props} runs={{ runs: [run({ id: "r_1" })], loading: false }} state={state} status="closed" info={{ attempt: 0, reason: "finished" }} />);
    expect(out).toContain('data-card="counterexample"');
    expect(out).toMatch(/aria-current="page"[^>]*href="\/runs\/r_1"|href="\/runs\/r_1"[^>]*aria-current="page"/);
  });
});

describe("login and repositories", () => {
  it("login: without Supabase config Google is disabled, the demo works", () => {
    const out = html(<LoginView session={GUEST} runs={noRuns} />);
    expect(out).toMatch(/<button[^>]*disabled=""[^>]*>Continue with Google<\/button>/);
    expect(out).toContain("not set up on this site");
    expect(out).toMatch(/<a (?=[^>]*href="\/")(?=[^>]*data-try-demo)[^>]*>/);
    expect(out).toContain("Try the demo without signing in");
  });

  it("login: with sign-in configured the Google button is live; busy and errors show", () => {
    const signIn = { available: true, onSignIn: () => undefined };
    const out = html(<LoginView session={GUEST} runs={noRuns} signIn={signIn} />);
    expect(out).toMatch(/<button(?![^>]*disabled="")[^>]*>Continue with Google<\/button>/);
    expect(out).not.toContain("not set up");
    expect(out).toContain("data-try-demo");
    const busy = html(<LoginView session={GUEST} runs={noRuns} signIn={{ ...signIn, busy: true, error: "<b>nope</b>" }} />);
    expect(busy).toMatch(/<button[^>]*disabled=""[^>]*>Signing in…<\/button>/);
    expect(busy).toContain('role="alert"');
    expect(busy).toContain("&lt;b&gt;nope&lt;/b&gt;");
  });

  it("login: a signed-in user sees who they are and can sign out", () => {
    const out = html(<LoginView session={USER_NO_GH} runs={noRuns} signIn={{ available: true, onSignOut: () => undefined }} />);
    expect(out).toContain("You&#x27;re signed in");
    expect(out).toContain("Aayush · a@example.com");
    expect(out).toMatch(/<button[^>]*>Sign out<\/button>/);
    expect(out).not.toContain("Continue with Google");
  });

  it("repositories: a guest sees the demo list only", () => {
    const out = html(<RepositoriesView session={GUEST} runs={noRuns} repos={[DEMO, GH]} loading={false} error={null} />);
    expect(out).toContain("Demo repositories");
    expect(out).toContain('data-repo="demo:tony19053000/shop-app"');
    expect(out).not.toContain("aayush/billing");
  });
});

describe("sidebar and composer", () => {
  it("sidebar: nav links, recents link to their run, skeleton while loading", () => {
    const out = html(<Sidebar recents={[{ id: "r_9", label: "shop-app · fixed", status: "ok" }]} coins={0.5} userName="guest" active="runs" />);
    for (const href of ["/", "/runs", "/counterexamples", "/rules", "/repositories", "/runs/r_9", "/login"]) expect(out).toContain(`href="${href}"`);
    expect(out).toContain("(passed)");
    expect(html(<Sidebar recents={[]} coins={0} userName="guest" recentsLoading />)).toContain('data-skeleton="recents"');
    const user = html(<Sidebar recents={[]} coins={0} userName="Aayush" signedIn />);
    expect(user).not.toContain('href="/login"');
    expect(user).toMatch(/<button[^>]*>Sign out<\/button>/);
    expect(user).toContain(">Aayush<");
    expect(html(<Sidebar recents={[]} coins={0} userName="guest" />)).not.toContain("Sign out");
  });

  it("composer: the toggle only with a handler, the picker slot replaces the label", () => {
    expect(html(<Composer />)).not.toContain("Auto-approve");
    expect(html(<Composer auto onAutoChange={() => {}} />)).toContain("Auto-approve: on");
    expect(html(<Composer picker={<span data-slot />} repoLabel="x" />)).toContain("data-slot");
  });
});
