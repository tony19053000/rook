// Pure logic behind the pages (04 §3.2, §3.3, §3.6): the recents, the repo picker groups, the new-run body,
// and how every API failure reads. Kept free of React so it is unit-tested directly.

import { ApiError, TIMEOUT_STATUS, type ApiClient, type CreateRunBody, type RepoOption, type RunSummary } from "./api";
import { short } from "./cardText";
import type { RecentRun, RecentStatus, SidebarProps } from "@/components/Sidebar";
import { clean } from "./safeText";
import { displayName, type Session } from "./session";

/** 02 §11: `request` is at most 2000 chars. */
export const REQUEST_MAX = 2000;
export const DEFAULT_REQUEST = "Find bugs";
/** 04 §3.6, the guest limit copy; the command is shown as code. */
export const CLI_INSTALL = "uv tool install git+https://github.com/tony19053000/rook";
/** 04 §3.3: the composer note under a picked GitHub repo when the server runs it (ROOK-041). */
export const HOSTED_GITHUB_NOTE = "Runs live on Roook's server with IBM Bob · costs coins";
/** How often the recents refresh while a run is queued or running. */
export const RECENTS_POLL_MS = 5000;

// ---------------------------------------------------------------------------
// Runs and recents
// ---------------------------------------------------------------------------

export function isActive(run: Pick<RunSummary, "status">): boolean {
  return run.status === "queued" || run.status === "running";
}

/** 04 §3.1 recents dots: pulsing accent = running, green = fixed/holding, red = broken. */
export function recentStatus(run: Pick<RunSummary, "status" | "result">): RecentStatus {
  if (isActive(run)) return "running";
  if (run.result === "broken") return "broken";
  if (run.result === "fixed" || run.status === "done") return "ok";
  return "idle";
}

/** A short plain status, never colour alone (04 §3.7). */
export function runStatusText(run: Pick<RunSummary, "status" | "result">): string {
  if (run.status === "queued") return "queued";
  if (run.status === "running") return run.result === "broken" ? "rule broken" : "finding…";
  if (run.result === "broken") return "rule broken";
  if (run.result === "fixed") return "fixed";
  if (run.status === "done") return "rules held";
  return run.status; // failed | cancelled
}

export function recentFromSummary(run: RunSummary): RecentRun {
  return {
    id: run.id,
    label: `${short(run.repo.name || run.repo.ref, 40)} · ${runStatusText(run)}`,
    status: recentStatus(run),
  };
}

export function recentsFrom(runs: readonly RunSummary[]): RecentRun[] {
  return runs.map(recentFromSummary);
}

export function anyActive(runs: readonly RunSummary[]): boolean {
  return runs.some(isActive);
}

/** "just now", "5 min ago", "3 h ago", else the date (UTC, so server and browser agree). */
export function formatWhen(iso: string, now: number = Date.now()): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "";
  const minutes = Math.floor((now - at) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  return new Date(at).toISOString().slice(0, 10);
}

/** The page path of a run; the id is encoded because it came from the server. */
export function runHref(id: string): string {
  return `/runs/${encodeURIComponent(id)}`;
}

/** Coins spent by the runs started today (UTC, so the server's day and the label agree). */
export function coinsToday(runs: readonly Pick<RunSummary, "coins" | "created_at">[], now: number = Date.now()): number {
  const today = new Date(now).toISOString().slice(0, 10);
  return runs.reduce((sum, run) => (run.created_at.slice(0, 10) === today ? sum + run.coins : sum), 0);
}

/** The sidebar props every page passes to AppShell. */
export function shellProps(
  session: Session,
  runs: { runs: readonly RunSummary[]; loading: boolean },
  now: number = Date.now(),
): Pick<SidebarProps, "recents" | "userName" | "email" | "recentsLoading" | "signedIn" | "githubConnected" | "coins"> {
  return {
    recents: recentsFrom(runs.runs),
    userName: displayName(session),
    email: session.kind === "user" ? session.email : "",
    recentsLoading: runs.loading,
    signedIn: session.kind === "user",
    githubConnected: session.kind === "user" && session.githubConnected,
    coins: coinsToday(runs.runs, now),
  };
}

// ---------------------------------------------------------------------------
// Repo picker (04 §3.3)
// ---------------------------------------------------------------------------

export interface PickerGroups {
  /** "Your GitHub repositories", or null when it isn't shown (a guest, or GitHub isn't connected). */
  github: RepoOption[] | null;
  /** "Demo repositories": always shown; the only group for a guest. */
  demo: RepoOption[];
  /** Offer the "Connect GitHub" item: a signed-in user without GitHub. */
  connectGithub: boolean;
}

export function pickerGroups(repos: readonly RepoOption[], session: Session): PickerGroups {
  const demo = repos.filter((r) => r.kind === "demo");
  if (session.kind === "guest") return { github: null, demo, connectGithub: false };
  if (!session.githubConnected) return { github: null, demo, connectGithub: true };
  return { github: repos.filter((r) => r.kind === "github"), demo, connectGithub: false };
}

/** The picker's options in display order (what arrow keys move through). */
export function pickerOptions(groups: PickerGroups): RepoOption[] {
  return [...(groups.github ?? []), ...groups.demo];
}

export function repoKey(repo: Pick<RepoOption, "kind" | "ref">): string {
  return `${repo.kind}:${repo.ref}`;
}

/** The dim second line of a picker item: `private · Node.js`. */
export function repoMeta(repo: Pick<RepoOption, "private" | "language">): string {
  const parts = [repo.private ? "private" : "public"];
  if (repo.language) parts.push(short(repo.language, 30));
  return parts.join(" · ");
}

/** The picker's search: keeps the repos whose name or `owner/name` contains the query (case-insensitive). */
export function filterGroups(groups: PickerGroups, query: string): PickerGroups {
  const q = query.trim().toLowerCase();
  if (q === "") return groups;
  const hit = (r: RepoOption) => r.name.toLowerCase().includes(q) || r.ref.toLowerCase().includes(q);
  return { ...groups, github: groups.github === null ? null : groups.github.filter(hit), demo: groups.demo.filter(hit) };
}

/**
 * The composer's mode line. A user's own repo always runs Bob live; an example repo follows the server's Bob
 * mode (GET /health `bob_mode`): `replay` means recorded answers. Until the server has said, it claims neither.
 */
export function bobModeLabel(repo: Pick<RepoOption, "kind"> | null, serverMode: string | null = null): string {
  if (repo === null) return "IBM Bob";
  if (repo.kind === "github") return "IBM Bob · live";
  if (serverMode === null) return "IBM Bob";
  return serverMode === "replay" ? "IBM Bob · recorded answers" : "IBM Bob · live";
}

/** The first name for the home greeting ("Aayush Kumar" → "Aayush", an email → its local part), cleaned. */
export function firstName(session: Session): string {
  if (session.kind === "guest") return "";
  const raw = (session.name || session.email).trim();
  const first = (raw.includes("@") && !raw.includes(" ") ? raw.split("@")[0] : raw.split(/\s+/)[0]) ?? "";
  return short(first, 40);
}

/** Whether the picker may offer this repo to this session (a guest: demo only). */
export function canPick(repo: Pick<RepoOption, "kind">, session: Session): boolean {
  return repo.kind === "demo" || (session.kind === "user" && session.githubConnected);
}

/** Moves a picker selection by `delta`, wrapping; -1 (nothing yet) goes to the first or last item. */
export function moveIndex(current: number, delta: number, count: number): number {
  if (count === 0) return -1;
  if (current < 0) return delta > 0 ? 0 : count - 1;
  return (((current + delta) % count) + count) % count;
}

// ---------------------------------------------------------------------------
// New run
// ---------------------------------------------------------------------------

/** The CLI hint for a GitHub repo this server won't run (an older server, or GitHub not linked). */
export function cliHint(ref: string): string {
  return `The hosted server runs only the example repositories. Run this one with the CLI: rook run ${ref}`;
}

/** Where your own repos run (`/app`, 06 §4: hosted runs of your own repos are off). */
export const OWN_REPOS_NOTE = "Your own repos run on your machine with the CLI. Hosted runs of your own repos are turned off.";
/** 06 §4: guests get 3 runs a day. */
export const GUEST_LIMIT_NOTE = "Guests get 3 example runs a day on the hosted server. Come back tomorrow, or run Roook on your own machine.";

/**
 * The POST /runs body, or why not. A GitHub repo runs on the server only when GET /me said `can_run_github`
 * (ROOK-041); otherwise it gets the CLI hint (03 §3: guests and older servers run only the demo repos).
 */
export function newRunBody(
  repo: Pick<RepoOption, "kind" | "ref"> | null,
  text: string,
  auto: boolean,
  canRunGithub = false,
): { body: CreateRunBody } | { error: string } {
  if (repo === null) return { error: "Pick a repository first." };
  if (repo.kind === "github" && !canRunGithub) return { error: cliHint(repo.ref) };
  const request = text.trim();
  if (request.length > REQUEST_MAX) return { error: `Requests are at most ${REQUEST_MAX.toLocaleString("en-US")} characters.` };
  return { body: { repo: { kind: repo.kind, ref: repo.ref }, request, options: { auto } } };
}

export type StartOutcome =
  /** Nothing was sent: show this in the composer (no repo, too long, or the CLI hint). */
  | { kind: "hint"; message: string }
  | { kind: "started"; runId: string; href: string }
  | { kind: "error"; error: ErrorView };

/** The home composer's send: check the body, POST /runs, and say where to go or what went wrong. */
export async function startRun(
  api: Pick<ApiClient, "createRun">,
  repo: Pick<RepoOption, "kind" | "ref"> | null,
  text: string,
  auto: boolean,
  canRunGithub = false,
): Promise<StartOutcome> {
  const checked = newRunBody(repo, text, auto, canRunGithub);
  if ("error" in checked) return { kind: "hint", message: checked.error };
  try {
    const { run_id } = await api.createRun(checked.body);
    return { kind: "started", runId: run_id, href: runHref(run_id) };
  } catch (e) {
    const error = errorView(e, "create");
    // Hosted runs of your own repos are off (503): the same two commands the server names, as code.
    const ownRepoOff = error.kind === "unavailable" && repo !== null && repo.kind === "github";
    if (!ownRepoOff) return { kind: "error", error };
    // The server's sentence already spells the commands out inline; say it once, with the commands below.
    const message = /rook run/.test(error.message) ? OWN_REPOS_NOTE : error.message;
    return { kind: "error", error: { ...error, message, commands: [CLI_INSTALL, `rook run ${repo.ref}`] } };
  }
}

// ---------------------------------------------------------------------------
// Errors (04 §3.6: a clear cause and a next step)
// ---------------------------------------------------------------------------

export type ErrorAction = "create" | "repos" | "runs" | "run";

export interface ErrorView {
  /** `limit` renders the guest-limit card with the CLI install command. */
  kind: "limit" | "busy" | "unavailable" | "denied" | "missing" | "auth" | "invalid" | "network" | "server";
  title: string;
  message: string;
  retryable: boolean;
  /** Shell commands shown under the message as code (the CLI way to do what the server refused). */
  commands?: string[];
}

const TITLES: Record<ErrorAction, string> = {
  create: "Couldn't start the run",
  repos: "Couldn't load the repositories",
  runs: "Couldn't load your runs",
  run: "Couldn't open this run",
};

function detailOf(error: ApiError, fallback: string): string {
  const detail = short(error.message, 300);
  return detail && !/^HTTP \d+$/.test(detail) ? detail : fallback;
}

/** "about 2 minutes" / "about 3 hours" for a Retry-After, or "" when there is none. */
export function retryText(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return "";
  if (seconds < 90) return "Try again in a minute.";
  if (seconds < 90 * 60) return `Try again in about ${Math.round(seconds / 60)} minutes.`;
  return `Try again in about ${Math.round(seconds / 3600)} hours.`;
}

export function errorView(error: unknown, action: ErrorAction): ErrorView {
  const title = TITLES[action];
  if (!(error instanceof ApiError)) {
    return { kind: "network", title, message: "Couldn't reach the server. Check your connection and try again.", retryable: true };
  }
  switch (error.status) {
    case 429: {
      // "Guest limit …"; servers before ROOK-048 send "Demo limit …".
      if (/^(guest|demo) limit/i.test(error.message)) {
        return {
          kind: "limit",
          title: "Guest limit reached for today",
          message: `Install the CLI to run on your own repos: ${CLI_INSTALL}`,
          retryable: false,
        };
      }
      // The busy queue, the daily AI budget and the hosted-run limits: the server's own words.
      const retry = retryText(error.retryAfter);
      const fallback = `Too many requests right now. ${retry || "Wait a moment and try again."}`;
      const detail = detailOf(error, "");
      if (!detail) return { kind: "busy", title, message: fallback, retryable: true };
      // Add the Retry-After wait only when the server's words don't already say when to come back.
      const saysWhen = /try again|retry|tomorrow/i.test(detail);
      return { kind: "busy", title, message: saysWhen || !retry ? detail : `${detail}${/[.!?]$/.test(detail) ? "" : "."} ${retry}`, retryable: true };
    }
    case 503:
      return {
        kind: "unavailable",
        title: "Not available on this server",
        message: detailOf(error, "The server isn't set up to do this right now. Try an example repository."),
        retryable: false,
      };
    case 501:
      return { kind: "unavailable", title: "Not available yet", message: detailOf(error, "The server can't do this yet."), retryable: false };
    case 401:
      return { kind: "auth", title, message: "Your session expired. Sign in again, or continue as a guest.", retryable: false };
    case 403:
      return {
        kind: "denied",
        title,
        message: detailOf(
          error,
          action === "create" ? "Roook can't run this repository for you. Check that it is shared with the Roook GitHub App." : "You aren't allowed to do that.",
        ),
        retryable: false,
      };
    case 404:
      return action === "run"
        ? { kind: "missing", title, message: "This run doesn't exist, or it belongs to someone else.", retryable: false }
        : { kind: "missing", title, message: "The server doesn't know this route. Is the API URL right?", retryable: false };
    case 400:
    case 413:
    case 422:
      return { kind: "invalid", title, message: detailOf(error, "The server didn't accept this request."), retryable: false };
    default:
      return { kind: "server", title, message: `The server had a problem (HTTP ${error.status}). Try again.`, retryable: true };
  }
}

/** Every string an ErrorView shows, cleaned (the detail came from the server). */
export function cleanErrorView(view: ErrorView): ErrorView {
  return { ...view, title: clean(view.title), message: clean(view.message), commands: view.commands?.map(clean) };
}

// ---------------------------------------------------------------------------
// Deletion (ROOK-051 routes: DELETE /runs/{id}, DELETE /me/data)
// ---------------------------------------------------------------------------

export type DeleteTarget = "run" | "data";

export type DeleteOutcome =
  | { kind: "deleted" }
  /** No answer in time: the server may still be deleting (stopping a running run takes up to 30 s). */
  | { kind: "pending"; message: string }
  | { kind: "error"; message: string; retryable: boolean };

export const STILL_DELETING = "Still deleting. The server can take up to 30 seconds to stop a running run. Refresh in a moment.";

/** Statuses that mean "no answer in time", from the browser (408) or a proxy in front of the server. */
const TIMEOUT_STATUSES: readonly number[] = [TIMEOUT_STATUS, 504, 524];

/** Runs a deletion and says how it went in plain words; never throws. */
export async function runDelete(action: () => Promise<unknown>, target: DeleteTarget): Promise<DeleteOutcome> {
  try {
    await action();
    return { kind: "deleted" };
  } catch (e) {
    if (!(e instanceof ApiError)) {
      return { kind: "error", message: "Couldn't reach the server, so nothing was deleted. Check your connection and try again.", retryable: true };
    }
    if (TIMEOUT_STATUSES.includes(e.status)) return { kind: "pending", message: STILL_DELETING };
    switch (e.status) {
      case 401:
        return { kind: "error", message: "Your session expired. Sign in again, then delete.", retryable: false };
      case 403:
        return { kind: "error", message: detailOf(e, "The server refused this request. Reload the page and try again."), retryable: true };
      case 404:
        return target === "run"
          ? { kind: "error", message: "This run is already gone, or it belongs to someone else.", retryable: false }
          : { kind: "error", message: "This server can't delete account data yet. Email us and we will delete it.", retryable: false };
      case 429:
        return { kind: "error", message: `Too many requests right now. ${retryText(e.retryAfter) || "Wait a moment and try again."}`, retryable: true };
      default:
        return { kind: "error", message: `The server had a problem (HTTP ${e.status}). Try again.`, retryable: true };
    }
  }
}

// ---------------------------------------------------------------------------
// Recorded vs live (06 §4: never blur the two)
// ---------------------------------------------------------------------------

export type RunMode = "recorded" | "live";

export const RUN_MODE_TEXT: Record<RunMode, { label: string; explain: string }> = {
  recorded: {
    label: "Recorded example run",
    explain: "Bob's answers are replayed from a saved real run. The engine still runs live against the real app.",
  },
  live: { label: "Live run", explain: "Bob is called live for this run, and the engine runs against the real app." },
};

/**
 * How this run gets Bob's answers, or null while nothing says yet. The server marks every finished agent call
 * (`recorded` on agent.finished), so that decides; before the first one, only a GitHub repo is known (always
 * live, 02 §11). One recorded call is enough to call the run recorded.
 */
export function runMode(state: {
  items: readonly { kind: string; status?: string; recorded?: boolean }[];
  created: { repo: { kind: string } } | null;
}): RunMode | null {
  const finished = state.items.filter((item) => item.kind === "agent" && item.status !== "working");
  if (finished.some((item) => item.recorded === true)) return "recorded";
  if (finished.length > 0) return "live";
  return state.created?.repo.kind === "github" ? "live" : null;
}

// ---------------------------------------------------------------------------
// The live run page (04 §3.6: skeleton while loading, a "Reconnecting…" banner)
// ---------------------------------------------------------------------------

export type StreamNotice =
  | { kind: "none" }
  /** Nothing received yet: skeleton rows (a queued run waits here too). */
  | { kind: "loading" }
  | { kind: "reconnecting"; attempt: number }
  /** The server refused the stream (401/403/404): an error card instead of the run. */
  | { kind: "refused"; error: ErrorView };

export function streamNotice(
  status: "connecting" | "open" | "reconnecting" | "closed",
  info: { attempt: number; httpStatus?: number; reason?: "finished" | "refused" | "closed" },
  lastSeq: number,
): StreamNotice {
  if (status === "closed" && info.reason === "refused") {
    return { kind: "refused", error: errorView(new ApiError(info.httpStatus ?? 404, ""), "run") };
  }
  if (status === "reconnecting") return { kind: "reconnecting", attempt: info.attempt };
  if (lastSeq === 0 && status !== "closed") return { kind: "loading" };
  return { kind: "none" };
}
