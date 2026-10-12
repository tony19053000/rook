import type { Metadata } from "next";
import Link from "next/link";
import { Card } from "@/components/site/Card";
import { Container } from "@/components/site/Container";
import { InlineCode } from "@/components/site/InlineCode";
import { Section } from "@/components/site/Section";
import { measure, type } from "@/components/site/tokens";
import { cliReference, docsCopy, guidesIndex, howItWorks } from "@/content/docs";
import { guides } from "@/content/docsGuides";
import { flowSteps } from "@/content/flow";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(docsCopy.title, docsCopy.description, "/docs");

const SECTIONS = [howItWorks, guidesIndex, cliReference];
const LINK = "text-site-link underline underline-offset-4";

// The docs overview (06 §1, ROOK-055): the six steps from content/flow.ts, the index of the guides and the CLI's
// commands. A server component. Each guide's card carries the last segment of its path as its id, so the anchors
// /docs#getting-started and /docs#github-action from before the guides existed still land on the right card.
export default function DocsPage() {
  return (
    <>
      <Container className="pt-14 sm:pt-20">
        <p className={type.eyebrow}>{docsCopy.eyebrow}</p>
        <h1 className={`${type.h1} mt-4 max-w-3xl text-site-ink`}>{docsCopy.heading}</h1>
        <p className={`${type.lead} mt-5 max-w-2xl`}>{docsCopy.lead}</p>
        <nav aria-label={docsCopy.tocLabel} className="mt-8">
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className={LINK}>
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </Container>

      <Section id={howItWorks.id} title={howItWorks.title} intro={howItWorks.intro}>
        <ol className="grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-2 xl:grid-cols-3">
          {flowSteps.map((step, i) => (
            <Card as="li" key={step.id}>
              <p className={type.eyebrow}>
                {docsCopy.stepLabel} {i + 1}
              </p>
              <h3 className={`${type.h3} mt-2 text-site-ink`}>{step.title}</h3>
              <p className={`${type.body} mt-2`}>{step.summary}</p>
              <ul className="mt-4 flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed text-site-muted marker:text-site-faint">
                {step.details.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </Card>
          ))}
        </ol>
      </Section>

      <Section id={guidesIndex.id} title={guidesIndex.title} intro={guidesIndex.intro}>
        <ul data-guides className="grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-2 xl:grid-cols-3">
          {guides.map((guide) => (
            <li key={guide.path} id={guide.path.split("/").pop()} className="flex scroll-mt-24 flex-col rounded-2xl border border-site-line bg-site-card p-6">
              <h3 className={`${type.h3} text-site-ink`}>{guide.navLabel}</h3>
              <p className={`${type.body} mt-2 flex-1`}>{guide.summary}</p>
              <p className="mt-4 text-sm">
                <Link href={guide.path} className={LINK}>
                  {docsCopy.guideLink}
                  <span className="sr-only">: {guide.navLabel}</span>
                </Link>
              </p>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={cliReference.id} title={cliReference.title} intro={cliReference.intro}>
        <dl className={`flex flex-col divide-y divide-site-line rounded-2xl border border-site-line bg-site-card ${measure}`}>
          {cliReference.items.map((c) => (
            <div key={c.usage} className="flex flex-col gap-1 px-5 py-4">
              <dt className="font-mono text-sm break-words text-site-ink">{c.usage}</dt>
              <dd className={type.small}>
                <InlineCode text={c.purpose} />
              </dd>
            </div>
          ))}
        </dl>
      </Section>
    </>
  );
}
