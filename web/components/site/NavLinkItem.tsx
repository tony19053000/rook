import Link from "next/link";
import type { NavLink } from "@/content/site";

/** A site link: next/link inside the site, a plain <a> (no referrer) to another site. */
export function NavLinkItem({ link, className = "" }: { link: NavLink; className?: string }) {
  if (link.external) {
    return (
      <a href={link.href} className={className} rel="noopener noreferrer">
        {link.label}
      </a>
    );
  }
  return (
    <Link href={link.href} className={className}>
      {link.label}
    </Link>
  );
}
