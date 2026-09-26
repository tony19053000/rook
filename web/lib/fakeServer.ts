// A fake of GET /api/v1/runs/{id}/events?after=N that serves a recorded event log as SSE, as a `fetch`
// implementation. Used by the tests and the dev page; it never touches the network.

import type { RookEvent } from "./events";

export interface FakeEventServerOptions {
  /** Delay between two events (0 = all at once). */
  intervalMs?: number;
  /** Drop connection k after `dropAfter[k]` events, to exercise reconnect + resume. */
  dropAfter?: number[];
  /** Resend this many already-seen events on each reconnect, to exercise de-duplication. */
  overlap?: number;
  /** HTTP status to answer connection k with instead of a stream (e.g. 503, 401). */
  statuses?: Array<number | undefined>;
}

export interface FakeEventServer {
  fetch: typeof fetch;
  /** The `after` value of each request, in order. */
  afters: number[];
  /** The Authorization header of each request (null when none). */
  authorizations: Array<string | null>;
}

const encoder = new TextEncoder();

export function createFakeEventServer(events: readonly RookEvent[], options: FakeEventServerOptions = {}): FakeEventServer {
  const afters: number[] = [];
  const authorizations: Array<string | null> = [];
  const interval = options.intervalMs ?? 0;

  const fakeFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
    const connection = afters.length;
    const after = Number(url.searchParams.get("after") ?? "0");
    afters.push(after);
    authorizations.push(new Headers(init?.headers).get("Authorization"));

    const status = options.statuses?.[connection];
    if (status !== undefined) return new Response(JSON.stringify({ detail: `HTTP ${status}` }), { status });

    const overlap = connection > 0 ? (options.overlap ?? 0) : 0;
    const first = events.findIndex((e) => e.seq > after);
    const batch = first === -1 ? [] : events.slice(Math.max(0, first - overlap));
    const limit = options.dropAfter?.[connection] ?? Infinity;
    const signal = init?.signal;

    let timer: ReturnType<typeof setTimeout> | undefined;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        let sent = 0;
        const abort = () => {
          clearTimeout(timer);
          try {
            controller.error(new DOMException("aborted", "AbortError"));
          } catch {
            // already closed
          }
        };
        if (signal?.aborted) return abort();
        signal?.addEventListener("abort", abort, { once: true });
        const next = () => {
          if (signal?.aborted) return;
          if (sent >= batch.length || sent >= limit) {
            signal?.removeEventListener("abort", abort);
            controller.close();
            return;
          }
          const event = batch[sent]!;
          sent += 1;
          controller.enqueue(encoder.encode(`id: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`));
          timer = setTimeout(next, interval);
        };
        controller.enqueue(encoder.encode(": connected\n\n"));
        next();
      },
      cancel() {
        clearTimeout(timer);
      },
    });
    return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  };

  return { fetch: fakeFetch as typeof fetch, afters, authorizations };
}
