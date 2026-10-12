// @vitest-environment jsdom
// ROOK-052: the web app's deletion controls (DELETE /runs/{id} and DELETE /me/data, ROOK-051), the
// "Recorded example run" / "Live run" labels (06 §4), the plain states, and no button that does nothing.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentRow } from "./AgentRow";
import { ErrorCard } from "./ErrorCard";
import { HomeView } from "./HomeView";
import { afterDeleteHref, RunPageView } from "./RunPage";
import { Sidebar } from "./Sidebar";
import { CounterexamplesView, RepositoriesView, RulesView, RunsPageView } from "./SimpleViews";
import { CONTACT_EMAIL } from "@/content/site";
import { ApiError, TIMEOUT_STATUS, type RepoOption } from "@/lib/api";
import { minishopRun } from "@/lib/fixtures/minishop";
import { errorView, OWN_REPOS_NOTE, RUN_MODE_TEXT, runMode, startRun, STILL_DELETING } from "@/lib/pages";
import { loginCopy } from "@/content/login";
import { initialRunState, reduceEvents, type AgentItem, type RunState } from "@/lib/runStore";
import { GUEST, type Session } from "@/lib/session";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const USER: Session = { kind: "user", name: "Aayush", email: "a@example.com", githubConnected: true };
const DEMO: RepoOption = { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app", private: false, language: "Node.js" };
const GH: RepoOption = { kind: "github", ref: "aayush/billing", name: "aayush/billing", private: true, language: "Python" };
const noRuns = { runs: [], loading: false, error: null };
const repos = (list: RepoOption[]) => ({ repos: list, loading: false, error: null, retry: () => {} });
const recordedState = reduceEvents(minishopRun);

/** The recorded run with every agent call marked live, as a run with live Bob calls sends it. */
function liveState(): RunState {
  return reduceEvents(
    minishopRun.map((event) => (event.type === "agent.finished" ? { ...event, data: { ...event.data, recorded: false } } : event)) as typeof minishopRun,
  );
}

function runPage(options: { deleteRun?: () => Promise<{ ok: boolean }>; session?: Session; state?: RunState } = {}) {
  const deleteRun = vi.fn(options.deleteRun ?? (async () => ({ ok: true })));
  const navigate = vi.fn();
  const api = { answer: async () => ({ ok: true }), chat: async () => ({ ok: true }), deleteRun };
  render(
    <RunPageView
      runId="r 1"
      api={api}
      session={options.session ?? USER}
      runs={{ runs: [], loading: false }}
      navigate={navigate}
      state={options.state ?? recordedState}
      status="closed"
      info={{ attempt: 0, reason: "finished" }}
      retry={() => {}}
    />,
  );
  return { deleteRun, navigate };
}

const runBox = () => screen.getByRole("group", { name: "Delete run" });

describe("Delete run (run page)", () => {
  it("asks first: nothing is sent until the confirm step, and Cancel backs out", () => {
    const { deleteRun, navigate } = runPage();
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    expect(runBox().textContent).toContain("removes the run, its events, its counterexamples and its workspace files");
    expect(runBox().textContent).toContain("can't be undone");
    expect(deleteRun).not.toHaveBeenCalled();
    fireEvent.click(within(runBox()).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group", { name: "Delete run" })).toBeNull();
    expect(screen.getByRole("button", { name: "Delete run" })).toBeTruthy();
    expect(deleteRun).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("on success calls DELETE /runs/{id} once and goes to /runs (a guest: /app)", async () => {
    const { deleteRun, navigate } = runPage();
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/runs"));
    expect(deleteRun).toHaveBeenCalledTimes(1);
    expect(deleteRun).toHaveBeenCalledWith("r 1");
    expect(afterDeleteHref(GUEST)).toBe("/app");
    cleanup();

    const guest = runPage({ session: GUEST });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    await waitFor(() => expect(guest.navigate).toHaveBeenCalledWith("/app"));
  });

  it("on failure shows a plain message with Retry, and the retry can succeed", async () => {
    let attempt = 0;
    const { deleteRun, navigate } = runPage({
      deleteRun: async () => {
        attempt += 1;
        if (attempt === 1) throw new ApiError(500, "Internal Server Error");
        return { ok: true };
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("The server had a problem (HTTP 500). Try again.");
    expect(navigate).not.toHaveBeenCalled();
    fireEvent.click(within(runBox()).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/runs"));
    expect(deleteRun).toHaveBeenCalledTimes(2);
  });

  it("a network failure says nothing was deleted; a run that is gone offers no Retry", async () => {
    runPage({ deleteRun: async () => Promise.reject(new TypeError("offline")) });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    expect((await screen.findByRole("alert")).textContent).toContain("nothing was deleted");
    expect(within(runBox()).getByRole("button", { name: "Retry" })).toBeTruthy();
    cleanup();

    runPage({ deleteRun: async () => Promise.reject(new ApiError(404, "Not Found")) });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This run is already gone, or it belongs to someone else.");
    expect(within(runBox()).queryByRole("button", { name: "Retry" })).toBeNull();
  });

  it.each([TIMEOUT_STATUS, 504])("a timeout (HTTP %i) reads as still deleting, not as an error", async (status) => {
    const { navigate } = runPage({ deleteRun: async () => Promise.reject(new ApiError(status, "timeout")) });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    await waitFor(() => expect(runBox().querySelector('[data-delete-result="pending"]')).not.toBeNull());
    expect(runBox().textContent).toContain(STILL_DELETING);
    expect(STILL_DELETING).toMatch(/Still deleting.*Refresh in a moment/);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(within(runBox()).getByRole("button", { name: "Refresh" })).toBeTruthy();
    expect(within(runBox()).queryByRole("button", { name: "Retry" })).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("the button is off while the request is on its way (no double delete)", async () => {
    let finish: (value: { ok: boolean }) => void = () => {};
    const { deleteRun } = runPage({ deleteRun: () => new Promise((resolve) => (finish = resolve)) });
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete this run" }));
    const sending = screen.getByRole("button", { name: "Deleting…" }) as HTMLButtonElement;
    expect(sending.disabled).toBe(true);
    fireEvent.click(sending);
    expect(deleteRun).toHaveBeenCalledTimes(1);
    finish({ ok: true });
    await screen.findByText("Deleted.");
  });
});

function sidebar(options: { onDeleteData?: () => Promise<unknown> } = {}) {
  const onDeleteData = vi.fn(options.onDeleteData ?? (async () => ({ ok: true, runs_deleted: 3 })));
  const onSignOut = vi.fn(async () => {});
  render(<Sidebar recents={[]} coins={0} userName="Aayush" email="a@example.com" signedIn defaultMenuOpen onDeleteData={onDeleteData} onSignOut={onSignOut} />);
  return { onDeleteData, onSignOut };
}

const dataBox = () => screen.getByRole("group", { name: "Delete my data" });

describe("Delete my data (account menu)", () => {
  it("is in the signed-in account menu and not offered to a guest", () => {
    sidebar();
    expect(screen.getByRole("menuitem", { name: "Delete my data" })).toBeTruthy();
    cleanup();
    render(<Sidebar recents={[]} coins={0} userName="guest" />);
    expect(screen.queryByText("Delete my data")).toBeNull();
  });

  it("the confirm step says what is deleted and what is not, before anything is sent", () => {
    const { onDeleteData, onSignOut } = sidebar();
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete my data" }));
    const text = dataBox().textContent ?? "";
    expect(text).toContain("all your runs");
    expect(text).toContain("your GitHub link");
    expect(text).toContain("signs you out");
    expect(text).toContain(`Your sign-in account itself is removed on request: email ${CONTACT_EMAIL}`);
    expect(onDeleteData).not.toHaveBeenCalled();
    fireEvent.click(within(dataBox()).getByRole("button", { name: "Cancel" }));
    expect(onDeleteData).not.toHaveBeenCalled();
    expect(onSignOut).not.toHaveBeenCalled();
  });

  it("on success calls DELETE /me/data once, then signs out", async () => {
    const { onDeleteData, onSignOut } = sidebar();
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete my data" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete my data" }));
    await waitFor(() => expect(onSignOut).toHaveBeenCalledTimes(1));
    expect(onDeleteData).toHaveBeenCalledTimes(1);
  });

  it("on failure stays signed in, shows a plain message with Retry, and the retry can succeed", async () => {
    let attempt = 0;
    const { onDeleteData, onSignOut } = sidebar({
      onDeleteData: async () => {
        attempt += 1;
        if (attempt === 1) throw new ApiError(403, "Cross-site request refused");
        return { ok: true, runs_deleted: 0 };
      },
    });
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete my data" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete my data" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Cross-site request refused");
    expect(onSignOut).not.toHaveBeenCalled();
    fireEvent.click(within(dataBox()).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(onSignOut).toHaveBeenCalledTimes(1));
    expect(onDeleteData).toHaveBeenCalledTimes(2);
  });

  it("a timeout reads as still deleting and does not sign out", async () => {
    const { onSignOut } = sidebar({ onDeleteData: async () => Promise.reject(new ApiError(TIMEOUT_STATUS, "timeout")) });
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete my data" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete my data" }));
    await waitFor(() => expect(dataBox().textContent).toContain(STILL_DELETING));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(onSignOut).not.toHaveBeenCalled();
  });
});

describe("run labels (06 §4: recorded vs live, never blurred)", () => {
  it("a run with recorded Bob answers is a Recorded example run, with the one-line explanation", () => {
    runPage({ state: recordedState });
    const label = document.querySelector("[data-run-mode]") as HTMLElement;
    expect(label.getAttribute("data-run-mode")).toBe("recorded");
    expect(label.textContent).toContain("Recorded example run");
    expect(label.textContent).toContain("Bob's answers are replayed from a saved real run. The engine still runs live against the real app.");
    expect(label.textContent).not.toContain("Live run");
  });

  it("a run with live Bob calls is a Live run", () => {
    runPage({ state: liveState() });
    const label = document.querySelector("[data-run-mode]") as HTMLElement;
    expect(label.getAttribute("data-run-mode")).toBe("live");
    expect(label.textContent).toContain("Live run");
    expect(label.textContent).not.toContain("Recorded");
  });

  it("the signal is the server's own mark on each finished agent call, not the repo kind", () => {
    expect(runMode(recordedState)).toBe("recorded");
    expect(runMode(liveState())).toBe("live"); // an example repo run with live Bob is still a live run
    expect(runMode(initialRunState)).toBeNull();
    const created = reduceEvents(minishopRun.filter((e) => e.type === "run.created"));
    expect(created.created?.repo.kind).not.toBe("github");
    expect(runMode(created)).toBeNull(); // not known yet: no label rather than a guess
    expect(runMode({ items: [], created: { repo: { kind: "github" } } })).toBe("live");
    const agent = (recorded: boolean, status = "done") => ({ kind: "agent", status, recorded });
    expect(runMode({ items: [agent(false), agent(true)], created: { repo: { kind: "github" } } })).toBe("recorded");
    expect(runMode({ items: [agent(true, "working")], created: null })).toBeNull();
    expect(RUN_MODE_TEXT.recorded.label).toBe("Recorded example run");
    expect(RUN_MODE_TEXT.live.label).toBe("Live run");
  });

  it("shows no label before the run has said which it is", () => {
    runPage({ state: initialRunState });
    expect(document.querySelector("[data-run-mode]")).toBeNull();
    expect(document.querySelector('[data-skeleton="run"]')?.textContent).toContain("Waiting for the run to start");
  });
});

describe("/app: what signing in adds, and where your own repos run", () => {
  it("a guest's home carries no sign-in pitch; /login says what signing in adds and where own repos run", () => {
    render(<HomeView api={{ createRun: async () => ({ run_id: "r" }) }} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} />);
    expect(document.querySelector("[data-sign-in-adds]")).toBeNull();
    expect(document.querySelector("[data-own-repos-note]")).toBeNull();
    expect(loginCopy.lead).toContain("keep your runs");
    expect(loginCopy.lead).toContain("connect GitHub");
    expect(loginCopy.guestNote).toContain("To run Rook on your own repos, install the CLI.");
    expect(OWN_REPOS_NOTE).toContain("on your machine with the CLI");
  });

  it("tells a signed-in user the same about their own repos, unless this server runs them", () => {
    const api = { createRun: async () => ({ run_id: "r" }) };
    render(<HomeView api={api} session={USER} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} />);
    expect(document.querySelector("[data-own-repos-note]")?.textContent).toContain(OWN_REPOS_NOTE);
    cleanup();
    render(<HomeView api={api} session={{ ...USER, canRunGithub: true }} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} />);
    expect(document.querySelector("[data-own-repos-note]")).toBeNull();
  });

  it("the server's 503 for an own-repo run shows once, with the two CLI commands as code", async () => {
    const detail =
      "Running your own GitHub repos is not available on this server. Run it on your machine with the rook CLI: uv tool install git+https://github.com/tony19053000/rook, then rook run <owner>/<repo>";
    const outcome = await startRun({ createRun: async () => Promise.reject(new ApiError(503, detail)) }, GH, "x", false, true);
    if (outcome.kind !== "error") throw new Error("expected an error");
    render(<ErrorCard view={outcome.error} onRetry={() => {}} />);
    expect(screen.getByRole("alert").textContent).toBe(OWN_REPOS_NOTE);
    const commands = [...document.querySelectorAll("[data-commands] code")].map((el) => el.textContent);
    expect(commands).toEqual(["uv tool install git+https://github.com/tony19053000/rook", "rook run aayush/billing"]);
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull(); // retrying can't help
  });
});

describe("states: loading, failure, quota reached, retry", () => {
  it("quota reached: says the guest limit in plain words, gives the CLI command, and offers no retry", () => {
    render(<ErrorCard view={errorView(new ApiError(429, "Guest limit reached for today."), "create")} onRetry={() => {}} />);
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).toContain("Guests get 3 example runs a day");
    expect(text).toContain("Come back tomorrow");
    expect(text).toContain("uv tool install git+https://github.com/tony19053000/rook");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("failure: a retryable error has a Try again button that calls back", () => {
    const onRetry = vi.fn();
    render(<ErrorCard view={errorView(new TypeError("offline"), "runs")} onRetry={onRetry} />);
    expect(screen.getByRole("alert").textContent).toBe("Couldn't reach the server. Check your connection and try again.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("loading and failure on the lists: a skeleton, then the reason with a retry", () => {
    const refresh = vi.fn();
    render(<RunsPageView session={USER} runs={{ runs: [], loading: true, error: null }} />);
    expect(document.querySelector('[data-skeleton="runs"][aria-busy="true"]')).not.toBeNull();
    cleanup();
    render(<RunsPageView session={USER} runs={{ runs: [], loading: false, error: new ApiError(500, ""), refresh }} />);
    expect(screen.getByRole("alert").textContent).toBe("The server had a problem (HTTP 500). Try again.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

/** React's props of a rendered element (the handlers a button really has). */
function reactProps(el: Element): Record<string, unknown> {
  const key = Object.keys(el).find((k) => k.startsWith("__reactProps$"));
  return key === undefined ? {} : ((el as unknown as Record<string, unknown>)[key] as Record<string, unknown>);
}

describe("no button that does nothing", () => {
  const pages: [string, () => React.ReactElement][] = [
    [
      "the finished run page",
      () => (
        <RunPageView
          runId="r_1"
          api={{ answer: async () => ({ ok: true }), chat: async () => ({ ok: true }), deleteRun: async () => ({ ok: true }) }}
          session={USER}
          runs={{ runs: [], loading: false }}
          navigate={() => {}}
          state={recordedState}
          status="closed"
          info={{ attempt: 0, reason: "finished" }}
          retry={() => {}}
        />
      ),
    ],
    ["the home, signed out", () => <HomeView api={{ createRun: async () => ({ run_id: "r" }) }} session={GUEST} runs={noRuns} repos={repos([DEMO])} navigate={() => {}} />],
    ["the home, signed in", () => <HomeView api={{ createRun: async () => ({ run_id: "r" }) }} session={USER} runs={noRuns} repos={repos([GH, DEMO])} navigate={() => {}} />],
    ["/runs", () => <RunsPageView session={USER} runs={noRuns} />],
    ["/counterexamples", () => <CounterexamplesView session={USER} runs={noRuns} />],
    ["/rules", () => <RulesView session={USER} runs={noRuns} />],
    ["/repositories", () => <RepositoriesView session={USER} runs={noRuns} repos={[GH, DEMO]} loading={false} error={null} connectGithub={async () => null} />],
    ["the open account menu", () => <Sidebar recents={[]} coins={0} userName="A" signedIn defaultMenuOpen onToggle={() => {}} />],
  ];

  it.each(pages)("%s: every enabled button has a handler (or submits its form)", (_name, page) => {
    render(page());
    const buttons = [...document.querySelectorAll("button")];
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      if (button.disabled) continue;
      const works = typeof reactProps(button).onClick === "function" || (button.type === "submit" && button.closest("form") !== null);
      expect(works, `button "${button.textContent || button.getAttribute("aria-label")}" does nothing`).toBe(true);
    }
  });

  it.each(pages)("%s: nothing offers the unbuilt actions (edit one rule, replay a counterexample, download the test)", (_name, page) => {
    render(page());
    for (const control of document.querySelectorAll("button, a")) {
      const label = `${control.textContent ?? ""} ${control.getAttribute("aria-label") ?? ""}`;
      expect(label).not.toMatch(/\b(edit|replay|download)\b/i);
    }
  });
});

describe("agent rows: Bob's Markdown reads as plain text", () => {
  const item = (summary: string): AgentItem => ({
    kind: "agent",
    key: "agent:c1",
    agent: "detective",
    callId: "c1",
    status: "done",
    detail: "",
    summary,
    cost: 0,
    recorded: true,
    startedAt: "",
    finishedAt: "",
  });

  it("[`app.py`](app.py:214) shows as app.py:214, never as a link or raw Markdown", () => {
    const { container } = render(<AgentRow item={item("Root cause in [`app.py`](app.py:214): the cap ignores earlier refunds")} reducedMotion />);
    expect(container.textContent).toContain("Root cause in app.py:214: the cap ignores earlier refunds");
    expect(container.textContent).not.toContain("[`app.py`](app.py:214)");
    expect(container.textContent).not.toContain("`");
    expect(container.querySelector("a")).toBeNull();
  });

  it("Markdown around HTML still renders as text only", () => {
    const { container } = render(<AgentRow item={item("[`<img src=x onerror=alert(1)>`](app.py:1)")} reducedMotion />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)> (app.py:1)");
  });
});
