// The legal drafts (06 §5.5). Privacy describes only what the app actually processes (06 §4); Terms states only
// true facts. Both stay visibly marked as drafts with placeholders until legal review.

import { LICENSE_URL, REPO_URL, site } from "./site";

export const LEGAL_DRAFT_BANNER = "Draft — pending legal review, not yet in effect";

export const legalPlaceholders = {
  company: "[Company legal name]",
  contact: "[contact email]",
  jurisdiction: "[jurisdiction]",
} as const;

export interface LegalSection {
  id: string;
  heading: string;
  paragraphs?: string[];
  items?: string[];
}

export interface LegalDoc {
  title: string;
  description: string;
  heading: string;
  intro: string[];
  sections: LegalSection[];
}

const { company, contact, jurisdiction } = legalPlaceholders;

export const privacyPolicy: LegalDoc = {
  title: "Privacy policy (draft)",
  description: "What data the Rook site and web app process, where it is kept, and who it is shared with. Draft.",
  heading: "Privacy policy",
  intro: [
    `This policy explains what data ${site.name} (operated by ${company}) processes when you use this website and the ${site.name} web app. It describes only what the app does today.`,
  ],
  sections: [
    {
      id: "sign-in",
      heading: "Signing in with Google",
      paragraphs: [
        "Sign-in uses Google through Supabase Auth. Supabase holds your account: your email address, name and the profile data Google provides.",
        "Your browser keeps the Supabase session in localStorage under the key rook-auth. Signing out removes it from that browser.",
      ],
    },
    {
      id: "server-data",
      heading: "What the Rook server stores",
      paragraphs: ["The Rook server keeps a database with:"],
      items: [
        "Runs: the owner (your user id, or a guest key), the repository kind and reference, the status, timestamps and the IBM Bob coins used.",
        "Each run's event log, with keys and tokens redacted. It includes the request text you type into the composer and the chat.",
        "Counterexamples found by runs.",
        "If you connect GitHub: a user record with your Supabase user id, email address, GitHub installation id and the time it was created.",
        "Guest quota records, per day, keyed by the guest cookie id and by your IP address.",
      ],
    },
    {
      id: "rate-limits",
      heading: "Rate limiting",
      paragraphs: ["The server limits requests per IP address. These counters are kept in memory only."],
    },
    {
      id: "cookies",
      heading: "Cookies and browser storage",
      items: [
        "rook_guest: a signed, httpOnly, SameSite=Lax cookie that identifies a guest browser for the guest run quota.",
        "rook_login: a signed cookie that lasts 10 minutes, set only while you sign in to the CLI.",
        "localStorage rook-auth: your sign-in session.",
        "localStorage rook.sidebar.collapsed: whether you collapsed the app's sidebar.",
      ],
    },
    {
      id: "github",
      heading: "GitHub (only if you connect it)",
      items: [
        "Your GitHub App installation id.",
        "The list of repositories your installation shares, as GitHub reports it.",
        "Short-lived installation tokens, kept in memory only.",
        "For a run of one of your repositories on the hosted server, the repository is cloned into a server workspace.",
      ],
    },
    {
      id: "ibm-bob",
      heading: "IBM Bob",
      paragraphs: [
        "In live runs, repository content and run data are sent to IBM Bob as prompts. Guest runs use recorded IBM Bob answers instead.",
      ],
    },
    {
      id: "hosting",
      heading: "Hosting",
      paragraphs: [
        "The website runs on Vercel. The API runs on AWS EC2 behind Caddy.",
        "Runs are not deleted automatically today.",
      ],
    },
    {
      id: "no-tracking",
      heading: "No analytics or tracking",
      paragraphs: ["There are no analytics, ads or tracking scripts on the site or in the app."],
    },
    {
      id: "contact",
      heading: "Contact",
      paragraphs: [`Questions about this policy or your data: ${contact}. This policy is governed by the laws of ${jurisdiction}.`],
    },
  ],
};

export const termsOfService: LegalDoc = {
  title: "Terms of service (draft)",
  description: "The draft terms for using the hosted Rook website and web app.",
  heading: "Terms of service",
  intro: [
    `These terms cover your use of the hosted ${site.name} website and web app, operated by ${company}.`,
  ],
  sections: [
    {
      id: "open-source",
      heading: "The open-source code",
      paragraphs: [
        `${site.name}'s source code is published at ${REPO_URL} under the MIT licence (${LICENSE_URL}). Your use of the code itself is governed by that licence, not by these terms.`,
      ],
    },
    {
      id: "hosted-service",
      heading: "The hosted service",
      paragraphs: [
        `${site.name} is a hackathon-stage project. There are no paid plans and no billing.`,
        "Guests can run only the allowlisted example repositories, with recorded IBM Bob answers, and have a daily run limit.",
        "Runs of your own GitHub repositories on the hosted server are available only when the server enables them, with a daily limit per user.",
        "Limits and features may change or be withdrawn at any time.",
      ],
    },
    {
      id: "your-use",
      heading: "Your use",
      items: [
        "Only connect repositories you are allowed to share.",
        "Don't try to get around the quotas, rate limits or sandboxing, or to disrupt the service for others.",
        "You are responsible for reviewing any fix Rook proposes before you merge it.",
      ],
    },
    {
      id: "as-is",
      heading: "No warranty",
      paragraphs: [
        "The service is provided as is and as available, without warranties of any kind. To the extent the law allows, the operator is not liable for any loss arising from its use.",
      ],
    },
    {
      id: "law",
      heading: "Governing law and contact",
      paragraphs: [`These terms are governed by the laws of ${jurisdiction}. Contact: ${contact}.`],
    },
  ],
};
