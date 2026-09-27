import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { config, middleware } from "../middleware";
import nextConfig from "../next.config";
import { contentSecurityPolicy, newNonce, PROXY_SECRET_HEADER, proxyRequestHeaders, SECURITY_HEADERS } from "./security";

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

  it("runs on the API and the pages, not on static files", () => {
    expect(config.matcher).toEqual(["/api/:path*", "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"]);
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
