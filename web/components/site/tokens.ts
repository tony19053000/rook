// The site's type scale, spacing and grid (06 §3), as Tailwind class strings over the `site-*` colour tokens
// defined in app/globals.css (scoped to `.site`).

export const type = {
  display: "text-[2.5rem] leading-[1.05] font-semibold tracking-[-0.035em] text-balance sm:text-6xl lg:text-7xl",
  h1: "text-4xl leading-tight font-semibold tracking-[-0.03em] text-balance sm:text-5xl",
  h2: "text-2xl leading-tight font-semibold tracking-[-0.02em] text-balance sm:text-3xl",
  h3: "text-lg leading-snug font-semibold tracking-[-0.01em]",
  lead: "text-lg leading-relaxed text-site-muted text-pretty sm:text-xl",
  body: "text-base leading-relaxed text-site-muted",
  small: "text-sm leading-relaxed text-site-muted",
  eyebrow: "font-mono text-xs font-medium uppercase tracking-[0.14em] text-site-faint",
} as const;

export const space = {
  /** Vertical rhythm of a page section. */
  section: "py-16 sm:py-24",
  /** The top of a page under the header. */
  pageTop: "pt-14 pb-16 sm:pt-20 sm:pb-24",
  stack: "flex flex-col gap-4",
} as const;

/** The page grid: one centred column with gutters that hold from 360 px up. */
export const container = "mx-auto w-full max-w-6xl px-5 sm:px-8";
export const narrow = "mx-auto w-full max-w-3xl px-5 sm:px-8";

/** The site background (--site-bg in globals.css), also the browser theme colour on site pages. */
export const SITE_THEME_COLOR = "#09090b";
