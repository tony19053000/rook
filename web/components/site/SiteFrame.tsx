import type { ReactNode } from "react";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";
import { headerCopy } from "@/content/site";

// The site's page frame (06 §3): the `.site` scope for the dark tokens, the skip link (the first focusable
// element), the header, `main#main` and the footer. Used by app/(site)/layout.tsx and app/not-found.tsx.
export function SiteFrame({ children }: { children: ReactNode }) {
  return (
    <div className="site flex min-h-screen flex-col overflow-x-clip">
      <a
        href="#main"
        className="sr-only rounded-full bg-site-ink px-4 py-2 text-sm font-medium text-site-bg focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
      >
        {headerCopy.skipLink}
      </a>
      <SiteHeader />
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}
