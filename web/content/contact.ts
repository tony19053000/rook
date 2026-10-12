// The /contact page copy (06 §5.9): the email as mailto: links with prefilled subjects, GitHub Issues for bugs,
// and what to expect. There is no form (and no form backend): the CSP keeps form-action 'self'.

import { CONTACT_EMAIL, FOUNDER_LINE, ISSUES_URL, operator, site, SITE_URL } from "./site";

/** An email link (the page builds the mailto: href with mailtoHref) or a web link. */
export type ContactLink = { kind: "email"; label: string; subject: string } | { kind: "web"; label: string; href: string };

export interface ContactChannel {
  id: string;
  title: string;
  body: string;
  link: ContactLink;
}

export const contactCopy = {
  title: "Contact",
  description: `Email ${site.name} about questions, early access or privacy, or open a GitHub issue for bugs and feature requests.`,
  eyebrow: "Contact",
  heading: `Contact ${site.name}`,
  lead: `${site.name} is founder-led: ${operator.name}, the founder, reads the inbox. Email for questions, early access and privacy requests; use GitHub Issues for bugs and feature requests.`,
  email: CONTACT_EMAIL,
  emailLabel: "Email",
  founderLabel: "Founder",
  founder: FOUNDER_LINE,
  websiteLabel: "Website",
  website: SITE_URL,
  /** The subject of the plain address link at the top. */
  emailSubject: "Roook",
  channelsTitle: "How to reach Roook",
  expectTitle: "What to expect",
  expect: [
    `One person, ${operator.name}, reads every message. There is no promised response time.`,
    "The email links open your own mail app; this site has no contact form and stores nothing you send.",
    "Please never send secrets such as API keys or tokens, by email or in an issue.",
  ],
} as const;

export const contactChannels: ContactChannel[] = [
  {
    id: "general",
    title: "General questions",
    body: `Questions about ${site.name}, how it works, or whether it fits your backend.`,
    link: { kind: "email", label: "Email a question", subject: "Roook: question" },
  },
  {
    id: "early-access",
    title: "Early access",
    body: "Interest in hosted runs of your own repos, or feedback from trying Roook.",
    link: { kind: "email", label: "Email about early access", subject: "Roook: early access" },
  },
  {
    id: "privacy",
    title: "Privacy requests",
    body: "Questions about the data Roook holds about you, or a request to delete it.",
    link: { kind: "email", label: "Email a privacy request", subject: "Roook: privacy request" },
  },
  {
    id: "issues",
    title: "Bugs and feature requests",
    body: "Open an issue on the GitHub repo, so the report and its fix stay public.",
    link: { kind: "web", label: "Open a GitHub issue", href: ISSUES_URL },
  },
];
