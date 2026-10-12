// What search engines get (06 §1, §8): the sitemap lists the public site pages only, and robots keeps crawlers out
// of the app and the API. Every URL derives from SITE_URL (content/site.ts).

import type { Metadata } from "next";
import { metadataCopy, site, SITE_URL } from "@/content/site";

/** The public site pages, as in app/(site)/ (/login is a utility page, not listed). */
export const SITEMAP_PATHS = [
  "/",
  "/docs",
  "/docs/getting-started",
  "/docs/install",
  "/docs/rules",
  "/docs/counterexamples",
  "/docs/github-action",
  "/docs/data",
  "/security",
  "/pricing",
  "/roadmap",
  "/about",
  "/contact",
  "/privacy",
  "/terms",
] as const;

/** The app routes, the dev story pages and the API: not for crawlers. */
export const ROBOTS_DISALLOW = ["/app", "/runs", "/rules", "/counterexamples", "/repositories", "/github", "/dev", "/api"] as const;

/** An absolute URL on the site. */
export function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}

/**
 * A site page's metadata (06 §8): its title (through the "%s · Roook" template), description, canonical URL, and the
 * same pair on the Open Graph and Twitter cards, with the card image from app/opengraph-image.tsx.
 */
export function pageMetadata(title: string, description: string, path: string): Metadata {
  const full = metadataCopy.titleTemplate.replace("%s", title);
  // A page's own openGraph/twitter objects replace the root's, file-based images included, so name them again.
  const image = { width: 1200, height: 630, alt: metadataCopy.ogAlt, type: "image/png" };
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", siteName: site.name, title: full, description, url: path, images: [{ url: "/opengraph-image", ...image }] },
    twitter: { card: "summary_large_image", title: full, description, images: [{ url: "/twitter-image", ...image }] },
  };
}
