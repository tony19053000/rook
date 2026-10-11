import type { Metadata, Viewport } from "next";
import { ButtonLink } from "@/components/site/Button";
import { Container } from "@/components/site/Container";
import { SiteFrame } from "@/components/site/SiteFrame";
import { SITE_THEME_COLOR, space, type } from "@/components/site/tokens";
import { notFoundCopy } from "@/content/site";

export const metadata: Metadata = { title: notFoundCopy.title };
export const viewport: Viewport = { themeColor: SITE_THEME_COLOR };

// The branded 404 for any unknown path (06 §1), in the site frame.
export default function NotFound() {
  return (
    <SiteFrame>
      <Container width="narrow" className={space.pageTop}>
        <p className={type.eyebrow}>404</p>
        <h1 className={`${type.h1} mt-4 text-site-ink`}>{notFoundCopy.heading}</h1>
        <p className={`${type.lead} mt-5`}>{notFoundCopy.body}</p>
        <div className="mt-10 flex flex-wrap gap-3">
          <ButtonLink href={notFoundCopy.home.href}>{notFoundCopy.home.label}</ButtonLink>
          <ButtonLink href={notFoundCopy.docs.href} variant="secondary">
            {notFoundCopy.docs.label}
          </ButtonLink>
        </div>
      </Container>
    </SiteFrame>
  );
}
