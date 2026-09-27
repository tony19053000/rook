import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";
import { siteUrl } from "@/lib/config";
import "./globals.css";

// Self-hosted by next/font at build time, so the CSP needs no third-party font origin (03 §8).
const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-plex-sans" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono" });
const newsreader = Newsreader({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-newsreader" });

// Every page renders per request so it can carry that request's CSP nonce (middleware.ts, 03 §8): a page
// prerendered at build time would have scripts without a nonce, and the browser would block them.
export const dynamic = "force-dynamic";

const DESCRIPTION =
  "Rook finds the smallest sequence of actions that breaks a business rule, proves it on the real app, and verifies the fix. Built on IBM Bob.";

export const metadata: Metadata = {
  metadataBase: siteUrl(process.env.NEXT_PUBLIC_SITE_URL, process.env.VERCEL_PROJECT_PRODUCTION_URL),
  title: "Rook · prove the bug, verify the fix",
  description: DESCRIPTION,
  applicationName: "Rook",
  openGraph: {
    type: "website",
    siteName: "Rook",
    title: "Rook · prove the bug, verify the fix",
    description: DESCRIPTION,
  },
  twitter: { card: "summary", title: "Rook · prove the bug, verify the fix", description: DESCRIPTION },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#262624" },
    { media: "(prefers-color-scheme: light)", color: "#faf9f5" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable} ${newsreader.variable}`}>
      <body>{children}</body>
    </html>
  );
}
