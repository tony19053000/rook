import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader, PageToc } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { link } from "@/components/site/tokens";
import { notYetTrue, securityCopy, securitySections } from "@/content/security";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(securityCopy.title, securityCopy.description, "/security");

const LIST = "site-list text-base leading-[1.7] text-site-muted";

// /security (06 §5.3): how data and code are handled, then "What is not yet true". A server component.
export default function SecurityPage() {
  return (
    <>
      <PageHeader eyebrow={securityCopy.eyebrow} heading={securityCopy.heading} lead={securityCopy.lead}>
        <PageToc label={securityCopy.tocLabel} items={[...securitySections, notYetTrue]} />
      </PageHeader>

      {securitySections.map((section) => (
        <Section key={section.id} id={section.id} title={section.title} intro={section.intro} width="narrow">
          <ul className={LIST}>
            {section.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          {section.link && (
            <p className="mt-6 text-[0.9375rem]">
              <Link href={section.link.href} className={link}>
                {section.link.label}
              </Link>
            </p>
          )}
        </Section>
      ))}

      <Section id={notYetTrue.id} title={notYetTrue.title} intro={notYetTrue.intro} width="narrow" className="pb-10 sm:pb-16">
        <ul
          className="flex flex-col divide-y divide-site-warn/20 rounded-2xl border border-site-warn/35 bg-site-warn-soft text-base leading-[1.7] text-site-ink"
          data-not-yet-true
        >
          {notYetTrue.items.map((item) => (
            <li key={item} className="flex gap-4 px-5 py-4 sm:px-6">
              <span aria-hidden className="mt-[0.72em] size-1.5 flex-none rounded-[1px] bg-site-warn" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </Section>
    </>
  );
}
