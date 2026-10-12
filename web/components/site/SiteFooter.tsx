import Link from "next/link";
import { Container } from "./Container";
import { Logo } from "./Logo";
import { NavLinkItem } from "./NavLinkItem";
import { footerColumns, footerCopy, headerCopy, site } from "@/content/site";

// The full site footer (06 §3): the brand, then Product, Docs, Company and Legal.
export function SiteFooter() {
  return (
    <footer className="border-t border-site-line bg-site-raised">
      <Container className="grid gap-12 py-14 lg:grid-cols-[1.2fr_2fr]">
        <div className="max-w-sm">
          <Link href="/" aria-label={headerCopy.homeLabel} className="inline-block rounded-md">
            <Logo size={24} />
          </Link>
          <p className="mt-4 text-sm leading-relaxed text-site-muted">{site.oneLiner}</p>
          <p className="mt-4 text-sm leading-relaxed text-site-faint">
            {footerCopy.note} {footerCopy.openSource}{" "}
            <NavLinkItem link={footerCopy.licenceLink} className="text-site-muted underline underline-offset-4 hover:text-site-ink" />.
          </p>
        </div>
        <nav aria-label={footerCopy.navLabel} className="grid grid-cols-2 gap-8 sm:grid-cols-4">
          {footerColumns.map((column) => (
            <div key={column.heading}>
              <h2 className="text-sm font-semibold text-site-ink">{column.heading}</h2>
              <ul className="mt-4 flex flex-col gap-3">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <NavLinkItem link={link} className="text-sm text-site-muted transition-colors hover:text-site-ink" />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </Container>
    </footer>
  );
}
