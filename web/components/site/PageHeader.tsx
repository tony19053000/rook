import { Container } from "./Container";
import { type } from "./tokens";

/** The top of a long-form site page: eyebrow, the page's one h1 and the lead, in the narrow column. */
export function PageHeader({ eyebrow, heading, lead }: { eyebrow: string; heading: string; lead: string }) {
  return (
    <Container width="narrow" className="pt-14 sm:pt-20">
      <p className={type.eyebrow}>{eyebrow}</p>
      <h1 className={`${type.h1} mt-4 text-site-ink`}>{heading}</h1>
      <p className={`${type.lead} mt-5`}>{lead}</p>
    </Container>
  );
}
