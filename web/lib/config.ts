// Where the browser sends API calls (02 §13). In production NEXT_PUBLIC_API_URL is unset (or the web origin
// itself) and calls go same-origin to `/api/v1/*`, which the rewrite in next.config.ts proxies to the Space,
// so the `rook_guest` cookie stays first-party. In local dev it can point straight at the server.

/** The API base for createApiClient / useRunStream: "" means same-origin. */
export function apiBase(value: string | undefined = process.env.NEXT_PUBLIC_API_URL): string {
  const base = (value ?? "").trim().replace(/\/+$/, "");
  return /^https?:\/\/[^\s/]+$/i.test(base) ? base : "";
}

/**
 * The rewrite target for `/api/v1/*` (the Hugging Face Space origin), read at build time from
 * ROOK_API_PROXY_TARGET. Only an http(s) origin with no path, query or credentials is accepted; anything
 * else means "no proxy" (null).
 */
export function proxyTarget(value: string | undefined): string | null {
  const raw = (value ?? "").trim();
  if (raw === "") return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  if (url.username !== "" || url.password !== "" || url.search !== "" || url.hash !== "") return null;
  if (url.pathname !== "/" && url.pathname !== "") return null;
  return url.origin;
}

/** The rewrites next.config.ts installs: `/api/v1/*` → `<target>/api/v1/*`, or none without a target. */
export function apiRewrites(target: string | null): { source: string; destination: string }[] {
  return target === null ? [] : [{ source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` }];
}

/** The /dev/* story pages exist only in development (`next dev`). */
export function devPagesEnabled(nodeEnv: string | undefined): boolean {
  return nodeEnv === "development" || nodeEnv === "test";
}
