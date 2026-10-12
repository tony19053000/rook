import type { Metadata } from "next";
import Link from "next/link";
import { Card } from "@/components/site/Card";
import { InlineCode } from "@/components/site/InlineCode";
import { PageHeader, PageToc } from "@/components/site/PageHeader";
import { Section } from "@/components/site/Section";
import { type } from "@/components/site/tokens";
import { cliReference, docsCopy, guidesIndex, howItWorks } from "@/content/docs";
import { guides } from "@/content/docsGuides";
import { flowSteps } from "@/content/flow";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(docsCopy.title, docsCopy.description, "/docs");

const SECTIONS = [howItWorks, guidesIndex, cliReference];

// The docs overview (06 §1, ROOK-055): the six steps from content/flow.ts, the index of the guides and the CLI's
// commands. A server component. Each guide's card carries the last segment of its path as its id, so the anchors
// /docs#getting-started and /docs#github-action from before the guides existed still land on the right card.
export default function DocsPage() {
  return (
    <>
      <PageHeader eyebrow={docsCopy.eyebrow} heading={docsCopy.heading} lead={docsCopy.lead} width="wide">
        <PageToc label={docsCopy.tocLabel} items={SECTIONS} />
      </PageHeader>

      <Section id={howItWorks.id} title={howItWorks.title} intro={howItWorks.intro}>
        <ol className="grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-2 xl:grid-cols-3">
          {flowSteps.map((step, i) => (
            <Card as="li" key={step.id} className="flex flex-col sm:p-7">
              <p className={type.label}>
                {docsCopy.stepLabel} {i + 1}
              </p>
              <h3 className="mt-3 text-xl leading-snug font-semibold tracking-[-0.015em] text-site-ink">{step.title}</h3>
              <p className={`${type.small} mt-2`}>{step.summary}</p>
              <ul className="site-list mt-5 border-t border-site-line pt-5 text-sm leading-relaxed text-site-muted">
                {step.details.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </Card>
          ))}
        </ol>
      </Section>

      <Section id={guidesIndex.id} title={guidesIndex.title} intro={guidesIndex.intro} className="border-t border-site-line">
        <ul data-guides className="grid grid-cols-1 gap-4 sm:gap-5 md:grid-cols-2 xl:grid-cols-3">
          {guides.map((guide) => (
            <li
              key={guide.path}
              id={guide.path.split("/").pop()}
              className="site-panel group relative flex scroll-mt-24 flex-col rounded-2xl p-6 transition-colors hover:border-site-strong sm:p-7"
            >
              <h3 className="text-xl leading-snug font-semibold tracking-[-0.015em] text-site-ink">{guide.navLabel}</h3>
              <p className={`${type.small} mt-2 flex-1`}>{guide.summary}</p>
              <p className="mt-6 text-sm font-medium">
                {/* The link's hit area is the whole card. */}
                <Link href={guide.path} className="inline-flex items-center gap-1.5 text-site-ink after:absolute after:inset-0 after:rounded-2xl">
                  {docsCopy.guideLink}
                  <span className="sr-only">: {guide.navLabel}</span>
                  <svg aria-hidden width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-site-muted transition-transform group-hover:translate-x-0.5">
                    <path d="M2.5 7h9M8 3.5 11.5 7 8 10.5" />
                  </svg>
                </Link>
              </p>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={cliReference.id} title={cliReference.title} intro={cliReference.intro} layout="aside" className="border-t border-site-line">
        <dl className="site-panel flex flex-col divide-y divide-site-line rounded-2xl">
          {cliReference.items.map((c) => (
            <div key={c.usage} className="flex flex-col gap-1.5 px-5 py-4 sm:px-6">
              <dt className="font-mono text-[0.8125rem] break-words text-site-ink">
                <span aria-hidden className="mr-2.5 select-none text-site-accent">
                  $
                </span>
                {c.usage}
              </dt>
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
