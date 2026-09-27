// Client for the server API (docs/02_ARCHITECTURE.md §11, CONTRACT), base `/api/v1`.
// Only the routes the web app calls are here; the CLI auth, device-code, GitHub token and webhook routes
// are for other clients.

import type { SetupParams } from "./github";

export const API_PREFIX = "/api/v1";

export interface Health {
  ok: boolean;
  version: string;
  bob_mode: string;
  /** The request came through the web proxy with its ROOK_PROXY_SECRET header (02 §11). */
  proxied: boolean;
}

export interface Me {
  id: string;
  email: string;
  github_connected: boolean;
  /** The server runs this user's own GitHub repos (ROOK-041). Missing on older servers: treat as false. */
  can_run_github?: boolean;
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

/** Run status (02 §11 pinned shapes). */
export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export const RUN_STATUSES: readonly RunStatus[] = ["queued", "running", "done", "failed", "cancelled"];

export interface RunRepo {
  kind: RepoKind;
  ref: string;
  name: string;
}

/** `RunSummary` (02 §11): each item of `GET /runs` (newest first, at most 50) and `run` in `GET /runs/{id}`. */
export interface RunSummary {
  id: string;
  repo: RunRepo;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  /** The run's request (or the repo name when empty), at most 120 chars. */
  headline: string;
  /** `broken` while a counterexample is open, `fixed` when every one is fixed or verified. */
  result: "broken" | "fixed" | null;
  coins: number;
  last_seq: number;
}

export type RunListItem = RunSummary;

export type CounterexampleStatus = "open" | "fixed" | "verified";

/** One item of `counterexamples[]` in `GET /runs/{id}`: the §7.8 export plus the stored status. */
export interface CounterexampleRecord {
  /** `<run_id>_<cx_id>`, the id `POST /counterexamples/{id}/replay` takes. */
  id: string;
  status: CounterexampleStatus;
  rule_id: string;
  rule_text: string;
  cx_id: string;
  rule: unknown;
  steps: unknown[];
  violated_at_step: number;
  observed: unknown;
  expected: unknown;
  reproduced: unknown;
  flaky: boolean;
  seed: number | null;
  model_hash: string;
  created_at: string;
}

export interface RunDetail {
  run: RunSummary;
  counterexamples: CounterexampleRecord[];
}

export interface Ok {
  ok: boolean;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Seconds from the `Retry-After` header (a 429), when the server sent one. */
    readonly retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  /** The API origin, e.g. NEXT_PUBLIC_API_URL; "" means same-origin (`/api/v1/…` through the proxy). */
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

/** `Retry-After` in seconds (only the delta-seconds form; the server never sends a date). */
export function retryAfterSeconds(value: string | null): number | null {
  if (value === null || !/^\d{1,9}$/.test(value.trim())) return null;
  return Number(value.trim());
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

// ---------------------------------------------------------------------------
// Response guards: a malformed item is dropped instead of crashing a page
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const str = (value: unknown): string | null => (typeof value === "string" ? value : null);
const num = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);

export function toRepoOption(value: unknown): RepoOption | null {
  if (!isRecord(value)) return null;
  const kind = value.kind;
  const ref = str(value.ref);
  if ((kind !== "github" && kind !== "demo") || ref === null || ref === "") return null;
  return {
    kind,
    ref,
    name: str(value.name) || ref,
    private: value.private === true,
    language: str(value.language) ?? "",
  };
}

export function toRunSummary(value: unknown): RunSummary | null {
  if (!isRecord(value)) return null;
  const id = str(value.id);
  const repo = isRecord(value.repo) ? value.repo : null;
  const status = value.status;
  if (id === null || id === "" || repo === null || !RUN_STATUSES.includes(status as RunStatus)) return null;
  const ref = str(repo.ref) ?? "";
  const result = value.result === "broken" || value.result === "fixed" ? value.result : null;
  return {
    id,
    repo: { kind: repo.kind === "github" ? "github" : "demo", ref, name: str(repo.name) || ref },
    status: status as RunStatus,
    created_at: str(value.created_at) ?? "",
    finished_at: str(value.finished_at),
    headline: str(value.headline) ?? "",
    result,
    coins: num(value.coins),
    last_seq: num(value.last_seq),
  };
}

function list<T>(value: unknown, guard: (item: unknown) => T | null): T[] {
  if (!Array.isArray(value)) return [];
  return value.map(guard).filter((item): item is T => item !== null);
}

export function toRunDetail(value: unknown): RunDetail | null {
  if (!isRecord(value)) return null;
  const run = toRunSummary(value.run);
  if (run === null) return null;
  const counterexamples = list(value.counterexamples, (item) =>
    isRecord(item) && typeof item.id === "string" ? (item as unknown as CounterexampleRecord) : null,
  );
  return { run, counterexamples };
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
    if (!response.ok) {
      throw new ApiError(response.status, await errorMessage(response), retryAfterSeconds(response.headers.get("Retry-After")));
    }
    return (await response.json()) as T;
  }

  const run = (id: string) => `/runs/${encodeURIComponent(id)}`;

  return {
    health: () => request<Health>("GET", "/health"),
    me: () => request<Me>("GET", "/me"),
    repos: async () => list(await request<unknown>("GET", "/repos"), toRepoOption),
    createRun: (body: CreateRunBody) => request<{ run_id: string }>("POST", "/runs", body),
    listRuns: async () => list(await request<unknown>("GET", "/runs"), toRunSummary),
    getRun: async (id: string) => {
      const detail = toRunDetail(await request<unknown>("GET", run(id)));
      if (detail === null) throw new ApiError(502, "The server sent a run in an unexpected shape.");
      return detail;
    },
    answer: (id: string, questionId: string, answer: unknown) =>
      request<Ok>("POST", `${run(id)}/answers`, { question_id: questionId, answer }),
    chat: (id: string, text: string) => request<Ok>("POST", `${run(id)}/chat`, { text }),
    cancel: (id: string) => request<Ok>("POST", `${run(id)}/cancel`),
    replayCounterexample: (cxId: string) =>
      request<{ run_id: string }>("POST", `/counterexamples/${encodeURIComponent(cxId)}/replay`),
    githubInstallUrl: () => request<{ url: string }>("GET", "/github/install-url"),
    githubCallback: (params: SetupParams) =>
      request<Ok>("GET", `/github/callback?${new URLSearchParams({ ...params }).toString()}`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
