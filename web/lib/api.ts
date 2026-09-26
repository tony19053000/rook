// Client for the server API (docs/02_ARCHITECTURE.md §11, CONTRACT), base `/api/v1`.
// Only the routes the web app calls are here; the CLI auth, device-code, GitHub token and webhook routes
// are for other clients.

import type { EventDataMap } from "./events";

export const API_PREFIX = "/api/v1";

export interface Health {
  ok: boolean;
  version: string;
  bob_mode: string;
}

export interface Me {
  id: string;
  email: string;
  github_connected: boolean;
}

export type RepoKind = "github" | "demo";

export interface RepoOption {
  kind: RepoKind;
  ref: string;
  name: string;
  private: boolean;
  language: string;
}

export interface CreateRunBody {
  repo: { kind: RepoKind; ref: string };
  request: string;
  options: { auto?: boolean };
}

/** 02 §11 doesn't fix the shape of `repo` or the `status` values here, so they stay loose. */
export interface RunListItem {
  id: string;
  repo: unknown;
  status: string;
  created_at: string;
  headline: string;
}

/** 02 §11 doesn't fix the shape of `run` or of the counterexample items. */
export interface RunDetail {
  run: Record<string, unknown>;
  counterexamples: Array<Partial<EventDataMap["counterexample.saved"]> & Record<string, unknown>>;
}

export interface Ok {
  ok: boolean;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  /** The API origin, e.g. NEXT_PUBLIC_API_URL ("https://…hf.space"). */
  baseUrl: string;
  /** Returns the Supabase JWT, or null for a guest (the `rook_guest` cookie goes with credentials). */
  getToken?: () => string | null | Promise<string | null>;
  fetch?: typeof fetch;
}

export function apiUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, "")}${API_PREFIX}${path}`;
}

export function runEventsUrl(baseUrl: string, runId: string, after: number): string {
  return apiUrl(baseUrl, `/runs/${encodeURIComponent(runId)}/events?after=${after}`);
}

/** FastAPI puts the reason in `detail`; fall back to the status text. Never echoes request headers. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // not JSON
  }
  return response.statusText || `HTTP ${response.status}`;
}

export function createApiClient(options: ApiClientOptions) {
  const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);

  async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    const token = options.getToken ? await options.getToken() : null;
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const response = await doFetch(apiUrl(options.baseUrl, path), {
      method,
      headers,
      credentials: "include",
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
    return (await response.json()) as T;
  }

  const run = (id: string) => `/runs/${encodeURIComponent(id)}`;

  return {
    health: () => request<Health>("GET", "/health"),
    me: () => request<Me>("GET", "/me"),
    repos: () => request<RepoOption[]>("GET", "/repos"),
    createRun: (body: CreateRunBody) => request<{ run_id: string }>("POST", "/runs", body),
    listRuns: () => request<RunListItem[]>("GET", "/runs"),
    getRun: (id: string) => request<RunDetail>("GET", run(id)),
    answer: (id: string, questionId: string, answer: unknown) =>
      request<Ok>("POST", `${run(id)}/answers`, { question_id: questionId, answer }),
    chat: (id: string, text: string) => request<Ok>("POST", `${run(id)}/chat`, { text }),
    cancel: (id: string) => request<Ok>("POST", `${run(id)}/cancel`),
    replayCounterexample: (cxId: string) =>
      request<{ run_id: string }>("POST", `/counterexamples/${encodeURIComponent(cxId)}/replay`),
    githubInstallUrl: () => request<{ url: string }>("GET", "/github/install-url"),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
