import { describe, expect, it } from "vitest";
import { ApiError, apiUrl, createApiClient, DELETE_TIMEOUT_MS, TIMEOUT_STATUS, retryAfterSeconds, runEventsUrl, toRepoOption, toRunDetail, toRunSummary, type RunSummary } from "./api";

const SUMMARY: RunSummary = {
  id: "r_1",
  repo: { kind: "demo", ref: "tony19053000/shop-app", name: "shop-app" },
  status: "done",
  created_at: "2026-09-26T09:00:00Z",
  finished_at: "2026-09-26T09:02:00Z",
  headline: "find bugs",
  result: "broken",
  coins: 0.12,
  last_seq: 88,
};

interface Call {
  url: string;
  method: string;
  headers: Headers;
  body: unknown;
  credentials: RequestCredentials | undefined;
}

function mockFetch(respond: (call: Call) => Response = () => Response.json({ ok: true })) {
  const calls: Call[] = [];
  const fetch: typeof globalThis.fetch = async (input, init) => {
    const call: Call = {
      url: String(input),
      method: init?.method ?? "GET",
      headers: new Headers(init?.headers),
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
      credentials: init?.credentials,
    };
    calls.push(call);
    return respond(call);
  };
  return { fetch, calls };
}

describe("URLs", () => {
  it("adds /api/v1 to the origin and trims trailing slashes", () => {
    expect(apiUrl("https://x.sslip.io/", "/health")).toBe("https://x.sslip.io/api/v1/health");
    expect(runEventsUrl("http://localhost:7860", "r 1/2", 42)).toBe("http://localhost:7860/api/v1/runs/r%201%2F2/events?after=42");
  });
});

describe("createApiClient", () => {
  it("calls every §11 route the web uses with the right method, path and body", async () => {
    const m = mockFetch((call) => (call.url.endsWith("/runs/r_1") ? Response.json({ run: SUMMARY, counterexamples: [] }) : Response.json({ ok: true })));
    const api = createApiClient({ baseUrl: "https://api.test", fetch: m.fetch });
    await api.health();
    await api.me();
    await api.repos();
    await api.createRun({ repo: { kind: "demo", ref: "shop-app" }, request: "find bugs", options: { auto: true } });
    await api.listRuns();
    await api.getRun("r_1");
    await api.answer("r_1", "q_1", ["rule_a"]);
    await api.chat("r_1", "why?");
    await api.cancel("r_1");
    await api.replayCounterexample("r_1_cx_001");
    await api.githubInstallUrl();
    await api.githubCallback({ installation_id: "42", state: "s".repeat(43), setup_action: "install" });
    expect(m.calls.map((c) => `${c.method} ${c.url.replace("https://api.test/api/v1", "")}`)).toEqual([
      "GET /health",
      "GET /me",
      "GET /repos",
      "POST /runs",
      "GET /runs",
      "GET /runs/r_1",
      "POST /runs/r_1/answers",
      "POST /runs/r_1/chat",
      "POST /runs/r_1/cancel",
      "POST /counterexamples/r_1_cx_001/replay",
      "GET /github/install-url",
      `GET /github/callback?installation_id=42&state=${"s".repeat(43)}&setup_action=install`,
    ]);
    expect(m.calls[3]!.body).toEqual({ repo: { kind: "demo", ref: "shop-app" }, request: "find bugs", options: { auto: true } });
    expect(m.calls[6]!.body).toEqual({ question_id: "q_1", answer: ["rule_a"] });
    expect(m.calls[7]!.body).toEqual({ text: "why?" });
    expect(m.calls[8]!.body).toBeUndefined();
    expect(m.calls[3]!.headers.get("Content-Type")).toBe("application/json");
    expect(m.calls.every((c) => c.credentials === "include")).toBe(true);
  });

  it("sends the Bearer token when signed in, and none for a guest", async () => {
    const m = mockFetch();
    let token: string | null = "jwt-1";
    const api = createApiClient({ baseUrl: "https://api.test", fetch: m.fetch, getToken: () => token });
    await api.me();
    token = null;
    await api.repos();
    expect(m.calls[0]!.headers.get("Authorization")).toBe("Bearer jwt-1");
    expect(m.calls[1]!.headers.has("Authorization")).toBe(false);
  });

  it("returns the parsed body", async () => {
    const m = mockFetch(() => Response.json({ run_id: "r_9" }));
    const api = createApiClient({ baseUrl: "https://api.test", fetch: m.fetch });
    await expect(api.createRun({ repo: { kind: "demo", ref: "x" }, request: "", options: {} })).resolves.toEqual({ run_id: "r_9" });
  });

  it("throws ApiError with FastAPI's detail", async () => {
    const m = mockFetch(() => Response.json({ detail: "Demo limit reached for today." }, { status: 429 }));
    const api = createApiClient({ baseUrl: "https://api.test", fetch: m.fetch });
    const error = await api.createRun({ repo: { kind: "demo", ref: "x" }, request: "", options: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 429, message: "Demo limit reached for today." });
  });

  it("falls back to the status when the error body isn't JSON", async () => {
    const m = mockFetch(() => new Response("oops", { status: 502, statusText: "Bad Gateway" }));
    const api = createApiClient({ baseUrl: "https://api.test", fetch: m.fetch });
    await expect(api.health()).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });
});

describe("pinned §11 shapes", () => {
  it("keeps a valid RunSummary as it is", () => {
    expect(toRunSummary(SUMMARY)).toEqual(SUMMARY);
  });

  it("drops a run with no id, no repo or an unknown status", () => {
    expect(toRunSummary({ ...SUMMARY, id: "" })).toBeNull();
    expect(toRunSummary({ ...SUMMARY, repo: "shop-app" })).toBeNull();
    expect(toRunSummary({ ...SUMMARY, status: "exploded" })).toBeNull();
    expect(toRunSummary(null)).toBeNull();
  });

  it("normalises loose fields: result, coins, finished_at and the repo name", () => {
    const run = toRunSummary({ ...SUMMARY, result: "maybe", coins: "lots", finished_at: 7, repo: { kind: "demo", ref: "x/y" } });
    expect(run).toMatchObject({ result: null, coins: 0, finished_at: null, repo: { kind: "demo", ref: "x/y", name: "x/y" } });
  });

  it("filters GET /runs and GET /repos down to well-formed items", async () => {
    const api = createApiClient({
      baseUrl: "",
      fetch: async (input) =>
        String(input).endsWith("/repos")
          ? Response.json([{ kind: "demo", ref: "a/shop", name: "shop", private: false, language: "Node.js" }, { kind: "svn", ref: "x" }, "junk"])
          : Response.json([SUMMARY, { id: 1 }]),
    });
    await expect(api.listRuns()).resolves.toEqual([SUMMARY]);
    await expect(api.repos()).resolves.toEqual([{ kind: "demo", ref: "a/shop", name: "shop", private: false, language: "Node.js" }]);
  });

  it("repo options default the name to the ref and never invent private", () => {
    expect(toRepoOption({ kind: "github", ref: "me/app" })).toEqual({ kind: "github", ref: "me/app", name: "me/app", private: false, language: "" });
    expect(toRepoOption({ kind: "demo", ref: "" })).toBeNull();
  });

  it("GET /runs/{id} returns {run, counterexamples} and rejects a malformed body", async () => {
    const cx = { id: "r_1_cx_001", status: "open", rule_id: "refund_le_paid", rule_text: "refunds ≤ paid", cx_id: "cx_001", steps: [] };
    expect(toRunDetail({ run: SUMMARY, counterexamples: [cx, { nope: 1 }] })).toEqual({ run: SUMMARY, counterexamples: [cx] });
    const api = createApiClient({ baseUrl: "", fetch: async () => Response.json({ run: { id: "x" } }) });
    await expect(api.getRun("x")).rejects.toMatchObject({ status: 502 });
  });

  it("same-origin: an empty base gives /api/v1 paths", () => {
    expect(apiUrl("", "/runs")).toBe("/api/v1/runs");
    expect(runEventsUrl("", "r_1", 3)).toBe("/api/v1/runs/r_1/events?after=3");
  });
});

describe("Retry-After", () => {
  it("reads delta seconds and ignores anything else", () => {
    expect(retryAfterSeconds("60")).toBe(60);
    expect(retryAfterSeconds(" 3600 ")).toBe(3600);
    expect(retryAfterSeconds("Wed, 21 Oct 2026 07:28:00 GMT")).toBeNull();
    expect(retryAfterSeconds("-5")).toBeNull();
    expect(retryAfterSeconds(null)).toBeNull();
  });

  it("puts it on the ApiError of a 429", async () => {
    const api = createApiClient({
      baseUrl: "",
      fetch: async () => Response.json({ detail: "The server is busy; try again in a few minutes" }, { status: 429, headers: { "Retry-After": "60" } }),
    });
    await expect(api.createRun({ repo: { kind: "demo", ref: "x" }, request: "", options: {} })).rejects.toMatchObject({
      status: 429,
      retryAfter: 60,
      message: "The server is busy; try again in a few minutes",
    });
  });
});

describe("deletion (ROOK-051 routes)", () => {
  it("deleteRun sends DELETE /runs/{id} with the token and the guest cookie, and no body", async () => {
    const { fetch, calls } = mockFetch(() => Response.json({ ok: true }));
    const api = createApiClient({ baseUrl: "", getToken: () => "jwt-1", fetch });
    expect(await api.deleteRun("r 1/2")).toEqual({ ok: true });
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe("/api/v1/runs/r%201%2F2");
    expect(calls[0]!.method).toBe("DELETE");
    expect(calls[0]!.headers.get("Authorization")).toBe("Bearer jwt-1");
    expect(calls[0]!.credentials).toBe("include");
    expect(calls[0]!.body).toBeUndefined();
  });

  it("deleteMyData sends DELETE /me/data and returns how many runs went", async () => {
    const { fetch, calls } = mockFetch(() => Response.json({ ok: true, runs_deleted: 4 }));
    const api = createApiClient({ baseUrl: "https://api.example", getToken: () => "jwt-1", fetch });
    expect(await api.deleteMyData()).toEqual({ ok: true, runs_deleted: 4 });
    expect(calls[0]!.url).toBe("https://api.example/api/v1/me/data");
    expect(calls[0]!.method).toBe("DELETE");
  });

  it("a refusal carries the server's reason: 404 for a run that isn't yours, 403 for a cross-site request", async () => {
    const notFound = createApiClient({ baseUrl: "", fetch: mockFetch(() => Response.json({ detail: "Run not found" }, { status: 404 })).fetch });
    await expect(notFound.deleteRun("r_x")).rejects.toMatchObject({ status: 404, message: "Run not found" });
    const crossSite = createApiClient({ baseUrl: "", fetch: mockFetch(() => Response.json({ detail: "Cross-site request refused" }, { status: 403 })).fetch });
    await expect(crossSite.deleteMyData()).rejects.toMatchObject({ status: 403, message: "Cross-site request refused" });
  });

  it("gives up after the delete timeout with a 408 ApiError (the server may still be deleting)", async () => {
    const hanging: typeof globalThis.fetch = (_input, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    const api = createApiClient({ baseUrl: "", fetch: hanging, deleteTimeoutMs: 10 });
    const error = await api.deleteRun("r_1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(TIMEOUT_STATUS);
    expect(DELETE_TIMEOUT_MS).toBeGreaterThan(30_000); // longer than the server's 30 s to stop a running run
  });

  it("a network failure is not a timeout: the original error comes through", async () => {
    const api = createApiClient({ baseUrl: "", fetch: async () => Promise.reject(new TypeError("offline")), deleteTimeoutMs: 1000 });
    await expect(api.deleteRun("r_1")).rejects.toBeInstanceOf(TypeError);
  });

  it("other requests carry no abort signal", async () => {
    let signal: AbortSignal | null | undefined;
    const fetch: typeof globalThis.fetch = async (_input, init) => {
      signal = init?.signal;
      return Response.json([]);
    };
    await createApiClient({ baseUrl: "", fetch }).listRuns();
    expect(signal).toBeUndefined();
  });
});
