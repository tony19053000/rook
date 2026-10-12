import type { Metadata, Viewport } from "next";
import { ButtonLink } from "@/components/site/Button";
import { Container } from "@/components/site/Container";
import { SiteFrame } from "@/components/site/SiteFrame";
import { SITE_THEME_COLOR, type } from "@/components/site/tokens";
import { notFoundCopy } from "@/content/site";

export const metadata: Metadata = { title: notFoundCopy.title };
export const viewport: Viewport = { themeColor: SITE_THEME_COLOR };

// The branded 404 for any unknown path (06 §1), in the site frame.
export default function NotFound() {
  return (
    <SiteFrame>
      <div className="relative isolate">
        <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-96" />
        <div aria-hidden className="site-grid pointer-events-none absolute inset-0 -z-10" />
        <Container width="narrow" className="flex min-h-[calc(100vh-18rem)] flex-col items-center justify-center py-20 text-center sm:py-28">
          <p className="font-mono text-sm font-medium tracking-[0.3em] text-site-accent">404</p>
          <h1 className={`${type.h1} mt-6 text-site-ink`}>{notFoundCopy.heading}</h1>
          <p className={`${type.lead} mt-5`}>{notFoundCopy.body}</p>
          <div className="mt-10 flex flex-wrap justify-center gap-3">
            <ButtonLink href={notFoundCopy.home.href} size="lg">
              {notFoundCopy.home.label}
            </ButtonLink>
            <ButtonLink href={notFoundCopy.docs.href} variant="secondary" size="lg">
              {notFoundCopy.docs.label}
            </ButtonLink>
          </div>
        </Container>
      </div>
    </SiteFrame>
  );
}
