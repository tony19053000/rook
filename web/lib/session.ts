// Who is using the web app. Until Supabase sign-in lands (ROOK-030) everyone is a guest: requests carry
// no bearer token, so the server identifies the browser by its `rook_guest` cookie (02 §11) and allows
// only the demo repos. ROOK-030 replaces `currentSession` and `getToken` with the Supabase session.

export type Session =
  | { kind: "guest" }
  | { kind: "user"; name: string; email: string; githubConnected: boolean };

/** Sign-in with Google isn't wired yet (ROOK-030), so the login page shows it as unavailable. */
export const SIGN_IN_AVAILABLE = false;

export const GUEST: Session = { kind: "guest" };

export function currentSession(): Session {
  return GUEST;
}

/** The Supabase JWT for `Authorization: Bearer …`, or null for a guest. */
export function getToken(): string | null {
  return null;
}

export function isGuest(session: Session): boolean {
  return session.kind === "guest";
}

export function displayName(session: Session): string {
  return session.kind === "guest" ? "guest" : session.name || session.email || "you";
}
