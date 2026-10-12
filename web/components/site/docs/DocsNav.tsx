import Link from "next/link";
import { type } from "../tokens";
import { docsNav, guidesCopy } from "@/content/docsGuides";

// The docs sub-navigation (ROOK-055): a wrapping list above the guide on small screens, a sticky side column
// from lg. Plain links, so it works without JS; the current page is marked with aria-current.
export function DocsNav({ current }: { current: string }) {
  return (
    <nav aria-label={guidesCopy.navLabel} className="lg:sticky lg:top-24 lg:self-start">
      <p className={type.label}>{guidesCopy.navLabel}</p>
      <ul className="mt-4 flex flex-wrap gap-1.5 lg:flex-col lg:gap-0.5 lg:border-l lg:border-site-line">
        {docsNav.map((link) => {
          const active = link.href === current;
          return (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-full border px-3.5 py-1.5 text-sm transition-colors lg:-ml-px lg:rounded-none lg:border-0 lg:border-l lg:py-1.5 lg:pl-4 ${
                  active
                    ? "border-site-control bg-white/[0.06] font-medium text-site-ink lg:border-site-accent lg:bg-transparent"
                    : "border-site-strong text-site-muted hover:text-site-ink lg:border-transparent lg:hover:border-site-control"
                }`}
              >
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
