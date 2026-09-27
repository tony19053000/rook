import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { Sidebar, type RecentRun } from "./Sidebar";
import { RepositoriesView } from "./SimpleViews";
import { GUEST } from "@/lib/session";
import { accountMenuItems, COLLAPSED_KEY, readCollapsed, runAccountAction, writeCollapsed } from "@/lib/sidebarPrefs";

const html = (node: React.ReactElement) => renderToStaticMarkup(node);
const RECENTS: RecentRun[] = [
  { id: "r_9", label: "shop-app · fixed", status: "ok" },
  { id: "r_8", label: "<img src=x onerror=alert(1)> · rule broken", status: "broken" },
];

describe("sidebar: signed in", () => {
  const out = html(<Sidebar recents={RECENTS} coins={0.5} userName="Aayush" email="a@example.com" signedIn currentRunId="r_9" onToggle={() => {}} />);

  it("has the wordmark, the collapse button and the nav with New run", () => {
    expect(out).toContain(">Rook<");
    expect(out).toContain('aria-label="Close sidebar"');
    for (const href of ["/", "/counterexamples", "/rules", "/repositories"]) expect(out).toContain(`href="${href}"`);
    expect(out).toContain("New run");
  });

  it("lists the recents, links each to its run, highlights the current one, and cleans labels", () => {
    expect(out).toContain("Recents");
    expect(out).toContain('href="/runs"'); // All runs
    expect(out).toMatch(/aria-current="page"[^>]*href="\/runs\/r_9"/);
    expect(out).toContain('href="/runs/r_8"');
    expect(out).toContain("(passed)");
    expect(out).toContain("(broken)");
    expect(out).not.toContain("<img");
  });

  it("shows the account row (name, today's coins, menu button) and no Sign in", () => {
    expect(out).toContain("data-account");
    expect(out).toContain('aria-haspopup="menu"');
    expect(out).toContain(">Aayush<");
    expect(out).toMatch(/0\.50<\/span> coins today/);
    expect(out).not.toContain('href="/login"');
    expect(out).not.toContain("guest");
  });

  it("shows the skeleton while recents load and the empty line when there are none", () => {
    expect(html(<Sidebar recents={[]} coins={0} userName="A" signedIn recentsLoading />)).toContain('data-skeleton="recents"');
    expect(html(<Sidebar recents={[]} coins={0} userName="A" signedIn />)).toContain("No runs yet. Pick a repository to start.");
  });

  it("the open menu offers Connect GitHub and Sign out, or GitHub connected", () => {
    const menu = html(<Sidebar recents={[]} coins={0} userName="A" email="a@example.com" signedIn defaultMenuOpen />);
    expect(menu).toContain('role="menu"');
    expect(menu).toContain("a@example.com");
    expect(menu).toMatch(/<button[^>]*role="menuitem"[^>]*>.*Connect GitHub<\/button>/);
    expect(menu).toMatch(/<button[^>]*role="menuitem"[^>]*>.*Sign out<\/button>/);
    const linked = html(<Sidebar recents={[]} coins={0} userName="A" signedIn githubConnected defaultMenuOpen />);
    expect(linked).toContain("data-github-connected");
    expect(linked).toContain("GitHub connected");
    expect(linked).not.toContain("Connect GitHub");
  });

  it("the menu is closed by default", () => {
    expect(out).not.toContain('role="menu"');
    expect(out).toContain('aria-expanded="false"');
  });
});

describe("sidebar: signed out", () => {
  const out = html(<Sidebar recents={RECENTS} coins={0} userName="guest" />);

  it("shows a Sign in button and no recents or account row", () => {
    expect(out).toMatch(/<a[^>]*data-sign-in[^>]*href="\/login"[^>]*>Sign in<\/a>/);
    expect(out).not.toContain("Recents");
    expect(out).not.toContain("/runs/r_9");
    expect(out).not.toContain("data-account");
    expect(out).not.toContain("Sign out");
    expect(out).not.toContain("coins");
  });

  it("still has the nav", () => {
    for (const href of ["/", "/counterexamples", "/rules", "/repositories"]) expect(out).toContain(`href="${href}"`);
  });
});

describe("sidebar: collapsed rail", () => {
  it("shows icon links with labels and an Open sidebar button, no recents", () => {
    const out = html(<Sidebar recents={RECENTS} coins={0} userName="Aayush" signedIn collapsed active="rules" />);
    expect(out).toContain("data-collapsed");
    expect(out).toContain('aria-label="Open sidebar"');
    expect(out).toMatch(/aria-label="Rules"[^>]*aria-current="page"/);
    for (const label of ["New run", "Counterexamples", "Repositories"]) expect(out).toContain(`aria-label="${label}"`);
    expect(out).not.toContain("/runs/r_9");
  });

  it("a signed-out rail links to sign in", () => {
    expect(html(<Sidebar recents={[]} coins={0} userName="guest" collapsed />)).toMatch(/href="\/login"/);
  });

  it("AppShell renders the rail when started collapsed and the full sidebar otherwise", () => {
    expect(html(<AppShell collapsed>x</AppShell>)).toContain('aria-label="Open sidebar"');
    const open = html(<AppShell>x</AppShell>);
    expect(open).toContain('aria-label="Close sidebar"');
    expect(open).toContain('aria-label="Open menu"'); // the mobile drawer button
  });
});

describe("sidebar prefs (collapse is remembered per browser)", () => {
  const memory = () => {
    const data = new Map<string, string>();
    return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), data };
  };

  it("round-trips the collapsed state", () => {
    const store = memory();
    expect(readCollapsed(store)).toBe(false);
    writeCollapsed(store, true);
    expect(store.data.get(COLLAPSED_KEY)).toBe("1");
    expect(readCollapsed(store)).toBe(true);
    writeCollapsed(store, false);
    expect(readCollapsed(store)).toBe(false);
  });

  it("survives missing or throwing storage", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readCollapsed(null)).toBe(false);
    expect(readCollapsed(broken)).toBe(false);
    expect(() => writeCollapsed(broken, true)).not.toThrow();
    expect(() => writeCollapsed(null, true)).not.toThrow();
  });

  it("uses a stable key", () => {
    expect(COLLAPSED_KEY).toBe("rook.sidebar.collapsed");
  });
});

describe("account menu actions", () => {
  it("lists Connect GitHub or GitHub connected, then Sign out", () => {
    expect(accountMenuItems(false).map((i) => i.key)).toEqual(["connect-github", "sign-out"]);
    expect(accountMenuItems(true).map((i) => i.key)).toEqual(["github-connected", "sign-out"]);
  });

  it("Sign out calls the logout and nothing else", async () => {
    const signOut = vi.fn(async () => {});
    const connectGithub = vi.fn(async () => null);
    expect(await runAccountAction("sign-out", { signOut, connectGithub })).toBeNull();
    expect(signOut).toHaveBeenCalledOnce();
    expect(connectGithub).not.toHaveBeenCalled();
  });

  it("Connect GitHub starts the install flow and passes its error back", async () => {
    const signOut = vi.fn();
    const connectGithub = vi.fn(async () => "GitHub is not set up on this server.");
    expect(await runAccountAction("connect-github", { signOut, connectGithub })).toBe("GitHub is not set up on this server.");
    expect(connectGithub).toHaveBeenCalledOnce();
    expect(signOut).not.toHaveBeenCalled();
  });

  it("GitHub connected does nothing (it is a link)", async () => {
    const signOut = vi.fn();
    const connectGithub = vi.fn(async () => null);
    expect(await runAccountAction("github-connected", { signOut, connectGithub })).toBeNull();
    expect(signOut).not.toHaveBeenCalled();
    expect(connectGithub).not.toHaveBeenCalled();
  });
});

describe("Add to CI moved off the shell", () => {
  it("is not in the sidebar", () => {
    expect(html(<Sidebar recents={[]} coins={0} userName="A" signedIn />)).not.toContain("Add to CI");
  });

  it("is a small section on the Repositories page", () => {
    const out = html(<RepositoriesView session={GUEST} runs={{ runs: [], loading: false, error: null }} repos={[]} loading={false} error={null} />);
    expect(out).toContain("data-add-to-ci");
    expect(out).toContain("rook run --ci");
  });
});
