// The /login page copy (06 §7).

import { cta } from "./site";

export const loginCopy = {
  title: "Sign in",
  description: "Sign in to Rook with Google to keep your runs and connect GitHub.",
  heading: "Sign in to Rook",
  lead: "Sign in with Google to keep your runs across devices and connect GitHub.",
  google: "Continue with Google",
  opening: "Opening Google…",
  completing: "Finishing sign-in…",
  retry: "Retry",
  /** Shown for `?error=` on the return from Google (the provider's text is not echoed). */
  cancelled: "Sign-in was cancelled or did not complete.",
  unavailable: "Google sign-in is not set up on this site. You can still try the demo without an account.",
  noscript: "Sign-in with Google needs JavaScript. Turn it on in your browser to sign in.",
  demo: { label: `${cta.demo.label} without signing in`, href: cta.demo.href },
  guestNote: "Guests can run the demo repository a few times a day. To run Rook on your own repos, install the CLI.",
  cliLink: { label: "Getting started", href: "/docs#getting-started" },
} as const;
