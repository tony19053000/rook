// The /about page copy (06 §5.7): who runs Roook, why it exists, the project story and what it is not. The only
// place on the site that mentions the hackathon (06 §4 "Positioning").

import { cta, operator, REPO_URL, site, type NavLink } from "./site";

export interface AboutSection {
  id: string;
  title: string;
  paragraphs: string[];
  items?: string[];
}

export const aboutCopy = {
  title: "About",
  description: `Who runs ${site.name}, why it exists, and how it started.`,
  eyebrow: "About",
  heading: `About ${site.name}`,
  lead: `${site.name} is an early-access, open-source developer tool, run by ${operator.name}, an individual developer in ${operator.location}.`,
} as const;

export const aboutSections: AboutSection[] = [
  {
    id: "who",
    title: `Who runs ${site.name}`,
    paragraphs: [
      `${site.name} is built and run by ${operator.name}, an individual developer based in ${operator.location}. One person runs the project, the hosted site and the inbox.`,
    ],
  },
  {
    id: "why",
    title: `Why ${site.name} exists`,
    paragraphs: [
      "Backends that hold money, stock, permissions or state can break a business rule through a sequence of requests that are each valid on their own. In the shop-app example, buying for ₹100, then refunding ₹60 and ₹50, refunds more than was paid.",
      `${site.name} searches for the smallest such sequence, proves it on the real running app, and checks that a fix holds. IBM Bob's agents read the code, propose rules and write fixes; only the deterministic engine decides whether a rule is broken or a fix is verified.`,
    ],
  },
  {
    id: "story",
    title: "The story so far",
    paragraphs: [
      `${site.name} started at the IBM Bob 2.0 Hackathon in September 2026.`,
      `It is now an early-access, open-source project under the ${site.licence}, built on IBM Bob, with the code on GitHub.`,
    ],
  },
  {
    id: "not",
    title: `What ${site.name} is not`,
    paragraphs: [],
    items: [
      "Not a company: there is no incorporation, no employees and no outside funding.",
      "Not a paid product: there are no paid plans, no billing, no team accounts and no SSO.",
      "Not finished: the roadmap lists what is limited today and what is planned.",
    ],
  },
];

export const aboutLinks: NavLink[] = [
  { label: "Contact", href: "/contact" },
  { label: "Roadmap", href: "/roadmap" },
  { label: cta.docs.label, href: cta.docs.href },
  { label: "Source on GitHub", href: REPO_URL, external: true },
];
