// Where the browser keeps the Supabase session (03 §6), and a cheap "is someone signed in here?" check that
// needs no auth library. lib/session.ts gives this key to auth-js; the site header's "Open workspace" hint
// (components/site/AccountHint.tsx) reads it without loading auth-js. It is a hint only: /app does the real check.

export const AUTH_STORAGE_KEY = "rook-auth";

/** True when `storage` holds a parsable session with a non-empty refresh token. Never throws. */
export function hasStoredSession(storage: Pick<Storage, "getItem"> | null | undefined): boolean {
  try {
    const raw = storage?.getItem(AUTH_STORAGE_KEY);
    if (!raw) return false;
    const value: unknown = JSON.parse(raw);
    if (value === null || typeof value !== "object") return false;
    const token = (value as { refresh_token?: unknown }).refresh_token;
    return typeof token === "string" && token.length > 0;
  } catch {
    return false;
  }
}

/** The browser's localStorage, or null on the server or when the browser blocks it. */
export function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
