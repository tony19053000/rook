import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/site/Container";
import { Section } from "@/components/site/Section";
import { type } from "@/components/site/tokens";
import { notYetTrue, securityCopy, securitySections } from "@/content/security";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(securityCopy.title, securityCopy.description, "/security");

const LIST = "flex list-disc flex-col gap-3 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint";
const LINK = "text-site-link underline underline-offset-4";

// /security (06 §5.3): how data and code are handled, then "What is not yet true". A server component.
export default function SecurityPage() {
  return (
    <>
      <Container width="narrow" className="pt-14 sm:pt-20">
        <p className={type.eyebrow}>{securityCopy.eyebrow}</p>
        <h1 className={`${type.h1} mt-4 text-site-ink`}>{securityCopy.heading}</h1>
        <p className={`${type.lead} mt-5`}>{securityCopy.lead}</p>
        <nav aria-label={securityCopy.tocLabel} className="mt-8">
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {[...securitySections, notYetTrue].map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className={LINK}>
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </Container>

      {securitySections.map((section) => (
        <Section key={section.id} id={section.id} title={section.title} intro={section.intro} width="narrow">
          <ul className={LIST}>
            {section.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {section.link && (
            <p className="mt-5 text-sm">
              <Link href={section.link.href} className={LINK}>
                {section.link.label}
              </Link>
            </p>
          )}
        </Section>
      ))}

      <Section id={notYetTrue.id} title={notYetTrue.title} intro={notYetTrue.intro} width="narrow">
        <ul className="flex list-disc flex-col gap-3 rounded-2xl border border-site-warn/40 bg-site-warn-soft py-5 pr-5 pl-10 text-base leading-relaxed text-site-ink marker:text-site-warn" data-not-yet-true>
          {notYetTrue.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>
    </>
  );
}
