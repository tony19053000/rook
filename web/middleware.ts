import { NextResponse, type NextRequest } from "next/server";
import { apiBase } from "./lib/config";
import { contentSecurityPolicy, newNonce, proxyRequestHeaders } from "./lib/security";

// Per request (03 §8, 02 §13):
// - `/api/v1/*` goes on to the rewrite in next.config.ts (a proxy to the Rook server) with the shared
//   ROOK_PROXY_SECRET header, so the server can trust the client IP Vercel put in X-Forwarded-For.
// - Pages get a nonce-based Content-Security-Policy. Next.js reads the nonce from the request's CSP header and
//   puts it on its scripts, which is why the pages render per request (see app/layout.tsx).
export function middleware(request: NextRequest): NextResponse {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.next({ request: { headers: proxyRequestHeaders(request.headers, process.env.ROOK_PROXY_SECRET) } });
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
  // Everything but the static build output and the icon (files, not pages: they need no CSP).
  matcher: ["/api/:path*", "/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
