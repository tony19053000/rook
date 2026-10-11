// Pricing (06 §5.4). `plans` is the one source: the page and anything else that mentions pricing derive the status
// from it. It is empty today; Rook has no paid plan and no billing.

import { site } from "./site";

export interface Plan {
  name: string;
  /** The price as it should be shown, e.g. a monthly amount. */
  price: string;
  summary: string;
  features: string[];
}

export const plans: readonly Plan[] = [];

export const PRICING_PENDING_NOTICE = "Pricing will be published at launch";

export type PricingStatus = { kind: "pending"; notice: string } | { kind: "published"; plans: readonly Plan[] };

export function pricingStatus(list: readonly Plan[]): PricingStatus {
  return list.length === 0 ? { kind: "pending", notice: PRICING_PENDING_NOTICE } : { kind: "published", plans: list };
}

export const pricingCopy = {
  title: "Pricing",
  description: "Pricing for Rook, the open-source tool that proves business-rule bugs and verifies the fixes.",
  heading: "Pricing",
  pendingDetails: [
    "There is no paid plan and no billing in Rook today.",
    `The code is open source under the ${site.licence}: you can install the CLI and run it on your own machine. Live runs need Docker and your own IBM Bob key.`,
    "The hosted demo is open without an account.",
  ],
} as const;
