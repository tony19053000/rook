// A reconnecting client for GET /api/v1/runs/{id}/events?after=N (02 §11).
//
// It uses fetch + a streaming body instead of EventSource because EventSource can't send the
// `Authorization: Bearer <Supabase JWT>` header (03 §5). On every (re)connect it asks for the events after
// the last seq it has seen, and it drops any event whose seq it has already delivered, so a replayed tail
// is never applied twice.

import { runEventsUrl } from "./api";
import { parseEventJson, type RookEvent } from "./events";

// ---------------------------------------------------------------------------
// SSE wire format (text/event-stream)
// ---------------------------------------------------------------------------

export interface SseMessage {
  event: string;
  data: string;
  id: string | null;
}

/**
 * Incremental parser for the text/event-stream format. Feed it decoded text chunks in order; it returns
 * the messages completed by each chunk. Handles CRLF/CR/LF line ends, comments and multi-line data.
 */
export class SseParser {
  private buffer = "";
  private data: string[] = [];
  private event = "";
  private id: string | null = null;
  private skipLf = false;

  feed(chunk: string): SseMessage[] {
    this.buffer += chunk;
    const out: SseMessage[] = [];
    for (;;) {
      // The "\n" of a "\r\n" split across two chunks.
      if (this.skipLf && this.buffer.length > 0) {
        if (this.buffer.startsWith("\n")) this.buffer = this.buffer.slice(1);
        this.skipLf = false;
      }
      const match = /\r|\n/.exec(this.buffer);
      if (match === null) break;
      const line = this.buffer.slice(0, match.index);
      this.buffer = this.buffer.slice(match.index + 1);
      this.skipLf = match[0] === "\r";
      const message = this.line(line);
      if (message !== null) out.push(message);
    }
    return out;
  }

  private line(line: string): SseMessage | null {
    if (line === "") {
      if (this.data.length === 0) {
        this.event = "";
        return null;
      }
      const message = { event: this.event || "message", data: this.data.join("\n"), id: this.id };
      this.data = [];
      this.event = "";
      return message;
    }
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") this.data.push(value);
    else if (field === "event") this.event = value;
    else if (field === "id" && !value.includes("\0")) this.id = value;
    return null;
  }
}

// ---------------------------------------------------------------------------
// Reconnecting run stream
// ---------------------------------------------------------------------------

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed";

export interface StreamStatusInfo {
  /** Consecutive failed attempts so far (0 while connected). */
  attempt: number;
  /** Delay before the next attempt, when reconnecting. */
  retryInMs?: number;
  /** HTTP status of a refused connection (401/403/404 end the stream). */
  httpStatus?: number;
  /** Why the stream closed: the run finished, the server refused it, or `close()` was called. */
  reason?: "finished" | "refused" | "closed";
}

export interface RunStreamOptions {
  /** The API origin, e.g. NEXT_PUBLIC_API_URL. */
  baseUrl: string;
  runId: string;
  /** Resume after this seq (0 = from the start). */
  after?: number;
  onEvent: (event: RookEvent) => void;
  onStatus?: (status: StreamStatus, info: StreamStatusInfo) => void;
  /** Returns the Supabase JWT, or null for a guest (the guest cookie is sent with credentials). */
  getToken?: () => string | null | Promise<string | null>;
  fetch?: typeof fetch;
  initialDelayMs?: number;
  maxDelayMs?: number;
}

export interface RunStream {
  /** Stop for good and abort the current request. */
  close(): void;
  /** Skip the backoff wait and reconnect now (the "Retry" in the Reconnecting… banner). */
  reconnectNow(): void;
  /** The last seq delivered to `onEvent`. */
  lastSeq(): number;
}

/** Responses that won't change by retrying: auth failures and a missing run. */
const FATAL_STATUSES = new Set([400, 401, 403, 404, 410]);

export function backoffDelay(attempt: number, initialMs: number, maxMs: number): number {
  return Math.min(maxMs, initialMs * 2 ** Math.max(0, attempt - 1));
}

export function openRunStream(options: RunStreamOptions): RunStream {
  const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  const initialMs = options.initialDelayMs ?? 500;
  const maxMs = options.maxDelayMs ?? 10_000;
  let lastSeq = options.after ?? 0;
  let closed = false;
  let controller: AbortController | null = null;
  let wake: (() => void) | null = null;

  const status = (s: StreamStatus, info: StreamStatusInfo): void => options.onStatus?.(s, info);

  const wait = (ms: number): Promise<void> =>
    new Promise((resolve) => {
      const timer = setTimeout(done, ms);
      function done(): void {
        clearTimeout(timer);
        wake = null;
        resolve();
      }
      wake = done;
    });

  /** One connection. Returns "finished" after run.finished, "refused" on a fatal status, else "dropped". */
  async function connectOnce(onOpen: () => void): Promise<"finished" | "refused" | "dropped"> {
    controller = new AbortController();
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    const token = options.getToken ? await options.getToken() : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await doFetch(runEventsUrl(options.baseUrl, options.runId, lastSeq), {
      headers,
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      if (FATAL_STATUSES.has(response.status)) {
        status("closed", { attempt: 0, httpStatus: response.status, reason: "refused" });
        return "refused";
      }
      throw new Error(`HTTP ${response.status}`);
    }
    if (response.body === null) throw new Error("empty body");
    onOpen();
    const parser = new SseParser();
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return "dropped";
        for (const message of parser.feed(value)) {
          const event = parseEventJson(message.data);
          if (event === null || event.run_id !== options.runId || event.seq <= lastSeq) continue;
          lastSeq = event.seq;
          options.onEvent(event);
          if (closed) return "dropped";
          if (event.type === "run.finished") return "finished";
        }
      }
    } finally {
      controller.abort();
      reader.releaseLock();
    }
  }

  async function loop(): Promise<void> {
    let attempt = 0;
    while (!closed) {
      if (attempt === 0) status("connecting", { attempt });
      let outcome: "finished" | "refused" | "dropped";
      try {
        outcome = await connectOnce(() => {
          attempt = 0;
          status("open", { attempt: 0 });
        });
      } catch {
        outcome = "dropped";
      }
      if (closed) return;
      if (outcome === "refused") {
        closed = true;
        return;
      }
      if (outcome === "finished") {
        closed = true;
        status("closed", { attempt: 0, reason: "finished" });
        return;
      }
      attempt += 1;
      const delay = backoffDelay(attempt, initialMs, maxMs);
      status("reconnecting", { attempt, retryInMs: delay });
      await wait(delay);
    }
  }

  void loop();

  return {
    close() {
      if (closed) return;
      closed = true;
      controller?.abort();
      wake?.();
      status("closed", { attempt: 0, reason: "closed" });
    },
    reconnectNow() {
      wake?.();
    },
    lastSeq: () => lastSeq,
  };
}
