// Who is using the web app (03 §6): a guest (no bearer token; the server knows the browser by its `rook_guest`
// cookie and allows only the demo repos) or a user signed in with Google through Supabase (OAuth with PKCE).
// The browser holds only the public Supabase key; the server verifies the access token on every call.

import { GoTrueClient, type User } from "@supabase/auth-js";

export type Session =
  | { kind: "guest" }
  | { kind: "user"; name: string; email: string; githubConnected: boolean };

export const GUEST: Session = { kind: "guest" };

export interface SupabaseConfig {
  /** The project origin, e.g. https://abc.supabase.co. */
  url: string;
  /** The public key (`sb_publishable_…` or a legacy anon JWT), sent as the `apikey` header. */
  key: string;
}

/** The Supabase settings, or null (sign-in off) when either is missing or malformed. */
export function supabaseConfig(url: string | undefined, key: string | undefined): SupabaseConfig | null {
  const k = (key ?? "").trim();
  if (!/^[A-Za-z0-9._-]{20,}$/.test(k)) return null;
  let parsed: URL;
  try {
    parsed = new URL((url ?? "").trim());
  } catch {
    return null;
  }
  const local = parsed.protocol === "http:" && (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1");
  if (parsed.protocol !== "https:" && !local) return null;
  if (parsed.pathname !== "/" || parsed.search || parsed.hash || parsed.username || parsed.password) return null;
  return { url: parsed.origin, key: k };
}

// NEXT_PUBLIC_* values are inlined at build time, so they must be read with these literal names.
const CONFIG = supabaseConfig(process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);

/** Google sign-in needs the Supabase URL and public key at build time; without them everyone is a guest. */
export const SIGN_IN_AVAILABLE = CONFIG !== null;

let client: GoTrueClient | null = null;

/** The browser's Supabase auth client (one per page load), or null on the server or without config. */
export function authClient(): GoTrueClient | null {
  if (CONFIG === null || typeof window === "undefined") return null;
  client ??= new GoTrueClient({
    url: `${CONFIG.url}/auth/v1`,
    // Only `apikey`: the new publishable keys are not JWTs, so they never go in Authorization.
    headers: { apikey: CONFIG.key },
    storageKey: "rook-auth",
    flowType: "pkce",
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false, // /login exchanges the code itself (completeSignIn)
  });
  return client;
}

/** The Supabase access token for `Authorization: Bearer …` (refreshed when needed), or null for a guest. */
export async function getToken(): Promise<string | null> {
  const auth = authClient();
  if (auth === null) return null;
  const { data } = await auth.getSession();
  return data.session?.access_token ?? null;
}

function metaString(meta: Record<string, unknown> | undefined, key: string): string {
  const value = meta?.[key];
  return typeof value === "string" ? value.trim() : "";
}

/** The signed-in user as the UI sees them: the Google name, else the email. */
export function sessionFromUser(user: Pick<User, "email" | "user_metadata">, githubConnected = false): Session {
  const meta = user.user_metadata as Record<string, unknown> | undefined;
  const email = user.email ?? "";
  const name = metaString(meta, "full_name") || metaString(meta, "name") || email;
  return { kind: "user", name, email, githubConnected };
}

/** Where Google sends the browser back: /login on this origin (in the Supabase redirect allowlist). */
export function signInRedirect(origin: string): string {
  return `${origin.replace(/\/+$/, "")}/login`;
}

export type OAuthReturn = { code: string } | { error: string } | null;

/** What Supabase put on /login's query: a PKCE `code`, an error, or nothing (a normal visit). */
export function oauthReturn(search: string): OAuthReturn {
  const params = new URLSearchParams(search);
  const error = params.get("error_description") || params.get("error");
  if (error) return { error: error.slice(0, 200) };
  const code = params.get("code");
  return code && /^[A-Za-z0-9-]{8,128}$/.test(code) ? { code } : null;
}

/** Start Google sign-in: auth-js stores the PKCE verifier and navigates to Supabase. An error message, or null. */
export async function signInWithGoogle(origin: string): Promise<string | null> {
  const auth = authClient();
  if (auth === null) return "Google sign-in is not configured on this site.";
  const { error } = await auth.signInWithOAuth({ provider: "google", options: { redirectTo: signInRedirect(origin) } });
  return error ? "Could not start Google sign-in. Try again." : null;
}

// One exchange per code: React may run the /login effect twice, and a code can be used only once.
const exchanges = new Map<string, Promise<string | null>>();

/** Finish sign-in on /login: trade the code (and the stored verifier) for a session. An error message, or null. */
export function completeSignIn(code: string): Promise<string | null> {
  const known = exchanges.get(code);
  if (known !== undefined) return known;
  const auth = authClient();
  const failed = "Sign-in did not complete. Try again.";
  const pending: Promise<string | null> =
    auth === null
      ? Promise.resolve("Google sign-in is not configured on this site.")
      : auth.exchangeCodeForSession(code).then(
          (result) => (result.error ? failed : null),
          () => failed,
        );
  exchanges.set(code, pending);
  return pending;
}

/** Sign out in this browser only (the CLI keeps its own session), then reload as a guest. */
export async function signOut(): Promise<void> {
  await authClient()?.signOut({ scope: "local" });
}

export async function signOutAndReload(): Promise<void> {
  await signOut();
  window.location.assign("/");
}

export function isGuest(session: Session): boolean {
  return session.kind === "guest";
}

export function displayName(session: Session): string {
  return session.kind === "guest" ? "guest" : session.name || session.email || "you";
}
