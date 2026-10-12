import type { Metadata } from "next";
import Link from "next/link";
import { ButtonLink } from "@/components/site/Button";
import { CodeBlock } from "@/components/site/CodeBlock";
import { Container } from "@/components/site/Container";
import { Section } from "@/components/site/Section";
import { JsonLd } from "@/components/site/JsonLd";
import { FeatureIcon } from "@/components/site/home/FeatureIcon";
import { FlowDiagram } from "@/components/site/home/FlowDiagram";
import { HeroParallax } from "@/components/site/home/HeroParallax";
import { RefundStory } from "@/components/site/home/RefundStory";
import { RunScreenshot } from "@/components/site/home/RunScreenshot";
import { Walkthrough } from "@/components/site/home/Walkthrough";
import { link, type } from "@/components/site/tokens";
import {
  closingCta,
  faqSection,
  features,
  flowDiagram,
  featuresSection,
  homeFaq,
  homeHero,
  refusals,
  refusalsSection,
  scope,
  scopeSection,
} from "@/content/home";
import { plans, pricingStatus } from "@/content/pricing";
import { cta } from "@/content/site";
import { storyCopy } from "@/content/story";
import { walkthroughCopy } from "@/content/walkthrough";
import { siteStructuredData } from "@/lib/structuredData";

// The title, description and cards are the site defaults (app/layout.tsx).
export const metadata: Metadata = { alternates: { canonical: "/" } };

const HERO_TITLE_ID = "hero-title";
/** A hairline between the home page's sections. */
const RULED = "border-t border-site-line";

// The marketing home (06 §5.1, ROOK-054): the problem-first hero with a real product screenshot, the refund
// bug end to end, the 6-step diagram, the walkthrough, then benefits, guarantees, scope, FAQ and the closing CTA.
// A server component: only the hero's parallax and the walkthrough are client islands (the only places
// `motion` and timers are used). Everything is in the server render.
export default function HomePage() {
  const faq = homeFaq(pricingStatus(plans));
  const closingTitleId = `${closingCta.id}-title`;
  return (
    <>
      <JsonLd data={siteStructuredData()} />
      <HeroParallax
        labelledBy={HERO_TITLE_ID}
        text={
          <>
            <p className="inline-flex items-center gap-2.5 rounded-full border border-site-strong bg-white/[0.03] py-1.5 pr-4 pl-3.5 font-mono text-xs font-medium tracking-[0.14em] text-site-muted uppercase">
              <span aria-hidden className="size-1.5 rounded-full bg-site-accent" />
              {homeHero.eyebrow}
            </p>
            <h1 id={HERO_TITLE_ID} className={`${type.display} mt-8 text-site-ink`}>
              {homeHero.heading}
            </h1>
            <p className={`${type.lead} mt-7 max-w-2xl`}>{homeHero.lead}</p>
            <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
              <ButtonLink href={cta.demo.href} size="lg">
                {cta.demo.label}
              </ButtonLink>
              <ButtonLink href={cta.docs.href} variant="secondary" size="lg">
                {cta.docs.label}
              </ButtonLink>
              <ButtonLink href={homeHero.github.href} variant="ghost" size="lg" external>
                {homeHero.github.label}
                <span aria-hidden>↗</span>
              </ButtonLink>
            </div>
          </>
        }
        figure={<RunScreenshot />}
      />

      <Section id={storyCopy.id} eyebrow={storyCopy.eyebrow} title={storyCopy.title} intro={storyCopy.intro} className={RULED}>
        <RefundStory />
      </Section>

      <Section id={flowDiagram.id} eyebrow={flowDiagram.eyebrow} title={flowDiagram.title} intro={flowDiagram.intro} className={RULED}>
        <FlowDiagram />
      </Section>

      <Section id={walkthroughCopy.id} eyebrow={walkthroughCopy.eyebrow} title={walkthroughCopy.title} intro={walkthroughCopy.intro} className={RULED}>
        <Walkthrough />
      </Section>

      <Section id={featuresSection.id} eyebrow={featuresSection.eyebrow} title={featuresSection.title} intro={featuresSection.intro} className={RULED}>
        {/* One ruled sheet: the 1 px gaps of the grid show the line colour behind the cells. */}
        <div className="grid gap-px overflow-hidden rounded-2xl border border-site-line bg-site-line sm:grid-cols-2 lg:grid-cols-4">
          {features.map((item, i) => (
            <article key={item.title} className="flex gap-4 bg-site-card p-5 transition-colors hover:bg-site-elev sm:flex-col sm:gap-6 sm:p-7">
              <span className="grid size-9 flex-none place-items-center rounded-[0.625rem] border border-site-strong bg-white/[0.03] text-site-ink">
                <FeatureIcon index={i} />
              </span>
              <div className="min-w-0">
                <h3 className={`${type.h3} text-site-ink`}>{item.title}</h3>
                <p className={`${type.small} mt-2`}>{item.body}</p>
              </div>
            </article>
          ))}
        </div>
      </Section>

      <Section
        id={refusalsSection.id}
        eyebrow={refusalsSection.eyebrow}
        title={refusalsSection.title}
        intro={refusalsSection.intro}
        layout="aside"
        className={RULED}
      >
        <ul className="flex flex-col divide-y divide-site-line border-y border-site-line">
          {refusals.map((item) => (
            <li key={item.title} className="flex gap-5 py-6">
              <span aria-hidden className="mt-0.5 grid size-6 flex-none place-items-center rounded-md border border-site-accent/35 bg-site-accent/10 text-site-accent">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" />
                </svg>
              </span>
              <div className="min-w-0">
                <h3 className={`${type.h3} text-site-ink`}>{item.title}</h3>
                <p className={`${type.small} mt-1.5`}>{item.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={scopeSection.id} eyebrow={scopeSection.eyebrow} title={scopeSection.title} intro={scopeSection.intro} layout="aside" className={RULED}>
        <ul className="site-panel flex flex-col divide-y divide-site-line rounded-2xl">
          {scope.map((line) => (
            <li key={line} className={`${type.body} flex gap-4 px-5 py-4 sm:px-6 sm:py-5`}>
              <span aria-hidden className="mt-[0.7em] size-1.5 flex-none rounded-[1px] bg-site-control" />
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={faqSection.id} eyebrow={faqSection.eyebrow} title={faqSection.title} layout="aside" className={RULED}>
        <div className="flex flex-col divide-y divide-site-line border-y border-site-line">
          {faq.map((item) => (
            <details key={item.question} className="group">
              <summary className="flex cursor-pointer items-center justify-between gap-6 rounded-md py-5 text-[1.0625rem] font-medium text-site-ink transition-colors hover:text-white">
                {item.question}
                <span aria-hidden className="grid size-7 flex-none place-items-center rounded-full border border-site-strong text-site-muted transition-transform duration-200 group-open:rotate-45">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M5 1v8M1 5h8" />
                  </svg>
                </span>
              </summary>
              <p className={`${type.body} max-w-2xl pr-10 pb-6`}>{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      <section id={closingCta.id} aria-labelledby={closingTitleId} className="scroll-mt-20 pb-16 sm:pb-28">
        <Container>
          <div className="relative isolate overflow-hidden rounded-3xl border border-site-line bg-site-card px-5 py-14 text-center shadow-[inset_0_1px_0_rgb(255_255_255/0.04)] sm:px-12 sm:py-20">
            <div aria-hidden className="site-top-light pointer-events-none absolute inset-x-0 top-0 -z-10 h-80" />
            <div aria-hidden className="site-beam pointer-events-none absolute inset-x-[18%] top-0" />
            <h2 id={closingTitleId} className={`${type.h2} text-site-ink`}>
              {closingCta.title}
            </h2>
            <p className={`${type.lead} mx-auto mt-5 max-w-xl`}>{closingCta.body}</p>
            <div className="mt-9 flex flex-wrap justify-center gap-3">
              <ButtonLink href={cta.demo.href} size="lg">
                {cta.demo.label}
              </ButtonLink>
              <ButtonLink href={closingCta.docsLink.href} variant="secondary" size="lg">
                {closingCta.docsLink.label}
              </ButtonLink>
            </div>
            <div className="mx-auto mt-12 max-w-2xl text-left">
              <CodeBlock code={closingCta.installCommand} label={closingCta.installLabel} prompt />
            </div>
            <p className="mt-6 text-sm">
              <Link href={closingCta.securityLink.href} className={link}>
                {closingCta.securityLink.label}
              </Link>
            </p>
          </div>
        </Container>
      </section>
    </>
  );
}
