import type { ReactNode } from "react";
import { Container } from "./Container";
import { space, type } from "./tokens";

interface SectionProps {
  /** Used for the anchor and the heading id. */
  id: string;
  title: string;
  eyebrow?: string;
  intro?: string;
  children?: ReactNode;
  /** `narrow` is a section of long-form text: the readable column, a smaller heading and a tighter rhythm. */
  width?: "wide" | "narrow";
  /** Wide sections only. `aside` puts the heading in a left column (sticky on wide screens) beside the content. */
  layout?: "stack" | "aside";
  className?: string;
}

/** A page section: an h2 with an optional eyebrow and intro, labelling the region. */
export function Section({ id, title, eyebrow, intro, children, width = "wide", layout = "stack", className = "" }: SectionProps) {
  const headingId = `${id}-title`;
  const doc = width === "narrow";
  const aside = !doc && layout === "aside";
  const heading = (
    <div className={aside ? "max-w-xl lg:sticky lg:top-28 lg:self-start" : "max-w-3xl"}>
      {eyebrow && <p className={`${type.eyebrow} mb-5`}>{eyebrow}</p>}
      <h2 id={headingId} className={`${doc ? type.h2Doc : type.h2} text-site-ink`}>
        {title}
      </h2>
      {intro && <p className={doc ? `${type.body} mt-3` : `${type.lead} mt-5 max-w-2xl`}>{intro}</p>}
    </div>
  );
  if (doc) {
    // Long-form: `site-doc` marks the section, so the column of one that follows another gets a hairline.
    return (
      <section id={id} aria-labelledby={headingId} className={`site-doc scroll-mt-20 ${className}`}>
        <Container width="narrow">
          <div className={`${space.sectionDoc} [.site-doc+.site-doc_&]:border-t [.site-doc+.site-doc_&]:border-site-line`}>
            {heading}
            {children && <div className="mt-6">{children}</div>}
          </div>
        </Container>
      </section>
    );
  }
  return (
    <section id={id} aria-labelledby={headingId} className={`scroll-mt-20 ${space.section} ${className}`}>
      <Container>
        {aside ? (
          <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
            {heading}
            <div className="min-w-0">{children}</div>
          </div>
        ) : (
          <>
            {heading}
            {children && <div className="mt-12 sm:mt-14">{children}</div>}
          </>
        )}
      </Container>
    </section>
  );
}
