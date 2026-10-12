import type { Metadata } from "next";
import { Container } from "@/components/site/Container";
import { NavLinkItem } from "@/components/site/NavLinkItem";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { type } from "@/components/site/tokens";
import { aboutCopy, aboutLinks, aboutSections } from "@/content/about";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(aboutCopy.title, aboutCopy.description, "/about");

const LIST = "flex list-disc flex-col gap-3 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint";

// /about (06 §5.7): who runs Rook, why it exists, the story and what it is not. A server component.
export default function AboutPage() {
  return (
    <>
      <PageHeader eyebrow={aboutCopy.eyebrow} heading={aboutCopy.heading} lead={aboutCopy.lead} />
      {aboutSections.map((section) => (
        <Section key={section.id} id={section.id} title={section.title} width="narrow">
          <div className="flex flex-col gap-4">
            {section.paragraphs.map((p) => (
              <p key={p} className={type.body}>
                {p}
              </p>
            ))}
            {section.items && (
              <ul className={LIST}>
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        </Section>
      ))}
      <Container width="narrow" className="py-16 sm:py-24">
        <ul className="flex flex-wrap gap-x-6 gap-y-3 text-sm">
          {aboutLinks.map((link) => (
            <li key={link.href}>
              <NavLinkItem link={link} className="text-site-link underline underline-offset-4" />
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
