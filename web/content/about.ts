// The /about page copy (06 §5.7): what Roook is, its founder, why it exists, the project story and where it stands.
// The only place on the site that mentions the hackathon (06 §4 "Positioning").

import { CONTACT_EMAIL, cta, FOUNDER_LINE, operator, REPO_URL, site, SITE_URL, type NavLink } from "./site";

export interface AboutSection {
  id: string;
  title: string;
  paragraphs: string[];
  items?: string[];
}

export const aboutCopy = {
  title: "About",
  description: `${site.name} is an independent, founder-led developer-tools startup. What it does, who runs it and how it started.`,
  eyebrow: "About",
  heading: `About ${site.name}`,
  lead: `${site.name} is a developer tool for finding, reproducing and verifying business-logic failures in backends. It is an independent, early-stage startup, founded and run by ${operator.name}.`,
} as const;

/** The founder card on /about (06 §4 "Operator and contact"): only facts that are true today, no invented history. */
export const founderCopy = {
  id: "founder",
  title: "Founder",
  line: FOUNDER_LINE,
  name: operator.name,
  role: `${operator.role}, ${site.name}`,
  paragraphs: [
    `${operator.name} founded ${site.name} and builds and runs it: the product, the hosted site and the inbox. ${site.name} is based in ${operator.location}.`,
    `${site.name} is founder-led and independent. It is early: one person, the code in the open, and a product that says plainly what it does and what it does not do yet.`,
  ],
  emailLabel: "Email",
  email: CONTACT_EMAIL,
  /** The subject of the founder card's email link. */
  emailSubject: site.name,
  websiteLabel: "Website",
  website: SITE_URL,
} as const;

/** What Roook does (06 §4): each line is as strong as the code, no more. */
export const aboutCapabilities = {
  id: "what",
  title: `What ${site.name} does`,
  paragraphs: [
    `${site.name} works on backends with an HTTP API. It looks for a sequence of valid requests that breaks a business rule, such as refunding more than was paid, and shows the result on the real running app.`,
  ],
  items: [
    "Finds: a deterministic, seeded search runs sequences of requests against your running app and checks every rule you approved after every step.",
    "Reproduces: a failing sequence is shrunk to a minimal one and replayed on the real app, 10 times by default. Results that do not repeat are reported as flaky. Each counterexample is saved as a JSON file plus a regression test.",
    "Verifies: a fix counts only if four engine checks pass: exact replay, your project's tests, the generated regression test, and a fresh search with a new seed.",
    "Keeps AI out of the verdict: IBM Bob's agents read the code, propose rules and write fixes. Only the deterministic engine decides whether a rule is broken or a fix is verified.",
  ],
} as const satisfies AboutSection;

export const aboutSections: AboutSection[] = [
  {
    id: "why",
    title: `Why ${site.name} exists`,
    paragraphs: [
      "Backends that hold money, stock, permissions or state can break a business rule through a sequence of requests that are each valid on their own. In the shop-app example, buying for ₹100, then refunding ₹60 and ₹50, refunds more than was paid.",
      `Tests cover the scenarios someone thought of, and a reviewer that says a bug might exist is only predicting. ${site.name} runs the failing sequence and keeps it as a test, so the report is a proof.`,
    ],
  },
  {
    id: "story",
    title: "The story so far",
    paragraphs: [
      `${site.name} started at the IBM Bob 2.0 Hackathon in September 2026.`,
      `It has continued since as an independent product: in early access, open source under the ${site.licence}, built on IBM Bob, with the code on GitHub.`,
    ],
  },
  {
    id: "today",
    title: `Where ${site.name} stands`,
    paragraphs: [],
    items: [
      `Independent and founder-led: ${site.name} is operated by ${operator.name} as an individual and is not incorporated as a company. There are no employees and no outside funding.`,
      "Free in early access: there are no paid plans, no billing, no team accounts and no SSO.",
      "Still being built: the roadmap lists what is limited today and what is planned.",
    ],
  },
];

export const aboutLinks: NavLink[] = [
  { label: "Contact", href: "/contact" },
  { label: "Roadmap", href: "/roadmap" },
  { label: cta.docs.label, href: cta.docs.href },
  { label: "Source on GitHub", href: REPO_URL, external: true },
];
