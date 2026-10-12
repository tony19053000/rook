// Pricing (06 §5.4): "Early access and open source". `plans` is the one source for a future price list: the page
// and the home FAQ derive the status from it. It is empty today; Rook has no paid plan and no billing.

import { cta, site, type NavLink } from "./site";

export interface Plan {
  name: string;
  /** The price as it should be shown, e.g. a monthly amount. */
  price: string;
  summary: string;
  features: string[];
}

export const plans: readonly Plan[] = [];

export const PRICING_PENDING_NOTICE = "Hosted plans are not offered or priced yet";

export type PricingStatus = { kind: "pending"; notice: string } | { kind: "published"; plans: readonly Plan[] };

export function pricingStatus(list: readonly Plan[]): PricingStatus {
  return list.length === 0 ? { kind: "pending", notice: PRICING_PENDING_NOTICE } : { kind: "published", plans: list };
}

/** One way to use Rook today and what it costs, in words (never a number). */
export interface UseWay {
  name: string;
  cost: string;
  details: string[];
  link: NavLink;
}

export const pricingCopy = {
  title: "Pricing",
  description: "Rook is in early access and open source: try it on this site or run the CLI on your machine. Hosted plans are not priced yet.",
  eyebrow: "Pricing",
  heading: "Early access and open source",
  lead: "Rook has no paid plans and no billing today. These are the ways to use it, and what each costs today.",
  waysTitle: "Ways to use Rook",
  /** The FAQ's cost answer after the notice (content/home.ts). */
  pendingDetails: [
    "Trying Rook on this site is free and needs no account.",
    `The CLI is free and open source under the ${site.licence}; live runs need Docker and your own IBM Bob key.`,
  ],
  interest: {
    id: "hosted-interest",
    title: "Interested in hosted Rook?",
    body: "If you would use hosted runs of your own repos, send an email saying what you would run. It helps decide what comes next.",
    link: { label: "Contact", href: "/contact" } satisfies NavLink,
  },
} as const;

export const useWays: UseWay[] = [
  {
    name: "Try Rook on this site",
    cost: "Free, no account",
    details: [
      "Recorded example runs of the example repos: IBM Bob's answers are replayed from a saved real run, and the engine runs live against the real app.",
      "3 runs a day.",
    ],
    link: cta.demo,
  },
  {
    name: "The CLI on your machine",
    cost: `Free and open source (${site.licence})`,
    details: [
      "Install it from GitHub and run it on your own repos.",
      "Live runs need Docker and your own IBM Bob key. Any IBM Bob usage cost is between you and IBM.",
    ],
    link: cta.docs,
  },
  {
    name: "Hosted runs of your own repos",
    cost: "Not offered yet",
    details: ["Planned. No price is set.", "Until then, run your own repos with the CLI."],
    link: { label: "See the roadmap", href: "/roadmap" },
  },
];
