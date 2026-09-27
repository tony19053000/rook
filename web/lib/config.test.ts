import { describe, expect, it } from "vitest";
import { apiBase, apiRewrites, devPagesEnabled, proxyTarget, siteUrl } from "./config";

describe("API base (02 §13)", () => {
  it("defaults to same-origin", () => {
    expect(apiBase(undefined)).toBe("");
    expect(apiBase("")).toBe("");
  });

  it("accepts an http(s) origin for local dev and trims the slash", () => {
    expect(apiBase("http://localhost:7860/")).toBe("http://localhost:7860");
    expect(apiBase("https://rook.example.app")).toBe("https://rook.example.app");
  });

  it("ignores anything that isn't a bare origin", () => {
    expect(apiBase("javascript:alert(1)")).toBe("");
    expect(apiBase("https://x.test/some/path")).toBe("");
  });
});

describe("same-origin proxy rewrite", () => {
  it("proxies /api/v1/* to the server origin", () => {
    const target = proxyTarget("https://203-0-113-7.sslip.io/");
    expect(target).toBe("https://203-0-113-7.sslip.io");
    expect(apiRewrites(target)).toEqual([{ source: "/api/v1/:path*", destination: "https://203-0-113-7.sslip.io/api/v1/:path*" }]);
  });

  it("no target, no rewrite", () => {
    expect(proxyTarget(undefined)).toBeNull();
    expect(apiRewrites(null)).toEqual([]);
  });

  it("refuses credentials, paths, queries and other schemes", () => {
    expect(proxyTarget("https://user:pw@x.sslip.io")).toBeNull();
    expect(proxyTarget("https://x.sslip.io/api")).toBeNull();
    expect(proxyTarget("https://x.sslip.io?a=1")).toBeNull();
    expect(proxyTarget("ftp://x.sslip.io")).toBeNull();
    expect(proxyTarget("not a url")).toBeNull();
  });
});

describe("dev pages", () => {
  it("exist in development and tests only", () => {
    expect(devPagesEnabled("development")).toBe(true);
    expect(devPagesEnabled("test")).toBe(true);
    expect(devPagesEnabled("production")).toBe(false);
    expect(devPagesEnabled(undefined)).toBe(false);
  });
});

describe("site URL for OG tags", () => {
  it("prefers NEXT_PUBLIC_SITE_URL, then the Vercel production host", () => {
    expect(siteUrl("https://rook.example.com/", "x.vercel.app")?.origin).toBe("https://rook.example.com");
    expect(siteUrl(undefined, "rook-weld-six.vercel.app")?.origin).toBe("https://rook-weld-six.vercel.app");
    expect(siteUrl("", "rook-weld-six.vercel.app")?.origin).toBe("https://rook-weld-six.vercel.app");
  });

  it("is null for missing, non-https or pathful values", () => {
    expect(siteUrl(undefined, undefined)).toBeNull();
    expect(siteUrl("http://rook.example.com", undefined)).toBeNull();
    expect(siteUrl("https://rook.example.com/x", undefined)).toBeNull();
    expect(siteUrl("javascript:alert(1)", "bad host/x")).toBeNull();
  });
});
