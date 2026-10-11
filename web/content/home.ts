// The marketing home (06 §5.1): hero, the sections after the walkthrough, the FAQ and the closing call to
// action. Every claim comes from 06 §4. The walkthrough's copy and sample data are in ./walkthrough.ts.

import { pricingCopy, type PricingStatus } from "./pricing";
import { INSTALL_COMMAND, site } from "./site";

export const homeHero = {
  eyebrow: site.builtOn.replace(/\.$/, ""),
  heading: "Find the smallest sequence that breaks your software, before your users do.",
  lead: site.oneLiner,
} as const;

/** The hero's product figure: an illustration of a Rook result (the shop-app refund bug). */
export const heroFigure = {
  caption: "Illustration of a Rook result",
  title: "Counterexample #1",
  status: "Rule broken",
  rule: "Total refunds on an order never exceed the amount paid",
  steps: ["buy ₹100", "refund ₹60", "refund ₹50"],
  observed: [
    { label: "paid", value: "₹100" },
    { label: "refunded", value: "₹110" },
  ],
  replayed: "Replayed 10/10 on the real app",
  test: "Regression test saved",
} as const;

export interface HomeItem {
  title: string;
  body: string;
}

export const featuresSection = {
  id: "features",
  eyebrow: "Features",
  title: "Proof, not predictions",
  intro: "Every finding is an executed sequence on your running app, and every fix is checked the same way.",
} as const;

export const features: HomeItem[] = [
  {
    title: "Proof by execution",
    body: "The engine runs seeded, reproducible sequences of valid actions against your real running app and checks every approved rule after every step.",
  },
  {
    title: "The smallest reproduction",
    body: "A failing sequence is shrunk to a minimal one, then replayed on the real app, 10 times by default. Flaky results are reported as flaky.",
  },
  {
    title: "A regression test, saved",
    body: "Each counterexample is saved as a JSON file plus a regression test in your repo.",
  },
  {
    title: "Verified fixes",
    body: "A fix counts only if four engine checks pass: exact replay, your project's tests, the generated regression test, and a fresh search with a new seed.",
  },
  {
    title: "Rules you approve",
    body: "Bob proposes business rules with evidence from your code and a critic rejects weak ones. Only the rules you approve are checked; they live in rook/rook.yaml.",
  },
  {
    title: "CLI, web app and GitHub Action",
    body: "An interactive rook terminal session, the web app, and a GitHub Action that runs on pull requests and fails the job if an approved rule breaks.",
  },
  {
    title: "Any backend with an HTTP API",
    body: "In any language. The example apps are written in Node.js, Python (FastAPI) and Go.",
  },
  {
    title: "13 Bob agents, one deciding engine",
    body: "A Coordinator and 12 specialists, from Scout to Surgeon, run as IBM Bob custom modes. Only the deterministic engine marks a rule broken or a fix verified.",
  },
];

export const refusalsSection = {
  id: "guarantees",
  eyebrow: "Guarantees",
  title: "What Rook refuses to do",
  intro: "Each of these is enforced in code, not left to a prompt.",
} as const;

export const refusals: HomeItem[] = [
  { title: "Let an AI decide pass or fail", body: "Only the deterministic engine marks a rule broken or a fix verified." },
  {
    title: "Execute AI-generated code",
    body: "Rules go through a safe expression evaluator and actions are declarative HTTP templates. Model output is never run with eval or exec.",
  },
  {
    title: "Change your code without your approval",
    body: "Only the Surgeon edits, only in a workspace copy, only the approved files; any other change is reverted. --auto skips the questions, but the fix still lands on its own branch for review.",
  },
  {
    title: "Push to your default branch",
    body: "Fixes go to a rook/fix-<id> branch; for a GitHub repo they arrive as a pull request from it.",
  },
  {
    title: "Call anything but your sandboxed app",
    body: "The engine only sends requests to the sandbox's host and port, follows no redirects elsewhere, and stops at a 10 s timeout and a 1 MB response cap.",
  },
  {
    title: "Hand your secrets to the app or the logs",
    body: "The sandbox gets none of Rook's environment, and a redaction filter scrubs keys and tokens from events and logs.",
  },
  {
    title: "Run arbitrary repos for guests",
    body: "On the hosted site, guests run only allowlisted example repos, pinned by commit SHA.",
  },
];

export const scopeSection = {
  id: "today",
  eyebrow: "Honest scope",
  title: "Where Rook is today",
  intro: "A hackathon-stage project, built for the IBM Bob 2.0 Hackathon in September 2026. Here is exactly what that means.",
} as const;

export const scope: string[] = [
  "No paid plans, no billing, no team accounts and no SSO.",
  "Guest runs on the hosted site offer shop-app only, with recorded IBM Bob answers labelled \"recorded\". Guests get 3 runs a day.",
  "Signed-in users with the GitHub App linked can run their own repos on the hosted server only when the server enables it: one such run at a time server-wide, 5 per user per day. Otherwise the CLI runs your repos on your machine.",
  "HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.",
  "Not on PyPI yet: install from GitHub. Live runs need Docker and your own IBM Bob key.",
  "In the web app, editing a single rule, replaying a counterexample and downloading the test are not built yet.",
];

export const faqSection = {
  id: "faq",
  eyebrow: "FAQ",
  title: "Questions",
} as const;

export interface FaqItem {
  question: string;
  answer: string;
}

/** The cost answer, derived from the pricing status (content/pricing.ts), never restated here. */
export function costAnswer(status: PricingStatus): string {
  if (status.kind === "published") {
    return `Plans: ${status.plans.map((plan) => plan.name).join(", ")}. See the pricing page for what each includes.`;
  }
  return [`${status.notice}.`, ...pricingCopy.pendingDetails].join(" ");
}

export function homeFaq(status: PricingStatus): FaqItem[] {
  return [
    {
      question: "Does an AI decide whether my code is broken?",
      answer:
        "No. Bob agents read the code, propose rules and write fixes, but only the deterministic engine marks a rule broken (by running the sequence on your app) or a fix verified (by its four checks).",
    },
    {
      question: "Which languages does it work with?",
      answer:
        "Any backend with an HTTP API, in any language. The example apps are Node.js, Python (FastAPI) and Go. Libraries, pure frontends, mobile apps and ML notebooks are out of scope.",
    },
    {
      question: "Do I need an account?",
      answer:
        "Not for trying Rook on the hosted site, or for running the CLI on a folder on your machine. Signing in with Google is needed to work with your GitHub repos, from the web app or the CLI.",
    },
    {
      question: "Will Rook change my code?",
      answer:
        "Only after you approve. The Surgeon edits a workspace copy, only in the approved files. The fix goes to a rook/fix-* branch (a pull request for a GitHub repo), never to your default branch.",
    },
    {
      question: "Is my code sent to an AI?",
      answer:
        "In live runs, repo content and run data go to IBM Bob as prompts. Guest runs on the hosted site use recorded Bob answers. Bob is the only AI in Rook.",
    },
    { question: "What does it cost?", answer: costAnswer(status) },
  ];
}

export const closingCta = {
  id: "get-started",
  title: "See it break, then see it fixed",
  body: "Try Rook on the hosted site in your browser, or install the CLI and point it at your own backend.",
  installLabel: "Install the CLI (Python 3.12+, Docker, IBM Bob Shell)",
  installCommand: INSTALL_COMMAND,
  docsLink: { label: "Read how it works", href: "/docs" },
  securityLink: { label: "Read the security page", href: "/security" },
} as const;
