import Link from "next/link";
import { ButtonLink } from "@/components/site/Button";
import { Card } from "@/components/site/Card";
import { CodeBlock } from "@/components/site/CodeBlock";
import { Grid } from "@/components/site/Container";
import { Section } from "@/components/site/Section";
import { HeroFigure } from "@/components/site/home/HeroFigure";
import { HeroParallax } from "@/components/site/home/HeroParallax";
import { Walkthrough } from "@/components/site/home/Walkthrough";
import { measure, type } from "@/components/site/tokens";
import {
  closingCta,
  faqSection,
  features,
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
import { walkthroughCopy } from "@/content/walkthrough";

const HERO_TITLE_ID = "hero-title";

// The marketing home (06 §5.1). A server component: only the hero's parallax and the walkthrough are client
// islands (the only places `motion` and timers are used). Everything is in the server render.
export default function HomePage() {
  const faq = homeFaq(pricingStatus(plans));
  return (
    <>
      <HeroParallax
        labelledBy={HERO_TITLE_ID}
        text={
          <>
            <p className={type.eyebrow}>{homeHero.eyebrow}</p>
            <h1 id={HERO_TITLE_ID} className={`${type.display} mt-5 text-site-ink`}>
              {homeHero.heading}
            </h1>
            <p className={`${type.lead} mt-6 max-w-2xl`}>{homeHero.lead}</p>
            <div className="mt-10 flex flex-wrap justify-center gap-3">
              <ButtonLink href={cta.demo.href} size="lg">
                {cta.demo.label}
              </ButtonLink>
              <ButtonLink href={cta.signIn.href} variant="secondary" size="lg">
                {cta.signIn.label}
              </ButtonLink>
            </div>
          </>
        }
        figure={<HeroFigure />}
      />

      <Section id={walkthroughCopy.id} eyebrow={walkthroughCopy.eyebrow} title={walkthroughCopy.title} intro={walkthroughCopy.intro}>
        <Walkthrough />
      </Section>

      <Section id={featuresSection.id} eyebrow={featuresSection.eyebrow} title={featuresSection.title} intro={featuresSection.intro}>
        <Grid columns={2} className="lg:grid-cols-4">
          {features.map((item) => (
            <Card key={item.title} as="article">
              <h3 className={`${type.h3} text-site-ink`}>{item.title}</h3>
              <p className={`${type.small} mt-2`}>{item.body}</p>
            </Card>
          ))}
        </Grid>
      </Section>

      <Section id={refusalsSection.id} eyebrow={refusalsSection.eyebrow} title={refusalsSection.title} intro={refusalsSection.intro}>
        <ul className="grid gap-x-10 gap-y-6 md:grid-cols-2 xl:grid-cols-4 xl:gap-x-8">
          {refusals.map((item) => (
            <li key={item.title} className="flex gap-4 border-t border-site-line pt-5">
              <span aria-hidden className="font-mono text-site-accent">
                ✗
              </span>
              <div>
                <h3 className={`${type.h3} text-site-ink`}>{item.title}</h3>
                <p className={`${type.small} mt-1.5`}>{item.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={scopeSection.id} eyebrow={scopeSection.eyebrow} title={scopeSection.title} intro={scopeSection.intro}>
        <ul className={`flex flex-col gap-3 ${measure}`}>
          {scope.map((line) => (
            <li key={line} className={`${type.body} flex gap-3`}>
              <span aria-hidden className="text-site-faint">
                —
              </span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id={faqSection.id} eyebrow={faqSection.eyebrow} title={faqSection.title}>
        <div className={`${measure} flex flex-col divide-y divide-site-line border-y border-site-line`}>
          {faq.map((item) => (
            <details key={item.question} className="group py-1">
              <summary className="flex cursor-pointer items-center justify-between gap-4 rounded-md py-4 font-medium text-site-ink">
                {item.question}
                <span aria-hidden className="font-mono text-site-faint group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className={`${type.body} pb-5`}>{item.answer}</p>
            </details>
          ))}
        </div>
      </Section>

      <Section id={closingCta.id} title={closingCta.title} intro={closingCta.body} className="border-t border-site-line">
        <div className="grid gap-8 lg:grid-cols-2 lg:items-start">
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap gap-3">
              <ButtonLink href={cta.demo.href} size="lg">
                {cta.demo.label}
              </ButtonLink>
              <ButtonLink href={closingCta.docsLink.href} variant="secondary" size="lg">
                {closingCta.docsLink.label}
              </ButtonLink>
            </div>
            <Link href={closingCta.securityLink.href} className="w-fit rounded-md text-sm text-site-link hover:underline">
              {closingCta.securityLink.label}
            </Link>
          </div>
          <CodeBlock code={closingCta.installCommand} label={closingCta.installLabel} prompt />
        </div>
      </Section>
    </>
  );
}
