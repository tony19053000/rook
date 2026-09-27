// The sidebar's per-browser state (04 §3.1): whether it is collapsed to the icon rail, and the account menu's
// items. Storage can be missing or throw (private mode, blocked cookies), so every access is guarded.

export const COLLAPSED_KEY = "rook.sidebar.collapsed";

type Store = Pick<Storage, "getItem" | "setItem">;

/** The browser's localStorage, or null when it can't be used. */
export function browserStorage(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function readCollapsed(store: Store | null): boolean {
  try {
    return store?.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeCollapsed(store: Store | null, collapsed: boolean): void {
  try {
    store?.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // not saved; the sidebar still toggles for this page
  }
}

export type AccountMenuKey = "connect-github" | "github-connected" | "sign-out";

export interface AccountMenuItem {
  key: AccountMenuKey;
  label: string;
}

/** The account menu of a signed-in user: GitHub (connect, or connected) and Sign out. */
export function accountMenuItems(githubConnected: boolean): AccountMenuItem[] {
  return [
    githubConnected ? { key: "github-connected", label: "GitHub connected" } : { key: "connect-github", label: "Connect GitHub" },
    { key: "sign-out", label: "Sign out" },
  ];
}

export interface AccountActions {
  signOut: () => void | Promise<void>;
  /** Resolves to an error message, or null when the browser is leaving for GitHub. */
  connectGithub: () => Promise<string | null>;
}

/** What choosing a menu item does. An error message to show in the menu, or null. */
export async function runAccountAction(key: AccountMenuKey, actions: AccountActions): Promise<string | null> {
  if (key === "sign-out") {
    await actions.signOut();
    return null;
  }
  if (key === "connect-github") return actions.connectGithub();
  return null; // "GitHub connected" is a link to /repositories
}
