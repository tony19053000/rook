// Security headers for the web app (03 §8) and the proxy-secret header for `/api/v1/*` (02 §13, §14).
// Pure functions: middleware.ts calls them per request, the tests call them directly.

/** The header the Vercel middleware adds to every proxied API request; the server trusts the client IP in
 *  X-Forwarded-For only when it carries the shared ROOK_PROXY_SECRET (03 §8). */
export const PROXY_SECRET_HEADER = "x-rook-proxy-secret";

export interface CspOptions {
  /** A fresh random value per response; Next.js puts it on every script it renders. */
  nonce: string;
  /** `next dev` needs eval (React debugging) and a websocket (hot reload). */
  dev: boolean;
  /** Extra origins the browser may call: NEXT_PUBLIC_API_URL in local dev, and the Supabase origin (token exchange and refresh). */
  connect: (string | undefined)[];
}

/** An http(s) origin, or null (paths, other schemes and junk are dropped, never put in the policy). */
function origin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" || url.protocol === "http:" ? url.origin : null;
  } catch {
    return null;
  }
}

/**
 * The Content-Security-Policy for pages. Scripts run only with the per-response nonce ('strict-dynamic' lets
 * those scripts load Next's chunks), so no injected script can run; styles allow inline (React style attributes
 * and next/font); the API is same-origin through the rewrite, so connect-src is 'self' plus the extras.
 */
export function contentSecurityPolicy({ nonce, dev, connect }: CspOptions): string {
  const connectSrc = ["'self'", ...connect.map(origin).filter((o): o is string => o !== null)];
  if (dev) connectSrc.push("ws:");
  const directives: [string, string[]][] = [
    ["default-src", ["'self'"]],
    ["script-src", ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", ...(dev ? ["'unsafe-eval'"] : [])]],
    ["style-src", ["'self'", "'unsafe-inline'"]],
    ["img-src", ["'self'", "data:", "blob:"]],
    ["font-src", ["'self'"]],
    ["connect-src", [...new Set(connectSrc)]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'self'"]],
    ["form-action", ["'self'"]],
    ["frame-ancestors", ["'none'"]],
  ];
  return directives.map(([name, values]) => `${name} ${values.join(" ")}`).join("; ");
}

/** A base64 nonce from 16 random bytes (Web Crypto: works in the Edge runtime and in Node). */
export function newNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

/** The static headers for every response (next.config.ts `headers()`); the CSP is per request (middleware). */
export const SECURITY_HEADERS: { key: string; value: string }[] = [
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
];

/**
 * The request headers for a proxied API call: never the client's own proxy-secret header, plus ours when
 * ROOK_PROXY_SECRET is set (a server-only Vercel env var, never NEXT_PUBLIC_).
 */
export function proxyRequestHeaders(incoming: Headers, secret: string | undefined): Headers {
  const headers = new Headers(incoming);
  headers.delete(PROXY_SECRET_HEADER);
  const value = (secret ?? "").trim();
  if (value !== "") headers.set(PROXY_SECRET_HEADER, value);
  return headers;
}
