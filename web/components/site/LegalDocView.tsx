import { Container } from "./Container";
import { space, type } from "./tokens";
import { LEGAL_DRAFT_BANNER, type LegalDoc } from "@/content/legal";

// A legal draft page (06 §5.5): the draft banner first, then the document.
export function LegalDocView({ doc }: { doc: LegalDoc }) {
  return (
    <Container width="narrow" className={space.pageTop}>
      <p role="note" data-legal-banner className="rounded-xl border border-site-warn/40 bg-site-warn-soft px-4 py-3 text-sm font-medium text-site-warn">
        {LEGAL_DRAFT_BANNER}
      </p>
      <h1 className={`${type.h1} mt-10 text-site-ink`}>{doc.heading}</h1>
      {doc.intro.map((p) => (
        <p key={p} className={`${type.body} mt-5`}>
          {p}
        </p>
      ))}
      {doc.sections.map((section) => (
        <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`} className="mt-12 scroll-mt-20">
          <h2 id={`${section.id}-title`} className={`${type.h3} text-site-ink`}>
            {section.heading}
          </h2>
          {section.paragraphs?.map((p) => (
            <p key={p} className={`${type.body} mt-3`}>
              {p}
            </p>
          ))}
          {section.items && (
            <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint">
              {section.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </Container>
  );
}
