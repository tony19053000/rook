import { Container } from "./Container";
import { space, type } from "./tokens";
import type { LegalDoc } from "@/content/legal";

// A legal page in effect (06 §5.5): the title, its "Last updated" date, then the document.
export function LegalDocView({ doc }: { doc: LegalDoc }) {
  return (
    <Container width="narrow" className={space.pageTop}>
      <h1 className={`${type.h1} text-site-ink`}>{doc.heading}</h1>
      <p className="mt-3 text-sm text-site-faint">Last updated: {doc.lastUpdated}</p>
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
