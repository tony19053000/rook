// Site-wide copy and links (06 §4). Every repeated fact (name, repo URL, install command) is defined once here.

export const REPO_URL = "https://github.com/tony19053000/rook";
export const INSTALL_COMMAND = `uv tool install git+${REPO_URL}`;
export const LICENSE_URL = `${REPO_URL}/blob/main/LICENSE`;
export const REPO_DOCS_URL = `${REPO_URL}/tree/main/docs`;
/** Shown as-is until a real address is chosen (06 §5.5). */
export const CONTACT_PLACEHOLDER = "[contact email]";

export const site = {
  name: "Rook",
  cliCommand: "rook",
  oneLiner:
    "Rook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.",
  tagline: "Find the smallest sequence that breaks your software, before your users do.",
  builtOn: "Built on IBM Bob.",
  licence: "MIT licence",
} as const;

export const metadataCopy = {
  defaultTitle: "Rook · find the smallest sequence that breaks your software",
  titleTemplate: "%s · Rook",
  description: `${site.oneLiner} ${site.builtOn}`,
  ogAlt: "Rook: find the smallest sequence that breaks your software",
} as const;

export interface NavLink {
  label: string;
  href: string;
  /** Opens another site (rendered as a plain <a>). */
  external?: boolean;
}

export const cta = {
  demo: { label: "Try the demo", href: "/app" },
  signIn: { label: "Sign in", href: "/login" },
} as const;

export const headerNav: NavLink[] = [
  { label: "How it works", href: "/docs" },
  { label: "Security", href: "/security" },
  { label: "Pricing", href: "/pricing" },
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
  /** A plain line after the links. */
  note?: string;
}

export const footerColumns: FooterColumn[] = [
  {
    heading: "Product",
    links: [
      { label: "Overview", href: "/" },
      { label: cta.demo.label, href: cta.demo.href },
      { label: "Pricing", href: "/pricing" },
      { label: cta.signIn.label, href: cta.signIn.href },
    ],
  },
  {
    heading: "Docs",
    links: [
      { label: "How it works", href: "/docs#how-it-works" },
      { label: "Getting started", href: "/docs#getting-started" },
      { label: "GitHub Action", href: "/docs#github-action" },
      { label: "Docs on GitHub", href: REPO_DOCS_URL, external: true },
    ],
  },
  {
    heading: "Company",
    links: [
      { label: "GitHub repository", href: REPO_URL, external: true },
      { label: site.licence, href: LICENSE_URL, external: true },
    ],
    note: `Contact: ${CONTACT_PLACEHOLDER}`,
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
  note: `Open source under the ${site.licence}. A hackathon-stage project built for the IBM Bob 2.0 Hackathon.`,
  navLabel: "Footer",
} as const;

export const notFoundCopy = {
  title: "Page not found",
  heading: "This page doesn't exist",
  body: "The link may be broken, or the page may have moved.",
  home: { label: "Back to the home page", href: "/" },
  docs: { label: "Read how Rook works", href: "/docs" },
} as const;
