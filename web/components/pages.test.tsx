import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AUTO_TOOLTIP, Composer } from "./Composer";
import { ErrorCard } from "./ErrorCard";
import { GithubSetupView } from "./GithubSetupView";
import { HomeView, SIGNED_OUT_TITLE } from "./HomeView";
import { RepoPicker } from "./RepoPicker";
import { RunPageView } from "./RunPage";
import { RunsList } from "./RunsList";
import { CounterexamplesView, LoginView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { ApiError, type RepoOption, type RunSummary } from "@/lib/api";
import { minishopRun } from "@/lib/fixtures/minishop";
import { CLI_INSTALL, errorView, HOSTED_GITHUB_NOTE, pickerGroups, startRun } from "@/lib/pages";
import { initialRunState, reduceEvents } from "@/lib/runStore";
import { RunView } from "./RunView";
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
  const USER: Session = { kind: "user", name: "Aayush Kumar", email: "a@example.com", githubConnected: true };
  const out = html(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} />);
  const sendButton = (markup: string) => markup.match(/<button[^>]*aria-label="Send"[^>]*>/)?.[0] ?? "";

  it("signed out: the title, what Rook is, Sign in with Google and the example link", () => {
    expect(out).toContain("data-signed-out");
    expect(out).toContain(SIGNED_OUT_TITLE);
    expect(out).toContain("smallest sequence of actions that breaks a business rule");
    expect(out).toMatch(/<a[^>]*href="\/login"[^>]*>Sign in with Google<\/a>/);
    expect(out).toMatch(/<button[^>]*data-try-example(?![^>]*disabled="")[^>]*>Try an example without signing in<\/button>/);
    const wired = html(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} signIn={async () => null} />);
    expect(wired).toMatch(/<button[^>]*>Sign in with Google<\/button>/);
  });

  it("signed out: no old demo hero (steps, big demo button, chips)", () => {
    expect(out).not.toContain("data-steps");
    expect(out).not.toContain("data-demo-chips");
    expect(out).not.toContain("Try the demo on");
    expect(out).not.toContain("What should we try to break today?");
  });

  it("the example link is disabled with no example repos", () => {
    const empty = html(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([])} navigate={() => {}} />);
    expect(empty).toMatch(/<button[^>]*disabled=""[^>]*>Try an example without signing in<\/button>/);
  });

  it("signed in: the greeting uses the first name, no sign-in pitch", () => {
    const user = html(<HomeView api={fakeApi} session={USER} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} />);
    expect(user).toContain("data-greeting");
    expect(user).toContain("What should Rook check next, Aayush?");
    expect(user).not.toContain("Sign in with Google");
    expect(user).not.toContain("Try an example without signing in");
    const hostile = html(<HomeView api={fakeApi} session={{ ...USER, name: "<b>Eve</b>\x1b[2J x" }} runs={noRuns} repos={repos([])} navigate={() => {}} />);
    expect(hostile).not.toContain("<b>");
    expect(hostile).not.toContain("\x1b");
  });

  it("the composer: IBM Bob chip, the repo chip, the Auto switch and the placeholder", () => {
    expect(out).toContain("data-env");
    expect(out).toContain("IBM Bob");
    expect(out).toContain("Select repository…");
    expect(out).toContain('aria-haspopup="listbox"');
    expect(out).toMatch(/role="switch" aria-checked="false"/);
    expect(out).toContain("Describe what to check, or ask a question");
  });

  it("send stays disabled until a repository is chosen", () => {
    expect(sendButton(out)).toContain('disabled=""');
    const picked = html(<HomeView api={fakeApi} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} defaultSelected={DEMO} />);
    expect(sendButton(picked)).not.toContain('disabled=""');
  });

  it("the mode line says replay for an example and live for your own repo", () => {
    const demo = html(<HomeView api={fakeApi} session={USER} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} defaultSelected={DEMO} />);
    expect(demo).toContain("IBM Bob · replay");
    const gh = html(<HomeView api={fakeApi} session={USER} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} defaultSelected={GH} />);
    expect(gh).toContain("IBM Bob · live");
  });

  it("a guest's sidebar offers Sign in instead of recents", () => {
    expect(out).toContain("data-sign-in");
    expect(out).not.toContain("No runs yet. Pick a repository to start.");
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
  it("a guest sees only the Examples, with private/public and the language, and a sign-in footer", () => {
    const out = html(<RepoPicker groups={pickerGroups([GH, DEMO], GUEST)} selected={null} onSelect={() => {}} defaultOpen />);
    expect(out).toContain('role="listbox"');
    expect(out).toContain('aria-label="Search repositories"');
    expect(out).toContain("Examples");
    expect(out).not.toContain("Your repositories");
    expect(out).not.toContain("aayush/billing");
    expect(out).toContain("shop-app");
    expect(out).toContain("public · Node.js");
    expect(out.match(/role="option"/g)).toHaveLength(1);
    expect(out).toMatch(/href="\/login"[^>]*>Sign in to use your repositories</);
    expect(out).not.toContain("Connect GitHub");
  });

  it("a signed-in user without GitHub gets 'Connect GitHub'", () => {
    const out = html(<RepoPicker groups={pickerGroups([DEMO], USER_NO_GH)} selected={null} onSelect={() => {}} defaultOpen />);
    expect(out).toContain("Connect GitHub");
    expect(out).toContain("coming soon");
    const wired = html(<RepoPicker groups={pickerGroups([DEMO], USER_NO_GH)} selected={null} onSelect={() => {}} onConnectGithub={() => {}} defaultOpen />);
    expect(wired).toMatch(/<button(?![^>]*disabled="")[^>]*>Connect GitHub<\/button>/);
    expect(wired).not.toContain("coming soon");
  });

  it("a connected user sees 'Your repositories' from GitHub first, Examples last, and 'Add repositories'", () => {
    const session: Session = { ...USER_NO_GH, githubConnected: true };
    const out = html(<RepoPicker groups={pickerGroups([DEMO, GH], session)} selected={DEMO} onSelect={() => {}} onConnectGithub={() => {}} defaultOpen />);
    expect(out).toContain("Your repositories");
    expect(out.indexOf("Your repositories")).toBeLessThan(out.indexOf("Examples"));
    expect(out.indexOf('data-repo="github:aayush/billing"')).toBeLessThan(out.indexOf('data-repo="demo:tony19053000/shop-app"'));
    expect(out).toContain("private · Python");
    expect(out).toMatch(/aria-selected="true"[^>]*data-repo="demo:tony19053000\/shop-app"/);
    expect(out).toMatch(/<button(?![^>]*disabled="")[^>]*>Add repositories<\/button>/);
    expect(out).not.toContain("Connect GitHub");
  });

  it("the chip shows the picked repo", () => {
    const out = html(<RepoPicker groups={pickerGroups([GH], { ...USER_NO_GH, githubConnected: true })} selected={GH} onSelect={() => {}} />);
    expect(out).toContain("aayush/billing");
    expect(out).not.toContain("Select repository…");
    expect(out).not.toContain('role="listbox"');
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
    const view = errorView(new ApiError(429, "Demo limit reached for today. Install the CLI to run on your own repos: uv tool install git+https://github.com/tony19053000/rook"), "create");
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
    const out = html(
      <RunPageView {...props} session={USER_NO_GH} runs={{ runs: [run({ id: "r_1" })], loading: false }} state={state} status="closed" info={{ attempt: 0, reason: "finished" }} />,
    );
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

  it("repositories: a signed-in user without GitHub gets 'Connect GitHub'; a connected one sees their repos", () => {
    const connect = async () => null;
    const out = html(<RepositoriesView session={USER_NO_GH} runs={noRuns} repos={[DEMO]} loading={false} error={null} connectGithub={connect} />);
    expect(out).toContain("data-connect-github");
    expect(out).toMatch(/<button(?![^>]*disabled="")[^>]*>Connect GitHub<\/button>/);
    const connected: Session = { ...USER_NO_GH, githubConnected: true };
    const withGh = html(<RepositoriesView session={connected} runs={noRuns} repos={[GH, DEMO]} loading={false} error={null} connectGithub={connect} />);
    expect(withGh).not.toContain("data-connect-github");
    expect(withGh).toContain('data-repo="github:aayush/billing"');
  });

  it("github setup: working, connected and failed states", () => {
    expect(html(<GithubSetupView session={USER_NO_GH} runs={noRuns} status={{ kind: "working" }} />)).toContain("Connecting GitHub…");
    const done = html(<GithubSetupView session={USER_NO_GH} runs={noRuns} status={{ kind: "done" }} />);
    expect(done).toContain("GitHub connected");
    expect(done).toContain("rook run owner/name");
    const failed = html(
      <GithubSetupView session={USER_NO_GH} runs={noRuns} status={{ kind: "error", message: "<b>nope</b>" }} connectGithub={async () => null} />,
    );
    expect(failed).toContain('role="alert"');
    expect(failed).toContain("&lt;b&gt;nope&lt;/b&gt;");
    expect(failed).toContain("Connect GitHub again");
  });

  it("repositories: a guest sees the demo list only", () => {
    const out = html(<RepositoriesView session={GUEST} runs={noRuns} repos={[DEMO, GH]} loading={false} error={null} />);
    expect(out).toContain("Demo repositories");
    expect(out).toContain('data-repo="demo:tony19053000/shop-app"');
    expect(out).not.toContain("aayush/billing");
  });
});

describe("sidebar and composer", () => {
  it("composer: the Auto switch only with a handler (with its tooltip), the picker slot replaces the label", () => {
    expect(html(<Composer />)).not.toContain('role="switch"');
    const on = html(<Composer auto onAutoChange={() => {}} />);
    expect(on).toMatch(/role="switch" aria-checked="true"/);
    expect(on).toContain(AUTO_TOOLTIP);
    expect(html(<Composer picker={<span data-slot />} repoLabel="x" />)).toContain("data-slot");
    expect(html(<Composer status="IBM Bob · replay" />)).toContain("IBM Bob · replay");
  });

  it("composer: canSend=false keeps the send arrow disabled even with allowEmpty", () => {
    expect(html(<Composer allowEmpty canSend={false} />)).toMatch(/<button type="submit" disabled=""[^>]*aria-label="Send"/);
    expect(html(<Composer allowEmpty />)).not.toMatch(/<button type="submit" disabled=""/);
  });
});

describe("hosted GitHub runs (ROOK-041)", () => {
  const USER_RUNS: Session = { kind: "user", name: "Aayush", email: "a@example.com", githubConnected: true, canRunGithub: true };
  const USER_CLI: Session = { ...USER_RUNS, canRunGithub: false };
  const recorder = () => {
    const bodies: unknown[] = [];
    return { bodies, api: { createRun: async (body: unknown) => (bodies.push(body), { run_id: "r_gh" }) } };
  };

  it("picking a GitHub repo starts a real run when the server can run it", async () => {
    const { bodies, api } = recorder();
    const outcome = await startRun(api, GH, "find bugs", false, true);
    expect(outcome).toEqual({ kind: "started", runId: "r_gh", href: "/runs/r_gh" });
    expect(bodies).toEqual([{ repo: { kind: "github", ref: "aayush/billing" }, request: "find bugs", options: { auto: false } }]);
  });

  it("falls back to the CLI hint otherwise, and sends nothing", async () => {
    const { bodies, api } = recorder();
    const outcome = await startRun(api, GH, "find bugs", false, false);
    expect(outcome).toMatchObject({ kind: "hint" });
    expect(outcome.kind === "hint" && outcome.message).toContain("rook run aayush/billing");
    expect(bodies).toEqual([]);
  });

  it("maps 401, 403, 429 and 503 to friendly error cards", async () => {
    const failing = (error: ApiError) => ({ createRun: async () => Promise.reject(error) });
    const view = async (error: ApiError) => {
      const outcome = await startRun(failing(error), GH, "x", false, true);
      if (outcome.kind !== "error") throw new Error("expected an error");
      return outcome.error;
    };
    expect((await view(new ApiError(401, "Sign in"))).kind).toBe("auth");
    expect(await view(new ApiError(403, "Not your repository"))).toMatchObject({ kind: "denied", message: "Not your repository", retryable: false });
    expect(await view(new ApiError(429, "Rook is busy", 120))).toMatchObject({ kind: "busy", message: "Rook is busy. Try again in about 2 minutes.", retryable: true });
    const na = await view(new ApiError(503, "Hosted GitHub runs are not configured"));
    expect(na).toMatchObject({ kind: "unavailable", retryable: false });
    const out = html(<ErrorCard view={na} onRetry={() => {}} />);
    expect(out).toContain("Hosted GitHub runs are not configured");
    expect(out).not.toContain("Try again");
  });

  it("the composer says a picked GitHub repo runs on Rook's server and costs coins", () => {
    const on = html(<HomeView api={fakeApi} session={USER_RUNS} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} defaultSelected={GH} />);
    expect(on).toContain("data-hosted-note");
    expect(on).toContain(HOSTED_GITHUB_NOTE.replace("'", "&#x27;"));
    const cli = html(<HomeView api={fakeApi} session={USER_CLI} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} defaultSelected={GH} />);
    expect(cli).not.toContain("data-hosted-note");
    const demo = html(<HomeView api={fakeApi} session={USER_RUNS} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} defaultSelected={DEMO} />);
    expect(demo).not.toContain("data-hosted-note");
  });

  it("the final card links the opened PR (only a github.com URL)", () => {
    const pr = { url: "https://github.com/aayush/billing/pull/7", number: 7, branch: "rook/fix" };
    const state = { ...initialRunState, status: "done" as const, summary: "1 rule broken, fixed and verified", pr };
    const out = html(<RunView state={state} runId="r_gh" api={fakeApi} />);
    expect(out).toMatch(/data-run-summary="done"[\s\S]*PR #(<!-- -->)?7(<!-- -->)? opened[\s\S]*href="https:\/\/github.com\/aayush\/billing\/pull\/7"/);
    expect(out).toContain("View pull request");
    const evil = html(<RunView state={{ ...state, pr: { ...pr, url: "javascript:alert(1)" } }} runId="r_gh" api={fakeApi} />);
    expect(evil).not.toContain('href="javascript');
    const none = html(<RunView state={{ ...state, pr: null }} runId="r_gh" api={fakeApi} />);
    expect(none).not.toContain("data-pr");
  });
});
