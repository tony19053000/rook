import { afterEach, describe, expect, it, vi } from "vitest";
import { GUEST, displayName, getToken, oauthReturn, sessionFromUser, signInRedirect, SIGN_IN_AVAILABLE, supabaseConfig } from "./session";

const KEY = "sb_publishable_abcdefghijklmnopqrstuvwxyz";

describe("supabase config (03 §6)", () => {
  it("accepts an https project origin and a public key", () => {
    expect(supabaseConfig("https://abc.supabase.co/", KEY)).toEqual({ url: "https://abc.supabase.co", key: KEY });
    expect(supabaseConfig("http://127.0.0.1:54321", KEY)).toEqual({ url: "http://127.0.0.1:54321", key: KEY });
  });

  it("turns sign-in off for anything missing or malformed", () => {
    expect(supabaseConfig(undefined, KEY)).toBeNull();
    expect(supabaseConfig("https://abc.supabase.co", undefined)).toBeNull();
    expect(supabaseConfig("http://abc.supabase.co", KEY)).toBeNull();
    expect(supabaseConfig("https://abc.supabase.co/auth/v1", KEY)).toBeNull();
    expect(supabaseConfig("javascript:alert(1)", KEY)).toBeNull();
    expect(supabaseConfig("https://abc.supabase.co", "short")).toBeNull();
    expect(supabaseConfig("https://abc.supabase.co", "has spaces in the key value!")).toBeNull();
  });

  it("without the build-time env the site is guest-only and has no token", async () => {
    expect(SIGN_IN_AVAILABLE).toBe(false);
    expect(await getToken()).toBeNull();
  });
});

describe("session helpers", () => {
  it("names the user from Google, else the email", () => {
    const user = sessionFromUser({ email: "a@example.com", user_metadata: { full_name: "Aayush K", name: "ak" } }, true);
    expect(user).toEqual({ kind: "user", name: "Aayush K", email: "a@example.com", githubConnected: true });
    expect(displayName(sessionFromUser({ email: "a@example.com", user_metadata: {} }))).toBe("a@example.com");
    expect(displayName(sessionFromUser({ email: "a@example.com", user_metadata: { name: 7 } }))).toBe("a@example.com");
    expect(displayName(GUEST)).toBe("guest");
  });

  it("reads what Supabase put on /login", () => {
    expect(oauthReturn("?code=34e770dd-9ff9-416c-87fa-43b31d7ef225")).toEqual({ code: "34e770dd-9ff9-416c-87fa-43b31d7ef225" });
    expect(oauthReturn("?error=access_denied&error_description=User+cancelled")).toEqual({ error: "User cancelled" });
    expect(oauthReturn("")).toBeNull();
    expect(oauthReturn("?code=<script>")).toBeNull();
    expect(signInRedirect("https://rook-weld-six.vercel.app/")).toBe("https://rook-weld-six.vercel.app/login");
  });
});

// The real auth-js client in a stubbed browser: the PKCE redirect and the code exchange, with a fetch mock.
describe("Google sign-in with PKCE", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  function browser() {
    const store = new Map<string, string>();
    const localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    };
    const assign = vi.fn();
    vi.stubGlobal("localStorage", localStorage);
    vi.stubGlobal("document", { visibilityState: "visible", addEventListener: () => undefined, removeEventListener: () => undefined });
    vi.stubGlobal("window", {
      localStorage,
      location: { assign, href: "https://rook.test/login", origin: "https://rook.test" },
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    });
    return { assign, store };
  }

  it("sends the browser to Supabase with a code challenge, then exchanges the code with only the public key", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://abc.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", KEY);
    const { assign } = browser();
    const calls: { url: string; init: RequestInit }[] = [];
    const now = Math.floor(Date.now() / 1000);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        calls.push({ url, init });
        const session = {
          access_token: "header.payload.sig",
          refresh_token: "r",
          expires_in: 3600,
          expires_at: now + 3600,
          token_type: "bearer",
          user: { id: "u-1", email: "a@example.com", user_metadata: { full_name: "Aayush" }, aud: "authenticated", app_metadata: {}, created_at: "" },
        };
        return new Response(JSON.stringify(session), { status: 200, headers: { "Content-Type": "application/json" } });
      }),
    );
    vi.resetModules();
    const session = await import("./session");
    expect(session.SIGN_IN_AVAILABLE).toBe(true);

    expect(await session.signInWithGoogle("https://rook.test")).toBeNull();
    expect(assign).toHaveBeenCalledOnce();
    const target = new URL(String(assign.mock.calls[0]?.[0]));
    expect(target.origin + target.pathname).toBe("https://abc.supabase.co/auth/v1/authorize");
    expect(target.searchParams.get("provider")).toBe("google");
    expect(target.searchParams.get("redirect_to")).toBe("https://rook.test/login");
    expect(target.searchParams.get("code_challenge_method")).toBe("s256");
    expect(target.searchParams.get("code_challenge")?.length).toBeGreaterThanOrEqual(43);

    const code = "34e770dd-9ff9-416c-87fa-43b31d7ef225";
    const [first, second] = await Promise.all([session.completeSignIn(code), session.completeSignIn(code)]);
    expect(first).toBeNull();
    expect(second).toBeNull();
    const exchanges = calls.filter((c) => c.url.includes("/token"));
    expect(exchanges).toHaveLength(1); // one exchange per code, however often /login's effect runs
    const [exchange] = exchanges as [{ url: string; init: RequestInit }];
    expect(exchange.url).toBe("https://abc.supabase.co/auth/v1/token?grant_type=pkce");
    const headers = new Headers(exchange.init.headers);
    expect(headers.get("apikey")).toBe(KEY);
    expect(headers.get("authorization")).toBeNull(); // a publishable key is never sent as a bearer token
    const body = JSON.parse(String(exchange.init.body)) as { auth_code: string; code_verifier: string };
    expect(body.auth_code).toBe(code);
    expect(body.code_verifier.length).toBeGreaterThanOrEqual(43);

    expect(await session.getToken()).toBe("header.payload.sig");
  });
});
