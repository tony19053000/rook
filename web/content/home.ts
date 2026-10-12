// The marketing home (06 §5.1): hero, the 6-step diagram, the benefits and the sections after them, the FAQ and
// the closing call to action. Every claim comes from 06 §4. The refund-bug story is in ./story.ts and the
// walkthrough's copy and sample data in ./walkthrough.ts.

import { pricingCopy, type PricingStatus } from "./pricing";
import { INSTALL_COMMAND, operator, REPO_URL, site } from "./site";

export const homeHero = {
  eyebrow: "Early access · Open source",
  heading: "Find the sequence of API calls that breaks your business rules",
  lead:
    "Each call is valid on its own. Together they refund more than was paid, sell stock you don't have, or let a normal user into an admin page. Roook finds the smallest sequence that does it, proves it on your running app, and verifies the fix.",
  github: { label: "View on GitHub", href: REPO_URL },
} as const;

export interface Screenshot {
  src: string;
  /** Intrinsic size in pixels (the capture is at 1.5x or 2x). */
  width: number;
  height: number;
  alt: string;
}

/**
 * The hero's product screenshots: the finished run page of a guest minishop run, captured from the running web
 * app by e2e/capture-run.mjs (06 §4 "Recorded vs live": labelled "Recorded example run").
 */
export const runScreenshot = {
  label: "Recorded example run",
  explanation: "Bob's answers are replayed from a saved real run; the engine still runs live against the real app.",
  desktop: {
    src: "/screenshots/run-desktop.webp",
    width: 2160,
    height: 1500,
    alt: "Roook's run page for the minishop example: counterexample #001 breaks the rule \"Total refunds on an order never exceed the amount paid\" in 4 steps (create a product at price 1, buy 1, refund 1, refund 1), observed paid 1 and refunded total 2, reproduced 10/10, with the root cause at app.py line 214 reviewed by the Diagnosis Reviewer.",
  },
  mobile: {
    src: "/screenshots/run-mobile.webp",
    width: 780,
    height: 1688,
    alt: "The same run on a phone: verification by the engine, fix verified. Before: paid 1, refunded total 2, rule broken. After: the rule held in 10/10 replays. Replay, project tests, regression test and fresh search all passed.",
  },
} as const satisfies { label: string; explanation: string; desktop: Screenshot; mobile: Screenshot };

/** The 6-step diagram (content/flow.ts): who does each step. */
export const flowDiagram = {
  id: "how-it-works",
  eyebrow: "How it works",
  title: "Six steps, from your repo to a verified fix",
  intro: "Bob agents read, propose and write. The deterministic engine searches, replays and verifies. You approve the rules and the fix.",
  listLabel: "The six steps of a Roook run",
  actors: {
    understand: ["Bob"],
    rules: ["Bob", "You approve"],
    search: ["Engine"],
    shrink: ["Engine"],
    fix: ["Bob", "You approve"],
    verify: ["Engine"],
  } as Record<string, string[]>,
} as const;

export interface HomeItem {
  title: string;
  body: string;
}

export const featuresSection = {
  id: "features",
  eyebrow: "What you get",
  title: "Proof you can keep, not a prediction",
  intro: "Each finding is a sequence that ran on your app, and each fix is checked the same way.",
} as const;

export const features: HomeItem[] = [
  {
    title: "Proof, not a guess",
    body: "A bug counts only when the deterministic engine breaks an approved rule on your running app. No AI decides pass or fail.",
  },
  {
    title: "The smallest reproduction",
    body: "A failing sequence is shrunk to a minimal one, steps first and then values, and replayed on the real app, 10 times by default. Flaky results are reported as flaky.",
  },
  {
    title: "A failing test you can keep",
    body: "Each counterexample is saved as a JSON file plus a regression test in your repo. In the refund case, the test failed on the unfixed code and passed after the fix.",
  },
  {
    title: "A fix that is checked, not trusted",
    body: "A fix counts only if four engine checks pass: exact replay, your project's tests, the generated regression test, and a fresh search with a new seed.",
  },
  {
    title: "Rules you approve, in your repo",
    body: "Bob proposes business rules with evidence from your code and a critic rejects weak ones. Only the rules you approve are checked; they live in rook/rook.yaml.",
  },
  {
    title: "The fix lands on its own branch",
    body: "Never on your default branch: a rook/fix-* branch, as a pull request for a GitHub repo or a local branch for a folder.",
  },
  {
    title: "In your terminal and your pull requests",
    body: "An interactive rook terminal session, the web app, and a GitHub Action that fails the job if an approved rule breaks.",
  },
  {
    title: "Any backend with an HTTP API",
    body: "In any language. The example apps are written in Node.js, Python (FastAPI) and Go.",
  },
];

export const refusalsSection = {
  id: "guarantees",
  eyebrow: "Guarantees",
  title: "What Roook refuses to do",
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
    body: "The sandbox gets none of Roook's environment, and a redaction filter scrubs keys and tokens from events and logs.",
  },
  {
    title: "Run arbitrary repos for guests",
    body: "On the hosted site, guests run only allowlisted example repos, pinned by commit SHA.",
  },
];

export const scopeSection = {
  id: "today",
  eyebrow: "Honest scope",
  title: "Where Roook is today",
  intro: "Roook is in early access. Here is exactly what works today, and what doesn't yet.",
} as const;

export const scope: string[] = [
  "No paid plans, no billing, no team accounts and no SSO.",
  "Guest runs on the hosted site offer two example repos, shop-app (Node.js) and minishop (Python), with recorded IBM Bob answers labelled \"recorded\". Guests get 3 runs a day.",
  "Hosted runs of your own repos are turned off on the hosted server for now. Run your own repos with the CLI on your machine.",
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
        "Not for trying Roook on the hosted site, or for running the CLI on a folder on your machine. Signing in with Google is needed to work with your GitHub repos, from the web app or the CLI.",
    },
    {
      question: "Will Roook change my code?",
      answer:
        "Only after you approve. The Surgeon edits a workspace copy, only in the approved files. The fix goes to a rook/fix-* branch (a pull request for a GitHub repo), never to your default branch.",
    },
    {
      question: "Is my code sent to an AI?",
      answer:
        "In live runs, repo content and run data go to IBM Bob as prompts. Guest runs on the hosted site use recorded Bob answers. Bob is the only AI in Roook.",
    },
    {
      question: "Who makes Roook?",
      answer: `${operator.name}, the founder, based in ${operator.location}. Roook is an independent, early-stage startup: the product is in early access, open source under the ${site.licence}, and built on IBM Bob.`,
    },
    { question: "What does it cost?", answer: costAnswer(status) },
  ];
}

export const closingCta = {
  id: "get-started",
  title: "See it break, then see it fixed",
  body: "Try Roook on the hosted site in your browser, or install the CLI and point it at your own backend.",
  installLabel: "Install the CLI (Python 3.12+, Docker, IBM Bob Shell)",
  installCommand: INSTALL_COMMAND,
  docsLink: { label: "Read how it works", href: "/docs" },
  securityLink: { label: "Read the security page", href: "/security" },
} as const;
