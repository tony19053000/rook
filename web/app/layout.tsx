import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { metadataCopy, site, SITE_URL } from "@/content/site";
import { newsreader, plexMono, plexSans } from "./fonts";
import "./globals.css";

// Every page renders per request so it can carry that request's CSP nonce (middleware.ts, 03 §8): a page
// prerendered at build time would have scripts without a nonce, and the browser would block them.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  // Absolute OG/Twitter/canonical URLs (06 §4 "Site URL"): one constant, so a custom domain is one change.
  metadataBase: new URL(SITE_URL),
  title: { default: metadataCopy.defaultTitle, template: metadataCopy.titleTemplate },
  description: metadataCopy.description,
  applicationName: site.name,
  // The image comes from app/opengraph-image.tsx and app/twitter-image.tsx.
  openGraph: {
    type: "website",
    siteName: site.name,
    title: metadataCopy.defaultTitle,
    description: metadataCopy.description,
  },
  twitter: { card: "summary_large_image", title: metadataCopy.defaultTitle, description: metadataCopy.description },
};

// The app's warm theme colours; the site's pages override this with their dark colour (app/(site)/layout.tsx).
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
