import Link from "next/link";
import { Badge } from "./Badge";
import { ButtonLink } from "./Button";
import { Card } from "./Card";
import { Container, Grid } from "./Container";
import { PageHeader } from "./PageHeader";
import { type } from "./tokens";
import { pricingCopy, pricingStatus, useWays, type Plan } from "@/content/pricing";

// Pricing (06 §5.4): the status comes only from the plans list. With none it shows the ways to use Roook today,
// the notice and the hosted-interest link; with plans, the plans replace them.
export function PricingView({ plans }: { plans: readonly Plan[] }) {
  const status = pricingStatus(plans);
  return (
    <>
      <PageHeader eyebrow={pricingCopy.eyebrow} heading={pricingCopy.heading} lead={pricingCopy.lead} width="wide" />
      <Container className="py-14 sm:py-20">
        {status.kind === "pending" ? (
          <>
            <section aria-labelledby="ways-title">
              <h2 id="ways-title" className={`${type.h2Doc} text-site-ink`}>
                {pricingCopy.waysTitle}
              </h2>
              <Grid className="mt-8">
                {useWays.map((way, i) => (
                  <Card key={way.name} as="article" className="group relative flex flex-col transition-colors hover:border-site-strong sm:p-8">
                    <p aria-hidden className={type.label}>
                      {String(i + 1).padStart(2, "0")}
                    </p>
                    <h3 className="mt-4 text-xl leading-snug font-semibold tracking-[-0.015em] text-site-ink">{way.name}</h3>
                    <p className="mt-4">
                      <Badge tone="neutral">{way.cost}</Badge>
                    </p>
                    <ul className="site-list mt-6 flex-1 border-t border-site-line pt-6 text-[0.9375rem] leading-relaxed text-site-muted">
                      {way.details.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                    <p className="mt-8 text-sm font-medium">
                      {/* The link's hit area is the whole card. */}
                      <Link href={way.link.href} className="inline-flex items-center gap-1.5 text-site-ink after:absolute after:inset-0 after:rounded-2xl">
                        {way.link.label}
                        <svg aria-hidden width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-site-muted transition-transform group-hover:translate-x-0.5">
                          <path d="M2.5 7h9M8 3.5 11.5 7 8 10.5" />
                        </svg>
                      </Link>
                    </p>
                  </Card>
                ))}
              </Grid>
              <p data-pricing-notice className="mt-6 flex items-center gap-3 text-[0.9375rem] text-site-muted">
                <span aria-hidden className="size-1.5 flex-none rounded-full bg-site-warn" />
                {status.notice}
              </p>
            </section>
            <section
              id={pricingCopy.interest.id}
              aria-labelledby={`${pricingCopy.interest.id}-title`}
              className="site-panel mt-14 flex flex-col gap-6 rounded-2xl p-6 sm:mt-20 sm:p-10 lg:flex-row lg:items-center lg:justify-between lg:gap-12"
            >
              <div className="max-w-2xl">
                <h2 id={`${pricingCopy.interest.id}-title`} className={`${type.h2Doc} text-site-ink`}>
                  {pricingCopy.interest.title}
                </h2>
                <p className={`${type.body} mt-3`}>{pricingCopy.interest.body}</p>
              </div>
              <div className="flex-none">
                <ButtonLink href={pricingCopy.interest.link.href} size="lg">
                  {pricingCopy.interest.link.label}
                </ButtonLink>
              </div>
            </section>
          </>
        ) : (
          <Grid>
            {status.plans.map((plan) => (
              <Card key={plan.name} as="article" className="sm:p-8">
                <h2 className="text-xl leading-snug font-semibold tracking-[-0.015em] text-site-ink">{plan.name}</h2>
                <p className="mt-3">
                  <Badge>{plan.price}</Badge>
                </p>
                <p className={`${type.body} mt-5`}>{plan.summary}</p>
                <ul className="site-list mt-5 text-[0.9375rem] leading-relaxed text-site-muted">
                  {plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              </Card>
            ))}
          </Grid>
        )}
      </Container>
    </>
  );
}
