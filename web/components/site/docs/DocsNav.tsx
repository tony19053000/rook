import Link from "next/link";
import { docsNav, guidesCopy } from "@/content/docsGuides";

// The docs sub-navigation (ROOK-055): a wrapping list above the guide on small screens, a sticky side column
// from lg. Plain links, so it works without JS; the current page is marked with aria-current.
export function DocsNav({ current }: { current: string }) {
  return (
    <nav aria-label={guidesCopy.navLabel} className="lg:sticky lg:top-24 lg:self-start">
      <p className="font-mono text-xs font-medium tracking-[0.14em] text-site-faint uppercase">{guidesCopy.navLabel}</p>
      <ul className="mt-3 flex flex-wrap gap-x-1 gap-y-1 lg:flex-col lg:gap-0.5">
        {docsNav.map((link) => {
          const active = link.href === current;
          return (
            <li key={link.href}>
              <Link
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-3 py-2 text-sm transition-colors ${
                  active ? "bg-site-card font-medium text-site-ink" : "text-site-muted hover:text-site-ink"
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
