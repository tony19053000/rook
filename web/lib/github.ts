// Connect GitHub (ROOK-031, 02 §11, 04 §3.3): the install URL the server hands out, and the setup return.
//
// "Connect GitHub" asks the server for the install URL (GET /github/install-url, it carries a one-time `state`
// bound to the signed-in user) and sends the browser there, only when it is really GitHub's install page.
// GitHub then sends the browser to the Setup URL, `/github/setup?installation_id=…&setup_action=…&state=…`
// (plus `code` when the App asks for user authorization), and that page passes the query to
// GET /github/callback with the user's token. The server verifies everything; the web only forwards.

import type { ApiClient } from "./api";

export const SETUP_PATH = "/github/setup";

/** `https://github.com/apps/<slug>/installations/new?state=…` and nothing else (no open redirect). */
export function isInstallUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  return (
    url.protocol === "https:" &&
    url.hostname === "github.com" &&
    url.port === "" &&
    url.username === "" &&
    url.password === "" &&
    /^\/apps\/[a-z0-9][a-z0-9-]{0,99}\/installations\/new$/.test(url.pathname) &&
    /^[A-Za-z0-9_-]{20,100}$/.test(url.searchParams.get("state") ?? "")
  );
}

export interface SetupParams {
  installation_id: string;
  state: string;
  setup_action?: string;
  code?: string;
}

/** The setup query GitHub sends back, checked; `null` when this is not a (valid) setup return. */
export function setupParams(search: string): SetupParams | null {
  const params = new URLSearchParams(search);
  const installation = params.get("installation_id") ?? "";
  const state = params.get("state") ?? "";
  if (!/^[1-9]\d{0,15}$/.test(installation) || !/^[A-Za-z0-9_-]{20,100}$/.test(state)) return null;
  const out: SetupParams = { installation_id: installation, state };
  const action = params.get("setup_action");
  if (action && /^[a-z_]{1,20}$/.test(action)) out.setup_action = action;
  const code = params.get("code");
  if (code && /^[A-Za-z0-9_-]{1,200}$/.test(code)) out.code = code;
  return out;
}

/** Whether a URL query is a GitHub setup return (GitHub may be pointed at the site root). */
export function isSetupReturn(search: string): boolean {
  return new URLSearchParams(search).has("installation_id");
}

/** Ask for the install URL and go there. An error message, or null once the browser is leaving. */
export async function startGithubConnect(
  api: Pick<ApiClient, "githubInstallUrl">,
  go: (url: string) => void,
): Promise<string | null> {
  try {
    const { url } = await api.githubInstallUrl();
    if (!isInstallUrl(url)) return "The server sent an unexpected GitHub link.";
    go(url);
    return null;
  } catch (e) {
    const status = typeof e === "object" && e !== null && "status" in e ? (e as { status: unknown }).status : null;
    if (status === 401) return "Sign in first, then connect GitHub.";
    if (status === 501) return "GitHub is not set up on this server.";
    return "Could not start the GitHub connection. Try again.";
  }
}

const finished = new Map<string, Promise<string | null>>();

/**
 * Send the setup return to the server once per `state` (the state is one-time; React may run effects twice).
 * An error message, or null when GitHub is connected.
 */
export function finishGithubConnect(api: Pick<ApiClient, "githubCallback">, params: SetupParams): Promise<string | null> {
  const known = finished.get(params.state);
  if (known !== undefined) return known;
  const pending = api.githubCallback(params).then(
    () => null,
    (e: unknown) => {
      const status = typeof e === "object" && e !== null && "status" in e ? (e as { status: unknown }).status : null;
      if (status === 401) return "Sign in to Rook first, then connect GitHub again.";
      if (status === 501) return "GitHub is not set up on this server.";
      if (status === 400 || status === 403) return "Rook could not verify this GitHub installation. Connect GitHub again from Rook.";
      if (status === 429) return "Too many GitHub connection attempts. Try again later.";
      return "Could not finish connecting GitHub. Try again.";
    },
  );
  finished.set(params.state, pending);
  return pending;
}
