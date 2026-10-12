// The site's type scale, spacing and grid (06 §3), as Tailwind class strings over the `site-*` colour tokens
// defined in app/globals.css (scoped to `.site`). Headings are set in the serif (Newsreader, the face of the
// app's own headings and wordmark), UI and body text in IBM Plex Sans, labels and data in IBM Plex Mono.

export const type = {
  display:
    "font-serif text-[2.625rem] leading-[1.05] font-normal tracking-[-0.025em] text-balance sm:text-6xl sm:leading-[1.02] lg:text-7xl xl:text-[5.25rem] 2xl:text-[5.75rem]",
  h1: "font-serif text-[2.5rem] leading-[1.08] font-normal tracking-[-0.022em] text-balance sm:text-[3.5rem] sm:leading-[1.05]",
  /** A marketing section's heading. */
  h2: "font-serif text-[2rem] leading-[1.12] font-normal tracking-[-0.02em] text-balance sm:text-[2.75rem] sm:leading-[1.08]",
  /** A section heading inside long-form text (docs, security, legal). */
  h2Doc: "font-serif text-[1.625rem] leading-[1.2] font-medium tracking-[-0.015em] text-balance sm:text-[1.875rem]",
  h3: "text-[1.0625rem] leading-snug font-semibold tracking-[-0.011em]",
  lead: "text-lg leading-relaxed text-site-muted text-pretty sm:text-xl sm:leading-[1.6]",
  body: "text-base leading-[1.7] text-site-muted",
  small: "text-[0.9375rem] leading-relaxed text-site-muted",
  eyebrow: "site-eyebrow font-mono text-xs font-medium uppercase tracking-[0.16em] text-site-faint",
  /** A mono label without the accent mark (inside cards and tables). */
  label: "font-mono text-[0.6875rem] font-medium uppercase tracking-[0.14em] text-site-faint",
} as const;

export const space = {
  /** Vertical rhythm of a wide (marketing) section. */
  section: "py-16 sm:py-28",
  /** Vertical rhythm of a section of long-form text. */
  sectionDoc: "py-10 sm:py-12",
  /** The top of a page under the header. */
  pageTop: "pt-16 pb-20 sm:pt-24 sm:pb-28",
  stack: "flex flex-col gap-4",
} as const;

/** Side padding that grows with the screen; shared by the full-width header bar and the containers. */
export const gutter = "px-5 sm:px-8 lg:px-10 2xl:px-12";
/** The page grid: one centred column up to 1440 px, with gutters that hold from 360 px up. */
export const container = `mx-auto w-full max-w-[90rem] ${gutter}`;
/** Long-form text (legal, security, 404, sign-in): a readable measure. */
export const narrow = "mx-auto w-full max-w-3xl px-5 sm:px-8";
/** The readable measure for paragraphs and lists inside a wide container. */
export const measure = "max-w-3xl";

/** An inline text link. */
export const link =
  "text-site-ink underline decoration-site-control decoration-1 underline-offset-4 transition-colors hover:decoration-site-accent";

/** The site background (--site-bg in globals.css), also the browser theme colour on site pages. */
export const SITE_THEME_COLOR = "#0b0a09";
