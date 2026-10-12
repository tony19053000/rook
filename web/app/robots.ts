import type { MetadataRoute } from "next";
import { absoluteUrl, ROBOTS_DISALLOW } from "@/lib/seo";

// /robots.txt (06 §1): the site is open to crawlers; the app, /dev/* and the API are not.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: [...ROBOTS_DISALLOW] },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
