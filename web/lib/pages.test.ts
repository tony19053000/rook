import { describe, expect, it } from "vitest";
import { ApiError, type RepoOption, type RunSummary } from "./api";
import {
  anyActive,
  canPick,
  cliHint,
  CLI_INSTALL,
  errorView,
  formatWhen,
  moveIndex,
  newRunBody,
  pickerGroups,
  pickerOptions,
  recentFromSummary,
  recentStatus,
  repoMeta,
  retryText,
  runHref,
  runStatusText,
  shellProps,
  streamNotice,
} from "./pages";
import { GUEST, type Session } from "./session";

const run = (patch: Partial<RunSummary> = {}): RunSummary => ({
  id: "r_1",
  repo: { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app" },
  status: "done",
  created_at: "2026-09-26T09:00:00Z",
  finished_at: null,
  headline: "find bugs",
  result: null,
  coins: 0.1,
  last_seq: 10,
  ...patch,
});

const DEMO: RepoOption = { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app", private: false, language: "Node.js" };
const DEMO2: RepoOption = { kind: "demo", ref: "tony19053000/wallet-api", name: "wallet-api", private: false, language: "Go" };
const GH: RepoOption = { kind: "github", ref: "aayush/billing", name: "aayush/billing", private: true, language: "Python" };
const USER: Session = { kind: "user", name: "Aayush", email: "a@example.com", githubConnected: true };
const USER_NO_GH: Session = { ...USER, githubConnected: false };

describe("recents (04 §3.1 status dots)", () => {
  it("running and queued pulse, broken is red, fixed or held is green, stopped is dim", () => {
    expect(recentStatus(run({ status: "running" }))).toBe("running");
    expect(recentStatus(run({ status: "queued" }))).toBe("running");
    expect(recentStatus(run({ result: "broken" }))).toBe("broken");
    expect(recentStatus(run({ result: "fixed" }))).toBe("ok");
    expect(recentStatus(run({ status: "done" }))).toBe("ok");
    expect(recentStatus(run({ status: "failed" }))).toBe("idle");
    expect(recentStatus(run({ status: "cancelled", result: "broken" }))).toBe("broken");
  });

  it("labels say the status in words, not only colour", () => {
    expect(recentFromSummary(run({ status: "running" }))).toEqual({ id: "r_1", label: "shop-app · finding…", status: "running" });
    expect(runStatusText(run({ result: "broken" }))).toBe("rule broken");
    expect(runStatusText(run({ result: "fixed" }))).toBe("fixed");
    expect(runStatusText(run())).toBe("rules held");
    expect(runStatusText(run({ status: "failed" }))).toBe("failed");
    expect(runStatusText(run({ status: "queued" }))).toBe("queued");
  });

  it("cleans and shortens a hostile repo name", () => {
    const label = recentFromSummary(run({ repo: { kind: "demo", ref: "x", name: `a\x1b[31m${"b".repeat(80)}` } })).label;
    expect(label).not.toContain("\x1b");
    expect(label.length).toBeLessThan(60);
  });

  it("polls only while a run is active", () => {
    expect(anyActive([run(), run({ status: "failed" })])).toBe(false);
    expect(anyActive([run(), run({ status: "queued" })])).toBe(true);
  });

  it("shellProps: guest name, sign-in link, summed coins", () => {
    const props = shellProps(GUEST, { runs: [run({ coins: 0.1 }), run({ id: "r_2", coins: 0.25 })], loading: false });
    expect(props).toMatchObject({ userName: "guest", signedIn: false, recentsLoading: false });
    expect(props.coins).toBeCloseTo(0.35);
    expect(props.recents).toHaveLength(2);
    expect(shellProps(USER, { runs: [], loading: true })).toMatchObject({ userName: "Aayush", signedIn: true, recentsLoading: true });
  });

  it("formats when and encodes the run link", () => {
    const now = Date.parse("2026-09-26T12:00:00Z");
    expect(formatWhen("2026-09-26T11:59:40Z", now)).toBe("just now");
    expect(formatWhen("2026-09-26T11:55:00Z", now)).toBe("5 min ago");
    expect(formatWhen("2026-09-26T09:00:00Z", now)).toBe("3 h ago");
    expect(formatWhen("2026-09-20T09:00:00Z", now)).toBe("2026-09-20");
    expect(formatWhen("not a date", now)).toBe("");
    expect(runHref("r_1/../x")).toBe("/runs/r_1%2F..%2Fx");
  });
});

describe("repo picker (04 §3.3)", () => {
  it("a guest sees only the demo repos, even if the server lists more", () => {
    const groups = pickerGroups([GH, DEMO, DEMO2], GUEST);
    expect(groups).toEqual({ github: null, demo: [DEMO, DEMO2], connectGithub: false });
    expect(pickerOptions(groups)).toEqual([DEMO, DEMO2]);
    expect(canPick(GH, GUEST)).toBe(false);
    expect(canPick(DEMO, GUEST)).toBe(true);
  });

  it("a signed-in user without GitHub gets the Connect GitHub item", () => {
    expect(pickerGroups([DEMO], USER_NO_GH)).toEqual({ github: null, demo: [DEMO], connectGithub: true });
    expect(canPick(GH, USER_NO_GH)).toBe(false);
  });

  it("a connected user sees their GitHub repos first, then the demos", () => {
    const groups = pickerGroups([DEMO, GH], USER);
    expect(groups).toEqual({ github: [GH], demo: [DEMO], connectGithub: false });
    expect(pickerOptions(groups)).toEqual([GH, DEMO]);
    expect(canPick(GH, USER)).toBe(true);
  });

  it("shows private/public and the language", () => {
    expect(repoMeta(GH)).toBe("private · Python");
    expect(repoMeta({ private: false, language: "" })).toBe("public");
  });

  it("arrow keys wrap around", () => {
    expect(moveIndex(-1, 1, 3)).toBe(0);
    expect(moveIndex(-1, -1, 3)).toBe(2);
    expect(moveIndex(2, 1, 3)).toBe(0);
    expect(moveIndex(0, -1, 3)).toBe(2);
    expect(moveIndex(0, 1, 0)).toBe(-1);
  });
});

describe("new run body (02 §11 POST /runs)", () => {
  it("needs a repo", () => {
    expect(newRunBody(null, "find bugs", false)).toEqual({ error: "Pick a repository first." });
  });

  it("sends only kind + ref, the trimmed request and auto", () => {
    expect(newRunBody(DEMO, "  check refunds  ", true)).toEqual({
      body: { repo: { kind: "demo", ref: "tony19053000/shop-app" }, request: "check refunds", options: { auto: true } },
    });
  });

  it("refuses a request over 2000 chars", () => {
    expect(newRunBody(DEMO, "x".repeat(2001), false)).toHaveProperty("error");
    expect(newRunBody(DEMO, "x".repeat(2000), false)).toHaveProperty("body");
    // the hosted server runs only demo repos: a GitHub repo gets the CLI command instead of a 403
    expect(newRunBody({ kind: "github", ref: "alice/shop" }, "find bugs", false)).toEqual({
      error: "The hosted server runs only the demo repositories. Run this one with the CLI: rook run alice/shop",
    });
  });
});

describe("hosted GitHub runs (ROOK-041)", () => {
  const gh = { kind: "github" as const, ref: "alice/shop" };

  it("a GitHub repo becomes a POST /runs body when the server can run it", () => {
    expect(newRunBody(gh, " find bugs ", false, true)).toEqual({
      body: { repo: { kind: "github", ref: "alice/shop" }, request: "find bugs", options: { auto: false } },
    });
  });

  it("falls back to the CLI hint otherwise (older server, or not linked)", () => {
    expect(newRunBody(gh, "find bugs", false, false)).toEqual({ error: cliHint("alice/shop") });
    expect(cliHint("alice/shop")).toContain("rook run alice/shop");
  });

  it("403 not your repo: the server's reason, else a friendly fallback", () => {
    expect(errorView(new ApiError(403, "This repository is not linked to your account"), "create")).toMatchObject({
      kind: "denied",
      message: "This repository is not linked to your account",
      retryable: false,
    });
    expect(errorView(new ApiError(403, "HTTP 403"), "create").message).toContain("shared with the Rook GitHub App");
  });

  it("429 busy or daily limit: the server's message plus the Retry-After wait", () => {
    expect(errorView(new ApiError(429, "You have used today's hosted runs", 7200), "create")).toMatchObject({
      kind: "busy",
      message: "You have used today's hosted runs. Try again in about 2 hours.",
      retryable: true,
    });
    expect(errorView(new ApiError(429, "Another run of yours is still going"), "create").message).toBe("Another run of yours is still going");
  });

  it("503 not configured: the server's message, no retry", () => {
    expect(errorView(new ApiError(503, "Hosted GitHub runs are not configured on this server"), "create")).toMatchObject({
      kind: "unavailable",
      title: "Not available on this server",
      message: "Hosted GitHub runs are not configured on this server",
      retryable: false,
    });
    expect(errorView(new ApiError(503, "HTTP 503"), "create").message).toContain("isn't set up");
  });
});

describe("errors (04 §3.6)", () => {
  it("the guest limit 429 shows the limit copy with the CLI install command", () => {
    const view = errorView(new ApiError(429, "Demo limit reached for today. Install the CLI to run on your own repos: uv tool install git+https://github.com/tony19053000/rook", 3600), "create");
    expect(view.kind).toBe("limit");
    expect(view.title).toBe("Demo limit reached for today");
    expect(view.message).toContain(CLI_INSTALL);
    expect(view.retryable).toBe(false);
  });

  it("a busy-queue or budget 429 shows the server's message and can retry", () => {
    const busy = errorView(new ApiError(429, "The server is busy; try again in a few minutes", 60), "create");
    expect(busy).toMatchObject({ kind: "busy", message: "The server is busy; try again in a few minutes", retryable: true });
    const budget = errorView(new ApiError(429, "Today's AI budget is spent; try again tomorrow", 40000), "create");
    expect(budget.message).toBe("Today's AI budget is spent; try again tomorrow");
    const bare = errorView(new ApiError(429, "HTTP 429", 120), "create");
    expect(bare.message).toBe("Too many requests right now. Try again in about 2 minutes.");
  });

  it("501 says it isn't available yet", () => {
    const view = errorView(new ApiError(501, "Replaying a counterexample on the server is not available yet"), "create");
    expect(view).toMatchObject({ kind: "unavailable", title: "Not available yet", retryable: false });
    expect(view.message).toContain("not available yet");
  });

  it("403 passes the server's reason; 404 on a run hides whether it exists", () => {
    expect(errorView(new ApiError(403, "This repo is not on the allowlist; run it with the CLI"), "create").message).toContain("CLI");
    expect(errorView(new ApiError(404, "Not found"), "run").message).toBe("This run doesn't exist, or it belongs to someone else.");
  });

  it("network failures and 5xx are retryable; 401 asks to sign in", () => {
    expect(errorView(new TypeError("fetch failed"), "runs")).toMatchObject({ kind: "network", retryable: true, title: "Couldn't load your runs" });
    expect(errorView(new ApiError(502, "Bad Gateway"), "repos")).toMatchObject({ kind: "server", retryable: true });
    expect(errorView(new ApiError(401, "x"), "runs").kind).toBe("auth");
  });

  it("strips control characters from the server's detail and caps its length", () => {
    const view = errorView(new ApiError(403, `bad\x1b]8;;evil\x07${"y".repeat(500)}`), "create");
    expect(view.message).not.toMatch(/[\x00-\x1f]/);
    expect(view.message.length).toBeLessThanOrEqual(300);
  });

  it("retry text", () => {
    expect(retryText(null)).toBe("");
    expect(retryText(30)).toBe("Try again in a minute.");
    expect(retryText(600)).toBe("Try again in about 10 minutes.");
    expect(retryText(7200)).toBe("Try again in about 2 hours.");
  });
});

describe("stream notice (04 §3.6)", () => {
  it("skeleton until the first event, a banner while reconnecting", () => {
    expect(streamNotice("connecting", { attempt: 0 }, 0)).toEqual({ kind: "loading" });
    expect(streamNotice("open", { attempt: 0 }, 0)).toEqual({ kind: "loading" });
    expect(streamNotice("open", { attempt: 0 }, 5)).toEqual({ kind: "none" });
    expect(streamNotice("reconnecting", { attempt: 2 }, 5)).toEqual({ kind: "reconnecting", attempt: 2 });
    expect(streamNotice("closed", { attempt: 0, reason: "finished" }, 90)).toEqual({ kind: "none" });
  });

  it("a refused stream becomes an error card", () => {
    const notice = streamNotice("closed", { attempt: 0, reason: "refused", httpStatus: 404 }, 0);
    expect(notice.kind).toBe("refused");
    if (notice.kind === "refused") expect(notice.error.kind).toBe("missing");
    const auth = streamNotice("closed", { attempt: 0, reason: "refused", httpStatus: 401 }, 0);
    if (auth.kind === "refused") expect(auth.error.kind).toBe("auth");
  });
});
