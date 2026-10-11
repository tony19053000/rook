import type { Viewport } from "next";
import type { ReactNode } from "react";
import { SiteFrame } from "@/components/site/SiteFrame";
import { SITE_THEME_COLOR } from "@/components/site/tokens";

// The public site's pages (06 §1): header, main and footer around each page. The site is dark only.
export const viewport: Viewport = { themeColor: SITE_THEME_COLOR };

export default function SiteLayout({ children }: { children: ReactNode }) {
  return <SiteFrame>{children}</SiteFrame>;
}
