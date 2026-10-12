import type { MetadataRoute } from "next";
import { absoluteUrl, SITEMAP_PATHS } from "@/lib/seo";

// /sitemap.xml (06 §1): the site pages only. No lastModified: the pages carry no real edit date.
export default function sitemap(): MetadataRoute.Sitemap {
  return SITEMAP_PATHS.map((path) => ({ url: absoluteUrl(path) }));
}
