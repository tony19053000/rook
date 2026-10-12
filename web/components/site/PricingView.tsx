import Link from "next/link";
import { Badge } from "./Badge";
import { ButtonLink } from "./Button";
import { Card } from "./Card";
import { Container, Grid } from "./Container";
import { space, type } from "./tokens";
import { pricingCopy, pricingStatus, useWays, type Plan } from "@/content/pricing";

// Pricing (06 §5.4): the status comes only from the plans list. With none it shows the ways to use Rook today,
// the notice and the hosted-interest link; with plans, the plans replace them.
export function PricingView({ plans }: { plans: readonly Plan[] }) {
  const status = pricingStatus(plans);
  return (
    <Container className={space.pageTop}>
      <p className={type.eyebrow}>{pricingCopy.eyebrow}</p>
      <h1 className={`${type.h1} mt-4 max-w-3xl text-site-ink`}>{pricingCopy.heading}</h1>
      <p className={`${type.lead} mt-5 max-w-2xl`}>{pricingCopy.lead}</p>
      {status.kind === "pending" ? (
        <>
          <section aria-labelledby="ways-title" className="mt-12">
            <h2 id="ways-title" className={`${type.h2} text-site-ink`}>
              {pricingCopy.waysTitle}
            </h2>
            <Grid className="mt-8">
              {useWays.map((way) => (
                <Card key={way.name} as="article" className="flex flex-col">
                  <h3 className={`${type.h3} text-site-ink`}>{way.name}</h3>
                  <p className="mt-3">
                    <Badge tone="accent">{way.cost}</Badge>
                  </p>
                  <ul className="mt-4 flex flex-1 flex-col gap-2">
                    {way.details.map((line) => (
                      <li key={line} className={type.small}>
                        {line}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-6">
                    <Link href={way.link.href} className="text-sm text-site-link underline underline-offset-4">
                      {way.link.label}
                    </Link>
                  </p>
                </Card>
              ))}
            </Grid>
            <p data-pricing-notice className={`${type.body} mt-6 max-w-2xl`}>
              {status.notice}
            </p>
          </section>
          <section id={pricingCopy.interest.id} aria-labelledby={`${pricingCopy.interest.id}-title`} className="mt-16 max-w-2xl">
            <h2 id={`${pricingCopy.interest.id}-title`} className={`${type.h2} text-site-ink`}>
              {pricingCopy.interest.title}
            </h2>
            <p className={`${type.body} mt-4`}>{pricingCopy.interest.body}</p>
            <div className="mt-6">
              <ButtonLink href={pricingCopy.interest.link.href} variant="secondary">
                {pricingCopy.interest.link.label}
              </ButtonLink>
            </div>
          </section>
        </>
      ) : (
        <Grid className="mt-10">
          {status.plans.map((plan) => (
            <Card key={plan.name} as="article">
              <h2 className={`${type.h3} text-site-ink`}>{plan.name}</h2>
              <p className="mt-2">
                <Badge>{plan.price}</Badge>
              </p>
              <p className={`${type.body} mt-4`}>{plan.summary}</p>
              <ul className="mt-4 flex flex-col gap-2">
                {plan.features.map((feature) => (
                  <li key={feature} className={type.small}>
                    {feature}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </Grid>
      )}
    </Container>
  );
}
