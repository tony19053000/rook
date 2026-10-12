import * as pageStaticInfo from "next/dist/build/analysis/get-page-static-info";
import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { config, middleware } from "../middleware";
import nextConfig from "../next.config";
import { contentSecurityPolicy, newNonce, PROXY_SECRET_HEADER, proxyRequestHeaders, SECURITY_HEADERS } from "./security";

// Next's own matcher compiler (used at build time); it is exported at runtime but not in Next's type declarations.
const { getMiddlewareMatchers } = pageStaticInfo as unknown as {
  getMiddlewareMatchers: (matcher: string[], nextConfig: object) => { regexp: string }[];
};

function directives(csp: string): Map<string, string[]> {
  return new Map(csp.split("; ").map((d) => {
    const [name, ...values] = d.split(" ");
    return [name!, values];
  }));
}

describe("Content-Security-Policy (03 §8)", () => {
  it("allows scripts only with the nonce, connects only same-origin, and can't be framed", () => {
    const csp = directives(contentSecurityPolicy({ nonce: "abc", dev: false, connect: [] }));
    expect(csp.get("script-src")).toEqual(["'self'", "'nonce-abc'", "'strict-dynamic'"]);
    expect(csp.get("connect-src")).toEqual(["'self'"]);
    expect(csp.get("frame-ancestors")).toEqual(["'none'"]);
    expect(csp.get("object-src")).toEqual(["'none'"]);
    expect(csp.get("default-src")).toEqual(["'self'"]);
    expect(csp.get("script-src")).not.toContain("'unsafe-inline'");
    expect(csp.get("script-src")).not.toContain("'unsafe-eval'");
  });

  it("adds the extra API / Supabase origins, and nothing that isn't an http(s) origin", () => {
    const csp = directives(contentSecurityPolicy({
      nonce: "n", dev: false,
      connect: ["https://abc.supabase.co/some/path", "", undefined, "javascript:alert(1)", "not a url", "'unsafe-inline'"],
    }));
    expect(csp.get("connect-src")).toEqual(["'self'", "https://abc.supabase.co"]);
  });

  it("lets `next dev` eval and hot-reload", () => {
    const csp = directives(contentSecurityPolicy({ nonce: "n", dev: true, connect: ["http://localhost:7860"] }));
    expect(csp.get("script-src")).toContain("'unsafe-eval'");
    expect(csp.get("connect-src")).toEqual(["'self'", "http://localhost:7860", "ws:"]);
  });

  it("uses a fresh nonce every time", () => {
    const a = newNonce();
    expect(a).toMatch(/^[A-Za-z0-9+/]{22}==$/);
    expect(newNonce()).not.toBe(a);
  });

  it("the static headers are on every path", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toEqual([{ source: "/:path*", headers: SECURITY_HEADERS }]);
    const names = SECURITY_HEADERS.map((h) => h.key);
    expect(names).toEqual(expect.arrayContaining(["Referrer-Policy", "X-Content-Type-Options", "X-Frame-Options"]));
  });
});

describe("middleware", () => {
  it("puts the same nonce CSP on the page response and on the request Next.js renders", () => {
    const res = middleware(new NextRequest("https://rook.example.app/runs/r_abc"));
    const csp = res.headers.get("content-security-policy") ?? "";
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    expect(res.headers.get("x-middleware-request-content-security-policy")).toBe(csp);
    const other = middleware(new NextRequest("https://rook.example.app/runs/r_abc"));
    expect(other.headers.get("content-security-policy")).not.toBe(csp);
  });

  it("adds the proxy secret to API calls, replacing any the client sent, and sets no CSP there", () => {
    process.env.ROOK_PROXY_SECRET = "s".repeat(40); // a fake value for the test
    try {
      const req = new NextRequest("https://rook.example.app/api/v1/runs", { headers: { [PROXY_SECRET_HEADER]: "guess" } });
      const res = middleware(req);
      expect(res.headers.get(`x-middleware-request-${PROXY_SECRET_HEADER}`)).toBe("s".repeat(40));
      expect(res.headers.get("content-security-policy")).toBeNull();
    } finally {
      delete process.env.ROOK_PROXY_SECRET;
    }
  });

  it("redirects a GitHub setup return on / to /github/setup with the same query (06 §1)", () => {
    const query = "?installation_id=42&setup_action=install&state=" + "s".repeat(24);
    const res = middleware(new NextRequest(`https://rook.example.app/${query}`));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe(`https://rook.example.app/github/setup${query}`);
  });

  it("leaves / and other pages alone otherwise", () => {
    for (const url of ["https://rook.example.app/", "https://rook.example.app/?ref=x", "https://rook.example.app/app?installation_id=42"]) {
      const res = middleware(new NextRequest(url));
      expect(res.headers.get("location"), url).toBeNull();
      expect(res.headers.get("content-security-policy"), url).toMatch(/'nonce-/);
    }
  });

  it("runs on everything but /_next/static/ (compiled the way Next compiles it)", () => {
    const matchers = getMiddlewareMatchers(config.matcher, {}).map((m) => new RegExp(m.regexp));
    const runs = (path: string) => matchers.some((re) => re.test(path));
    for (const path of [
      "/",
      "/about",
      "/app",
      "/api/v1/runs",
      "/opengraph-image",
      "/twitter-image",
      "/sitemap.xmlx",
      "/robots.txtevil",
      "/icon.svgx",
      "/favicon.icoabc",
      "/_next/staticx",
      "/_next/imagex",
      "/sitemapxxml",
      "/sitemap.xml/x",
      // The matcher sees the raw path; these decode to pages, so they must get the CSP.
      "/_next/image",
      "/_next/image/..%2fabout",
      "/_next/image/..%2f..%2fabout",
      "/_next/image/..%2f..%2fapp",
      // Files: a CSP header on them is harmless, and nothing is skipped by a name a page could imitate.
      "/sitemap.xml",
      "/robots.txt",
      "/icon.svg",
      "/favicon.ico",
    ]) {
      expect(runs(path), `middleware runs on ${path}`).toBe(true);
    }
    for (const path of ["/_next/static/chunks/main.js", "/_next/static/css/app.css"]) {
      expect(runs(path), `middleware skips ${path}`).toBe(false);
    }
  });
});

describe("proxy secret header", () => {
  it("drops a client-sent header and sets ours when configured", () => {
    const incoming = new Headers({ [PROXY_SECRET_HEADER]: "guess", cookie: "rook_guest=x" });
    const withSecret = proxyRequestHeaders(incoming, " s3cret-value ");
    expect(withSecret.get(PROXY_SECRET_HEADER)).toBe("s3cret-value");
    expect(withSecret.get("cookie")).toBe("rook_guest=x");
    const without = proxyRequestHeaders(incoming, undefined);
    expect(without.has(PROXY_SECRET_HEADER)).toBe(false);
    expect(proxyRequestHeaders(incoming, "  ").has(PROXY_SECRET_HEADER)).toBe(false);
    expect(incoming.get(PROXY_SECRET_HEADER)).toBe("guess"); // the original is untouched
  });
});
