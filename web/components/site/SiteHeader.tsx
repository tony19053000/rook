import Link from "next/link";
import { HeaderAccountCtas, MobileAccountLink } from "./AccountHint";
import { Logo } from "./Logo";
import { NavLinkItem } from "./NavLinkItem";
import { gutter } from "./tokens";
import { headerCopy, headerNav } from "@/content/site";

const NAV_LINK = "rounded-md px-3 py-1.5 text-sm text-site-muted transition-colors hover:bg-white/[0.06] hover:text-site-ink";
const MENU_LINK = "block rounded-lg px-3 py-3 text-base text-site-ink transition-colors hover:bg-white/[0.06]";

// The sticky, translucent site header (06 §3), spanning the full viewport width. A server component: the mobile menu is a native <details>, so it
// opens and closes without JS. The account CTAs are the one client island (AccountHint.tsx).
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-site-line bg-site-bg/75 backdrop-blur-xl backdrop-saturate-150">
      <div className={`flex h-15 w-full items-center gap-2 ${gutter}`}>
        <Link href="/" aria-label={headerCopy.homeLabel} className="mr-4 rounded-md">
          <Logo />
        </Link>

        <nav aria-label={headerCopy.navLabel} className="hidden md:block">
          <ul className="flex items-center gap-0.5">
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
          <summary className="grid size-9 cursor-pointer place-items-center rounded-[0.625rem] border border-site-strong text-site-muted transition-colors hover:text-site-ink">
            <span className="sr-only">{headerCopy.menu}</span>
            <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <path className="group-open:hidden" d="M4 8h16M4 16h16" />
              <path className="hidden group-open:block" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </summary>
          <nav aria-label={headerCopy.mobileNavLabel} className="absolute inset-x-0 top-15 border-b border-site-line bg-site-bg shadow-[0_24px_48px_-12px_rgb(0_0_0/0.8)]">
            <ul className="flex w-full flex-col divide-y divide-site-line px-2 pt-1 pb-3 sm:px-5">
              {headerNav.map((link) => (
                <li key={link.href}>
                  <NavLinkItem link={link} className={MENU_LINK} />
                </li>
              ))}
              <li>
                <MobileAccountLink className={MENU_LINK} />
              </li>
            </ul>
          </nav>
        </details>
      </div>
    </header>
  );
}
