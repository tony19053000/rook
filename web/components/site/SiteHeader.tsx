import Link from "next/link";
import { HeaderAccountCtas, MobileAccountLink } from "./AccountHint";
import { Container } from "./Container";
import { Logo } from "./Logo";
import { NavLinkItem } from "./NavLinkItem";
import { headerCopy, headerNav } from "@/content/site";

const NAV_LINK = "rounded-md px-3 py-2 text-sm text-site-muted transition-colors hover:text-site-ink";

// The sticky, translucent site header (06 §3). A server component: the mobile menu is a native <details>, so it
// opens and closes without JS. The account CTAs are the one client island (AccountHint.tsx).
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-site-line bg-site-bg/80 backdrop-blur-md">
      <Container className="flex h-16 items-center gap-2">
        <Link href="/" aria-label={headerCopy.homeLabel} className="mr-2 rounded-md">
          <Logo />
        </Link>

        <nav aria-label={headerCopy.navLabel} className="hidden md:block">
          <ul className="flex items-center gap-1">
            {headerNav.map((link) => (
              <li key={link.href}>
                <NavLinkItem link={link} className={NAV_LINK} />
              </li>
            ))}
          </ul>
        </nav>

        <div className="ml-auto">
          <HeaderAccountCtas />
        </div>

        <details className="group md:hidden">
          <summary className="grid size-10 cursor-pointer place-items-center rounded-full text-site-muted hover:text-site-ink">
            <span className="sr-only">{headerCopy.menu}</span>
            <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path className="group-open:hidden" d="M4 7h16M4 12h16M4 17h16" />
              <path className="hidden group-open:block" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </summary>
          <nav aria-label={headerCopy.mobileNavLabel} className="absolute inset-x-0 top-16 border-b border-site-line bg-site-bg">
            <ul className="mx-auto flex max-w-6xl flex-col px-3 py-3">
              {headerNav.map((link) => (
                <li key={link.href}>
                  <NavLinkItem link={link} className="block rounded-md px-3 py-3 text-base text-site-ink hover:bg-site-raised" />
                </li>
              ))}
              <li>
                <MobileAccountLink className="block rounded-md px-3 py-3 text-base text-site-ink hover:bg-site-raised" />
              </li>
            </ul>
          </nav>
        </details>
      </Container>
    </header>
  );
}
