import { describe, expect, it } from "vitest";
import { ApiError, apiUrl, createApiClient, runEventsUrl } from "./api";

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
    expect(apiUrl("https://x.hf.space/", "/health")).toBe("https://x.hf.space/api/v1/health");
    expect(runEventsUrl("http://localhost:7860", "r 1/2", 42)).toBe("http://localhost:7860/api/v1/runs/r%201%2F2/events?after=42");
  });
});

describe("createApiClient", () => {
  it("calls every §11 route the web uses with the right method, path and body", async () => {
    const m = mockFetch();
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
