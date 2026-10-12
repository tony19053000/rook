// The legal pages (06 §5.5), in effect. Privacy describes only what the app actually processes (06 §4 "Data the
// app actually processes"); Terms states only true facts. No compliance, certification or audit is claimed.

import { CONTACT_EMAIL, LICENSE_URL, REPO_URL, operator, site } from "./site";

/** The date both pages took effect. */
export const LEGAL_LAST_UPDATED = "12 October 2026";

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
  lastUpdated: string;
  intro: string[];
  sections: LegalSection[];
}

const operatorLine = `${operator.name}, an individual developer based in ${operator.location}`;

export const privacyPolicy: LegalDoc = {
  title: "Privacy policy",
  description: "What data the Rook site and web app process, where it is kept, who receives it, how long it is kept and how to delete it.",
  heading: "Privacy policy",
  lastUpdated: LEGAL_LAST_UPDATED,
  intro: [
    `This policy explains what data ${site.name} processes when you use this website and the ${site.name} web app. ${site.name} is run by ${operatorLine}. It describes only what the app does today.`,
  ],
  sections: [
    {
      id: "collected",
      heading: "What is collected",
      paragraphs: ["Sign-in uses Google through Supabase Auth. Supabase holds your account: your email address, name and the profile data Google provides."],
      items: [
        "Runs: the owner (your user id, or a guest key), the repository kind and reference, the status, timestamps and the IBM Bob coins used.",
        "Each run's event log, with keys and tokens redacted. It includes the request text you type into the composer and the chat.",
        "Counterexamples found by runs.",
        "If you connect GitHub: a user record with your Supabase user id, email address, GitHub installation id and the time it was created.",
        "Guest quota records, per day, keyed by the guest cookie id and by your IP address.",
        "Rate-limit counters per IP address, kept in memory only.",
      ],
    },
    {
      id: "cookies",
      heading: "Cookies and browser storage",
      items: [
        "rook_guest: a signed, httpOnly, SameSite=Lax cookie that identifies a guest browser for the guest run quota.",
        "rook_login: a signed cookie that lasts 10 minutes, set only while you sign in to the CLI.",
        "localStorage rook-auth: your sign-in session. Signing out removes it from that browser.",
        "localStorage rook.sidebar.collapsed: whether you collapsed the app's sidebar.",
      ],
    },
    {
      id: "storage",
      heading: "Where it is stored",
      items: [
        "Supabase holds your sign-in account.",
        "The Rook server keeps runs, event logs, counterexamples, user records and guest quota rows in a SQLite database on AWS EC2 in US West (Oregon).",
        "The website is hosted on Vercel.",
        "If you connect GitHub, short-lived installation tokens are kept in memory only.",
      ],
    },
    {
      id: "recipients",
      heading: "Who receives it",
      items: [
        "Supabase, for sign-in.",
        "Vercel and AWS, which host the website and the server.",
        "GitHub, only if you connect it: Rook reads your installation's repository list from GitHub.",
        "IBM Bob, for live runs only: repository content and run data are sent to IBM Bob as prompts. Recorded example runs send nothing to IBM Bob.",
      ],
      paragraphs: ["Rook does not sell your data."],
    },
    {
      id: "retention",
      heading: "How long it is kept",
      items: [
        "Runs, with their events and counterexamples, are deleted automatically after 30 days.",
        "Guest quota rows are deleted automatically after 2 days.",
        "Your Supabase sign-in account is kept until you ask for it to be deleted.",
      ],
    },
    {
      id: "delete",
      heading: "How to delete your data",
      items: [
        "Delete a single run, with its events and counterexamples, from the web app.",
        "Delete all your data on the Rook server (your runs and the GitHub link) from the account menu in the web app.",
        `To delete your Supabase sign-in account, email ${CONTACT_EMAIL}. The Rook server cannot delete it, and there is no self-serve option yet.`,
      ],
    },
    {
      id: "no-tracking",
      heading: "No analytics or tracking",
      paragraphs: ["There are no analytics, ads or tracking scripts on the site or in the app."],
    },
    {
      id: "changes",
      heading: "Changes to this policy",
      paragraphs: ["If this policy changes, the new version is published on this page with a new \"Last updated\" date."],
    },
    {
      id: "contact",
      heading: "Contact",
      paragraphs: [`Privacy questions and requests: ${CONTACT_EMAIL}. This policy is governed by the laws of ${operator.location}.`],
    },
  ],
};

export const termsOfService: LegalDoc = {
  title: "Terms of service",
  description: "The terms for using the hosted Rook website and web app.",
  heading: "Terms of service",
  lastUpdated: LEGAL_LAST_UPDATED,
  intro: [
    `These terms cover your use of the hosted ${site.name} website and web app, run by ${operatorLine}.`,
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
      heading: "The hosted site",
      paragraphs: [
        `The hosted site is provided as is during early access. There are no paid plans and no billing.`,
        "Guests can run only the example repositories, with recorded IBM Bob answers, and have a daily run limit.",
        "Features and limits may change, and the hosted site may be changed or stopped at any time.",
      ],
    },
    {
      id: "your-use",
      heading: "Acceptable use",
      items: [
        "Only test repositories you are allowed to test, and only connect repositories you are allowed to share.",
        "Don't abuse the guest quota, and don't try to get around the quotas, rate limits or sandboxing.",
        "Don't try to disrupt the service for others.",
        "You are responsible for reviewing any fix Rook proposes before you merge it.",
      ],
    },
    {
      id: "as-is",
      heading: "No warranty and limited liability",
      paragraphs: [
        "The service is provided as is and as available, without warranties of any kind.",
        `To the extent the law of ${operator.location} allows, the operator is not liable for any loss arising from its use.`,
      ],
    },
    {
      id: "law",
      heading: "Governing law and contact",
      paragraphs: [`These terms are governed by the laws of ${operator.location}. Contact: ${CONTACT_EMAIL}.`],
    },
  ],
};
