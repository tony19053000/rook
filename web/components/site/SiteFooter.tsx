import Link from "next/link";
import { Container } from "./Container";
import { Logo } from "./Logo";
import { NavLinkItem } from "./NavLinkItem";
import { link as linkClass, type } from "./tokens";
import { CONTACT_EMAIL, footerColumns, footerCopy, headerCopy, mailtoHref, site } from "@/content/site";

// The full site footer (06 §3): the brand, then Product, Docs, Company and Legal, the operator with the contact
// address, and the licence line.
export function SiteFooter() {
  return (
    <footer className="border-t border-site-line bg-site-raised">
      <Container className="pt-16 pb-10 sm:pt-20">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,2fr)] lg:gap-16">
          <div className="max-w-sm">
            <Link href="/" aria-label={headerCopy.homeLabel} className="inline-block rounded-md">
              <Logo size={30} />
            </Link>
            <p className="mt-5 text-[0.9375rem] leading-relaxed text-site-muted">{site.oneLiner}</p>
          </div>
          <nav aria-label={footerCopy.navLabel} className="grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-4">
            {footerColumns.map((column) => (
              <div key={column.heading}>
                <h2 className={type.label}>{column.heading}</h2>
                <ul className="mt-5 flex flex-col gap-3">
                  {column.links.map((link) => (
                    <li key={link.href}>
                      <NavLinkItem link={link} className="text-sm text-site-muted transition-colors hover:text-site-ink" />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>
        <div className="mt-16 flex flex-col gap-2 border-t border-site-line pt-6 text-sm leading-relaxed text-site-faint">
          <p>
            {footerCopy.operatedBy} {footerCopy.contactLabel}{" "}
            <a href={mailtoHref(footerCopy.contactSubject)} className={linkClass} data-footer="email">
              {CONTACT_EMAIL}
            </a>
          </p>
          <p>
            {footerCopy.note} {footerCopy.openSource} <NavLinkItem link={footerCopy.licenceLink} className={linkClass} />.
          </p>
        </div>
      </Container>
    </footer>
  );
}
