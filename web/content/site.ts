// Site-wide copy and links (06 §4). Every repeated fact (name, repo URL, install command) is defined once here.

export const REPO_URL = "https://github.com/tony19053000/rook";
export const INSTALL_COMMAND = `uv tool install git+${REPO_URL}`;
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`;
/** The site's public origin (06 §4 "Site URL"): metadataBase, the sitemap, robots and OG URLs derive from it. */
export const SITE_URL = "https://rook-weld-six.vercel.app";
/** Contact, support and privacy requests (06 §4 "Operator and contact"). */
export const CONTACT_EMAIL = "c40534394@gmail.com";
export const ISSUES_URL = `${REPO_URL}/issues`;

/** Who runs Rook (06 §4): one individual developer, not a company. */
export const operator = { name: "Aayush Kumar", location: "India" } as const;

/** A mailto: link to CONTACT_EMAIL with a prefilled subject (the contact page has no form backend). */
export function mailtoHref(subject: string): string {
  return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`;
}

export const site = {
  name: "Rook",
  cliCommand: "rook",
  oneLiner:
    "Rook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.",
  tagline: "Find the smallest sequence that breaks your software, before your users do.",
  builtOn: "Built on IBM Bob.",
  stage: "Early access, open source.",
  licence: "MIT licence",
} as const;

export const metadataCopy = {
  defaultTitle: "Rook · find the smallest sequence that breaks your software",
  titleTemplate: "%s · Rook",
  description: `${site.oneLiner} ${site.stage} ${site.builtOn}`,
  ogAlt: "Rook: find the smallest sequence that breaks your software",
} as const;

export interface NavLink {
  label: string;
  href: string;
  /** Opens another site (rendered as a plain <a>). */
  external?: boolean;
}

export const cta = {
  demo: { label: "Try Rook", href: "/app" },
  signIn: { label: "Sign in", href: "/login" },
  docs: { label: "Read the docs", href: "/docs/getting-started" },
  /** Replaces both for a visitor this browser remembers as signed in (06 §5). */
  workspace: { label: "Open workspace", href: "/app" },
} as const;

export const headerNav: NavLink[] = [
  { label: "Docs", href: "/docs" },
  { label: "Security", href: "/security" },
  { label: "Pricing", href: "/pricing" },
  { label: "Roadmap", href: "/roadmap" },
  { label: "GitHub", href: REPO_URL, external: true },
];

export const headerCopy = {
  skipLink: "Skip to content",
  homeLabel: "Rook home",
  menu: "Menu",
  navLabel: "Main",
  mobileNavLabel: "Main (menu)",
} as const;

export interface FooterColumn {
  heading: string;
  links: NavLink[];
}

export const footerColumns: FooterColumn[] = [
  {
    heading: "Product",
    links: [
      { label: "Overview", href: "/" },
      { label: cta.demo.label, href: cta.demo.href },
      { label: "Pricing", href: "/pricing" },
      { label: "Roadmap", href: "/roadmap" },
      { label: cta.signIn.label, href: cta.signIn.href },
    ],
  },
  {
    heading: "Docs",
    links: [
      // 06 §8. The labels and paths are the guides' own (content/docsGuides.ts; a test compares them).
      { label: "Getting started", href: cta.docs.href },
      { label: "Install", href: "/docs/install" },
      { label: "Rules", href: "/docs/rules" },
      { label: "GitHub Action", href: "/docs/github-action" },
      { label: "Data and IBM Bob", href: "/docs/data" },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Contact", href: "/contact" },
      { label: "GitHub", href: REPO_URL, external: true },
    ],
  },
  {
    heading: "Legal",
    links: [
      { label: "Privacy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
      { label: "Security", href: "/security" },
    ],
  },
];

export const footerCopy = {
  note: `Early access. ${site.builtOn}`,
  /** Followed by the licence link. */
  openSource: "Open source under the",
  licenceLink: { label: site.licence, href: LICENSE_URL, external: true } satisfies NavLink,
  navLabel: "Footer",
} as const;

export const notFoundCopy = {
  title: "Page not found",
  heading: "This page doesn't exist",
  body: "The link may be broken, or the page may have moved.",
  home: { label: "Back to the home page", href: "/" },
  docs: { label: "Read how Rook works", href: "/docs" },
} as const;
