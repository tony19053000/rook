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
  width?: "wide" | "narrow";
  className?: string;
}

/** A page section: an h2 with an optional eyebrow and intro, labelling the region. */
export function Section({ id, title, eyebrow, intro, children, width = "wide", className = "" }: SectionProps) {
  const headingId = `${id}-title`;
  return (
    <section id={id} aria-labelledby={headingId} className={`scroll-mt-20 ${space.section} ${className}`}>
      <Container width={width}>
        <div className="max-w-2xl">
          {eyebrow && <p className={`${type.eyebrow} mb-3`}>{eyebrow}</p>}
          <h2 id={headingId} className={`${type.h2} text-site-ink`}>
            {title}
          </h2>
          {intro && <p className={`${type.body} mt-4`}>{intro}</p>}
        </div>
        {children && <div className="mt-10">{children}</div>}
      </Container>
    </section>
  );
}
