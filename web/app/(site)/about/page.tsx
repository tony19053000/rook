import type { Metadata } from "next";
import { buttonClass } from "@/components/site/Button";
import { Container } from "@/components/site/Container";
import { NavLinkItem } from "@/components/site/NavLinkItem";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { type } from "@/components/site/tokens";
import { aboutCopy, aboutLinks, aboutSections } from "@/content/about";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(aboutCopy.title, aboutCopy.description, "/about");

const LIST = "site-list text-base leading-[1.7] text-site-muted";

// /about (06 §5.7): who runs Roook, why it exists, the story and what it is not. A server component.
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
      <Container width="narrow" className="pb-20 sm:pb-28">
        <ul className="flex flex-wrap gap-2.5 border-t border-site-line pt-10">
          {aboutLinks.map((link) => (
            <li key={link.href}>
              <NavLinkItem link={link} className={buttonClass("secondary", "md")} />
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
