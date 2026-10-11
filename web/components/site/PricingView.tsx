import { Badge } from "./Badge";
import { Card } from "./Card";
import { Container, Grid } from "./Container";
import { space, type } from "./tokens";
import { pricingCopy, pricingStatus, type Plan } from "@/content/pricing";

// Pricing (06 §5.4): the status comes only from the plans list. With none it shows the launch notice.
export function PricingView({ plans }: { plans: readonly Plan[] }) {
  const status = pricingStatus(plans);
  return (
    <Container className={space.pageTop}>
      <h1 className={`${type.h1} text-site-ink`}>{pricingCopy.heading}</h1>
      {status.kind === "pending" ? (
        <div className="mt-10 max-w-2xl">
          <Card>
            <p data-pricing-notice className={`${type.h3} text-site-ink`}>
              {status.notice}
            </p>
            <ul className="mt-4 flex flex-col gap-3">
              {pricingCopy.pendingDetails.map((line) => (
                <li key={line} className={type.body}>
                  {line}
                </li>
              ))}
            </ul>
          </Card>
        </div>
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
