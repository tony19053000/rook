import { NextResponse, type NextRequest } from "next/server";
import { apiBase } from "./lib/config";
import { isSetupReturn, SETUP_PATH } from "./lib/github";
import { contentSecurityPolicy, newNonce, proxyRequestHeaders } from "./lib/security";

// Per request (03 §8, 02 §13):
// - `/api/v1/*` goes on to the rewrite in next.config.ts (a proxy to the Roook server) with the shared
//   ROOK_PROXY_SECRET header, so the server can trust the client IP Vercel put in X-Forwarded-For.
// - Pages get a nonce-based Content-Security-Policy. Next.js reads the nonce from the request's CSP header and
//   puts it on its scripts, which is why the pages render per request (see app/layout.tsx).
// - A GitHub App setup return that lands on the site root goes to /github/setup with the same query (06 §1),
//   as a plain redirect so it works without JS.
export function middleware(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  if (pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers: proxyRequestHeaders(request.headers, process.env.ROOK_PROXY_SECRET) } });
  }
  if (pathname === "/" && isSetupReturn(search)) {
    const target = request.nextUrl.clone();
    target.pathname = SETUP_PATH;
    return NextResponse.redirect(target, 307);
  }
  const csp = contentSecurityPolicy({
    nonce: newNonce(),
    dev: process.env.NODE_ENV === "development",
    connect: [apiBase(process.env.NEXT_PUBLIC_API_URL), process.env.NEXT_PUBLIC_SUPABASE_URL],
  });
  const headers = new Headers(request.headers);
  headers.set("content-security-policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("content-security-policy", csp);
  return response;
}

export const config = {
  // Everything but the hashed build output under /_next/static/ (plain files that never render HTML). The matcher
  // sees the raw, still percent-encoded path, so nothing else is skipped: a CSP header on an image, the sitemap,
  // robots or the icon is harmless, while a skipped path like /_next/image/..%2fabout could render a page without it.
  matcher: ["/api/:path*", "/((?!_next/static/).*)"],
};
