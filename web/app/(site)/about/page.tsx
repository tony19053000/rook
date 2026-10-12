import type { Metadata } from "next";
import { buttonClass } from "@/components/site/Button";
import { Card } from "@/components/site/Card";
import { Container } from "@/components/site/Container";
import { NavLinkItem } from "@/components/site/NavLinkItem";
import { PageHeader } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { link, type } from "@/components/site/tokens";
import { aboutCapabilities, aboutCopy, aboutLinks, aboutSections, founderCopy, type AboutSection } from "@/content/about";
import { mailtoHref } from "@/content/site";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(aboutCopy.title, aboutCopy.description, "/about");

const LIST = "site-list text-base leading-[1.7] text-site-muted";
const LINK = `${link} break-words`;

function SectionBody({ section }: { section: AboutSection }) {
  return (
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
  );
}

/** The founder: the name and title, a short introduction, and how to reach them. */
function FounderCard() {
  const initials = founderCopy.name
    .split(" ")
    .map((part) => part[0])
    .join("");
  return (
    <Card className="flex flex-col gap-5 sm:flex-row sm:gap-6" as="article">
      <span
        aria-hidden
        className="flex size-14 shrink-0 items-center justify-center rounded-full border border-site-strong bg-white/[0.04] font-serif text-lg text-site-ink"
      >
        {initials}
      </span>
      <div className="min-w-0">
        <h3 className={`${type.h3} text-site-ink`}>{founderCopy.line}</h3>
        <div className="mt-3 flex flex-col gap-3">
          {founderCopy.paragraphs.map((p) => (
            <p key={p} className={type.body}>
              {p}
            </p>
          ))}
        </div>
        <dl className="mt-5 grid gap-x-6 gap-y-2 border-t border-site-line pt-5 text-[0.9375rem] sm:grid-cols-[auto_1fr]">
          <dt className={type.label}>{founderCopy.emailLabel}</dt>
          <dd>
            <a href={mailtoHref(founderCopy.emailSubject)} className={LINK} data-founder="email">
              {founderCopy.email}
            </a>
          </dd>
          <dt className={type.label}>{founderCopy.websiteLabel}</dt>
          <dd>
            <a href={founderCopy.website} className={LINK} data-founder="website">
              {founderCopy.website}
            </a>
          </dd>
        </dl>
      </div>
    </Card>
  );
}

// /about (06 §5.7): what Roook does, its founder, why it exists, the story and where it stands. A server component.
export default function AboutPage() {
  return (
    <>
      <PageHeader eyebrow={aboutCopy.eyebrow} heading={aboutCopy.heading} lead={aboutCopy.lead} />
      <Section id={aboutCapabilities.id} title={aboutCapabilities.title} width="narrow">
        <SectionBody section={aboutCapabilities} />
      </Section>
      <Section id={founderCopy.id} title={founderCopy.title} width="narrow">
        <FounderCard />
      </Section>
      {aboutSections.map((section) => (
        <Section key={section.id} id={section.id} title={section.title} width="narrow">
          <SectionBody section={section} />
        </Section>
      ))}
      <Container width="narrow" className="pb-20 sm:pb-28">
        <ul className="flex flex-wrap gap-2.5 border-t border-site-line pt-10">
          {aboutLinks.map((item) => (
            <li key={item.href}>
              <NavLinkItem link={item} className={buttonClass("secondary", "md")} />
            </li>
          ))}
        </ul>
      </Container>
    </>
  );
}
