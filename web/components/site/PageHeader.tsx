import type { ReactNode } from "react";
import { Container } from "./Container";
import { type } from "./tokens";

interface PageHeaderProps {
  eyebrow?: string;
  heading: string;
  lead?: string;
  width?: "wide" | "narrow";
  /** Extra content under the lead (a page's table of contents, a date). */
  children?: ReactNode;
}

/** The top of a site page: eyebrow, the page's one h1 and the lead, over a faint light from the top edge. */
export function PageHeader({ eyebrow, heading, lead, width = "narrow", children }: PageHeaderProps) {
  return (
    <div className="relative isolate border-b border-site-line">
      <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-72" />
      <Container width={width} className="pt-16 pb-12 sm:pt-24 sm:pb-16">
        {eyebrow && <p className={type.eyebrow}>{eyebrow}</p>}
        <h1 className={`${type.h1} ${eyebrow ? "mt-6" : ""} max-w-4xl text-site-ink`}>{heading}</h1>
        {lead && <p className={`${type.lead} mt-6 max-w-2xl`}>{lead}</p>}
        {children}
      </Container>
    </div>
  );
}

/** A page's table of contents under its header: anchor links as quiet chips. */
export function PageToc({ label, items }: { label: string; items: readonly { id: string; title: string }[] }) {
  return (
    <nav aria-label={label} className="mt-9">
      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              className="inline-flex h-8 items-center rounded-full border border-site-strong bg-white/[0.03] px-3.5 text-sm text-site-muted transition-colors hover:border-site-control hover:text-site-ink"
            >
              {item.title}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
