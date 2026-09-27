import type { NextConfig } from "next";
import { apiRewrites, proxyTarget } from "./lib/config";
import { SECURITY_HEADERS } from "./lib/security";

// Same-origin API (02 §11, §13; 03 §5): `/api/v1/*` is proxied to the Rook server (EC2 + Caddy), so the browser
// only talks to the web origin and the `rook_guest` cookie stays first-party. ROOK_API_PROXY_TARGET is the
// server origin (e.g. https://203-0-113-7.sslip.io), read at build time; it is a public URL, not a secret.
const target = proxyTarget(process.env.ROOK_API_PROXY_TARGET);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The SSE stream must not be gzipped (buffering would hold events back).
  compress: false,
  // Static security headers on every response; the per-request CSP is set in middleware.ts (03 §8).
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return apiRewrites(target);
  },
};

export default nextConfig;
