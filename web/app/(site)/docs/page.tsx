import type { Metadata } from "next";
import { Card } from "@/components/site/Card";
import { CodeBlock } from "@/components/site/CodeBlock";
import { Container } from "@/components/site/Container";
import { Section } from "@/components/site/Section";
import { measure, type } from "@/components/site/tokens";
import { docsCopy, githubAction, gettingStarted, howItWorks } from "@/content/docs";
import { flowSteps } from "@/content/flow";
import { REPO_URL } from "@/content/site";
import { pageMetadata } from "@/lib/seo";

export const metadata: Metadata = pageMetadata(docsCopy.title, docsCopy.description, "/docs");

const SECTIONS = [howItWorks, gettingStarted, githubAction];
const LINK = "text-site-link underline underline-offset-4";

function SubHeading({ children }: { children: string }) {
  return <h3 className={`${type.h3} text-site-ink`}>{children}</h3>;
}

// /docs (06 §5.2): the six steps from content/flow.ts, then getting started and the GitHub Action. A server
// component; the anchors are the ones the footer links to.
export default function DocsPage() {
  const { requirements, install, firstRun, commands, files } = gettingStarted;
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

      <Section id={gettingStarted.id} title={gettingStarted.title} intro={gettingStarted.intro}>
        {/* One column of readable width; from xl, setup on the left and the reference on the right. */}
        <div className="grid grid-cols-1 gap-12 xl:grid-cols-2 xl:gap-16">
          <div className={`flex min-w-0 flex-col gap-12 ${measure}`}>
            <div>
              <SubHeading>{requirements.heading}</SubHeading>
              <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-base leading-relaxed text-site-muted marker:text-site-faint">
                {requirements.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            <div>
              <SubHeading>{install.heading}</SubHeading>
              <div className="mt-3">
                <CodeBlock code={install.command} prompt />
              </div>
              <p className={`${type.small} mt-3`}>{install.note}</p>
            </div>

            <div>
              <SubHeading>{firstRun.heading}</SubHeading>
              {firstRun.paragraphs.map((p) => (
                <p key={p} className={`${type.body} mt-3`}>
                  {p}
                </p>
              ))}
              <div className="mt-4">
                <CodeBlock code={firstRun.examples.join("\n")} />
              </div>
            </div>
          </div>

          <div className={`flex min-w-0 flex-col gap-12 ${measure}`}>
            <div>
              <SubHeading>{commands.heading}</SubHeading>
              <dl className="mt-4 flex flex-col divide-y divide-site-line rounded-2xl border border-site-line bg-site-card">
                {commands.items.map((c) => (
                  <div key={c.usage} className="flex flex-col gap-1 px-5 py-4">
                    <dt className="font-mono text-sm break-words text-site-ink">{c.usage}</dt>
                    <dd className={type.small}>{c.purpose}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <div>
              <SubHeading>{files.heading}</SubHeading>
              <div className="mt-3">
                <CodeBlock code={files.code} />
              </div>
              <p className={`${type.small} mt-3`}>{files.note}</p>
            </div>
          </div>
        </div>
      </Section>

      <Section id={githubAction.id} title={githubAction.title} intro={githubAction.intro}>
        {/* From xl, the workflow on the left and its notes beside it. */}
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] xl:items-start xl:gap-10">
          <div className="min-w-0">
            <CodeBlock code={githubAction.workflow} label={githubAction.workflowLabel} />
          </div>
          <div className={`flex min-w-0 flex-col gap-5 ${measure}`}>
            <p className={type.small}>{githubAction.pinNote}</p>
            <div role="note" className="rounded-xl border border-site-warn/40 bg-site-warn-soft px-4 py-3">
              <p className="text-sm font-semibold text-site-warn">{githubAction.warningTitle}</p>
              <p className="mt-1 text-sm leading-relaxed text-site-warn">{githubAction.warning}</p>
            </div>
            <p className={type.small}>
              <a href={`${REPO_URL}/blob/main/${githubAction.more.path}`} className={LINK} rel="noopener noreferrer">
                {githubAction.more.label}
              </a>
            </p>
          </div>
        </div>
      </Section>
    </>
  );
}
