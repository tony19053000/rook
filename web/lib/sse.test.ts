import { describe, expect, it } from "vitest";
import type { RookEvent } from "./events";
import { createFakeEventServer } from "./fakeServer";
import { minishopRun } from "./fixtures/minishop";
import { SseParser, backoffDelay, openRunStream, type StreamStatus, type StreamStatusInfo } from "./sse";

const RUN = minishopRun[0]!.run_id;
const BASE = "https://api.example.test/";

describe("SseParser", () => {
  it("parses messages split across chunks, with CRLF, comments and multi-line data", () => {
    const p = new SseParser();
    expect(p.feed(": hello\r\n\r\nid: 1\r\nda")).toEqual([]);
    expect(p.feed("ta: {\"a\":\r\ndata: 1}\r")).toEqual([]);
    expect(p.feed("\n\r\n")).toEqual([{ event: "message", data: '{"a":\n1}', id: "1" }]);
    expect(p.feed("event: ping\ndata:x\n\ndata\n\n")).toEqual([
      { event: "ping", data: "x", id: "1" },
      { event: "message", data: "", id: "1" },
    ]);
  });

  it("handles a lone CR line end", () => {
    const p = new SseParser();
    expect(p.feed("data: a\r\rdata: b\r")).toEqual([{ event: "message", data: "a", id: null }]);
    expect(p.feed("\r")).toEqual([{ event: "message", data: "b", id: null }]);
  });
});

describe("backoffDelay", () => {
  it("doubles up to the cap", () => {
    expect([1, 2, 3, 4, 5, 6].map((a) => backoffDelay(a, 500, 10_000))).toEqual([500, 1000, 2000, 4000, 8000, 10_000]);
  });
});

interface Collected {
  events: RookEvent[];
  statuses: Array<[StreamStatus, StreamStatusInfo]>;
  closed: Promise<StreamStatusInfo>;
}

function collect(): Collected & { onEvent: (e: RookEvent) => void; onStatus: (s: StreamStatus, i: StreamStatusInfo) => void } {
  const events: RookEvent[] = [];
  const statuses: Array<[StreamStatus, StreamStatusInfo]> = [];
  let resolve!: (info: StreamStatusInfo) => void;
  const closed = new Promise<StreamStatusInfo>((r) => (resolve = r));
  return {
    events,
    statuses,
    closed,
    onEvent: (e) => events.push(e),
    onStatus: (s, i) => {
      statuses.push([s, i]);
      if (s === "closed") resolve(i);
    },
  };
}

describe("openRunStream", () => {
  it("delivers the whole run in order, then closes after run.finished", async () => {
    const server = createFakeEventServer(minishopRun);
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, fetch: server.fetch, onEvent: c.onEvent, onStatus: c.onStatus });
    expect(await c.closed).toMatchObject({ reason: "finished" });
    expect(c.events).toEqual(minishopRun);
    expect(server.afters).toEqual([0]);
    expect(c.statuses.map(([s]) => s)).toEqual(["connecting", "open", "closed"]);
  });

  it("reconnects with after=<last seq> and drops the replayed duplicates", async () => {
    const server = createFakeEventServer(minishopRun, { dropAfter: [40, 100, 7], overlap: 5 });
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, fetch: server.fetch, onEvent: c.onEvent, onStatus: c.onStatus, initialDelayMs: 1 });
    await c.closed;
    expect(c.events.map((e) => e.seq)).toEqual(minishopRun.map((e) => e.seq));
    // conn 1: 40 events; conn 2: 5 duplicates + 95 new -> 135; conn 3: 5 dup + 2 new -> 137.
    expect(server.afters).toEqual([0, 40, 135, 137]);
    expect(c.statuses.filter(([s]) => s === "reconnecting")).toHaveLength(3);
  });

  it("resumes from the `after` it was opened with", async () => {
    const server = createFakeEventServer(minishopRun);
    const c = collect();
    const stream = openRunStream({ baseUrl: BASE, runId: RUN, after: 300, fetch: server.fetch, onEvent: c.onEvent, onStatus: c.onStatus });
    await c.closed;
    expect(server.afters).toEqual([300]);
    expect(c.events[0]!.seq).toBe(301);
    expect(stream.lastSeq()).toBe(369);
  });

  it("backs off on server errors and network failures, then recovers", async () => {
    const server = createFakeEventServer(minishopRun, { statuses: [503, 502] });
    let calls = 0;
    const flaky: typeof fetch = (input, init) => (++calls === 1 ? Promise.reject(new TypeError("network")) : server.fetch(input, init));
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, fetch: flaky, onEvent: c.onEvent, onStatus: c.onStatus, initialDelayMs: 1 });
    await c.closed;
    expect(c.events).toHaveLength(369);
    const waits = c.statuses.filter(([s]) => s === "reconnecting").map(([, i]) => i.retryInMs);
    expect(waits).toEqual([1, 2, 4]);
  });

  it.each([401, 403, 404])("stops on HTTP %i without retrying", async (status) => {
    const server = createFakeEventServer(minishopRun, { statuses: [status] });
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, fetch: server.fetch, onEvent: c.onEvent, onStatus: c.onStatus, initialDelayMs: 1 });
    expect(await c.closed).toMatchObject({ reason: "refused", httpStatus: status });
    expect(server.afters).toHaveLength(1);
    expect(c.events).toEqual([]);
  });

  it("sends the Bearer token and the resume URL", async () => {
    const urls: string[] = [];
    const server = createFakeEventServer(minishopRun);
    const spy: typeof fetch = (input, init) => {
      urls.push(String(input));
      expect(init?.credentials).toBe("include");
      return server.fetch(input, init);
    };
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, after: 360, fetch: spy, getToken: async () => "jwt-abc", onEvent: c.onEvent, onStatus: c.onStatus });
    await c.closed;
    expect(urls).toEqual([`https://api.example.test/api/v1/runs/${RUN}/events?after=360`]);
    expect(server.authorizations).toEqual(["Bearer jwt-abc"]);
  });

  it("sends no Authorization header for a guest", async () => {
    const server = createFakeEventServer(minishopRun);
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, after: 368, fetch: server.fetch, getToken: () => null, onEvent: c.onEvent, onStatus: c.onStatus });
    await c.closed;
    expect(server.authorizations).toEqual([null]);
  });

  it("skips events of another run and malformed data", async () => {
    const encoder = new TextEncoder();
    const other = { ...minishopRun[1]!, run_id: "r_other" };
    const body = [`data: ${JSON.stringify(minishopRun[0])}`, "data: {broken", `data: ${JSON.stringify(other)}`, `data: ${JSON.stringify(minishopRun[368])}`]
      .map((l) => `${l}\n\n`)
      .join("");
    const fetchOnce: typeof fetch = async () => new Response(encoder.encode(body), { status: 200 });
    const c = collect();
    openRunStream({ baseUrl: BASE, runId: RUN, fetch: fetchOnce, onEvent: c.onEvent, onStatus: c.onStatus });
    await c.closed;
    expect(c.events.map((e) => e.seq)).toEqual([1, 369]);
  });

  it("close() aborts the stream and stops reconnecting", async () => {
    const server = createFakeEventServer(minishopRun, { intervalMs: 5 });
    const c = collect();
    const stream = openRunStream({ baseUrl: BASE, runId: RUN, fetch: server.fetch, onEvent: c.onEvent, onStatus: c.onStatus });
    await new Promise((r) => setTimeout(r, 30));
    stream.close();
    expect(await c.closed).toMatchObject({ reason: "closed" });
    const seen = c.events.length;
    await new Promise((r) => setTimeout(r, 30));
    expect(c.events.length).toBe(seen);
    expect(seen).toBeLessThan(369);
    expect(server.afters).toHaveLength(1);
  });

  it("reconnectNow() skips the backoff wait", async () => {
    const server = createFakeEventServer(minishopRun, { dropAfter: [10] });
    const c = collect();
    const stream = openRunStream({
      baseUrl: BASE,
      runId: RUN,
      fetch: server.fetch,
      initialDelayMs: 60_000,
      onEvent: c.onEvent,
      onStatus: (s, i) => {
        c.onStatus(s, i);
        if (s === "reconnecting") setTimeout(() => stream.reconnectNow(), 0);
      },
    });
    await c.closed;
    expect(server.afters).toEqual([0, 10]);
    expect(c.events).toHaveLength(369);
  });
});
