import { Fragment, type ReactNode } from "react";
import { Container } from "./Container";
import { PageHeader } from "./PageHeader";
import { link, type } from "./tokens";
import type { LegalDoc } from "@/content/legal";
import { CONTACT_EMAIL, mailtoHref, site } from "@/content/site";

/** The text with each mention of the contact address as a mailto: link. */
function withEmailLinks(text: string, subject: string): ReactNode {
  const parts = text.split(CONTACT_EMAIL);
  return parts.map((part, i) => (
    // The parts of one sentence never reorder, so the index is a stable key.
    <Fragment key={i}>
      {i > 0 && (
        <a href={mailtoHref(subject)} className={`${link} break-words`}>
          {CONTACT_EMAIL}
        </a>
      )}
      {part}
    </Fragment>
  ));
}

// A legal page in effect (06 §5.5): the title, its "Last updated" date, then the document.
export function LegalDocView({ doc }: { doc: LegalDoc }) {
  const subject = `${site.name}: ${doc.title.toLowerCase()}`;
  return (
    <>
      <PageHeader heading={doc.heading}>
        <p className="mt-6 font-mono text-xs tracking-[0.04em] text-site-faint">Last updated: {doc.lastUpdated}</p>
      </PageHeader>
      <Container width="narrow" className="pt-10 pb-20 sm:pt-14 sm:pb-28">
        {doc.intro.map((p) => (
          <p key={p} className={`${type.body} mt-5 text-[1.0625rem] first:mt-0`}>
            {p}
          </p>
        ))}
        {doc.sections.map((section) => (
          <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="mt-10 scroll-mt-24 border-t border-site-line pt-10">
            <h2 id={`${section.id}-title`} className="font-serif text-2xl leading-snug font-medium tracking-[-0.012em] text-site-ink">
              {section.heading}
            </h2>
            {section.paragraphs?.map((p) => (
              <p key={p} className={`${type.body} mt-4`}>
                {withEmailLinks(p, subject)}
              </p>
            ))}
            {section.items && (
              <ul className="site-list mt-4 text-base leading-[1.7] text-site-muted">
                {section.items.map((item) => (
                  <li key={item}>{withEmailLinks(item, subject)}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </Container>
    </>
  );
}
