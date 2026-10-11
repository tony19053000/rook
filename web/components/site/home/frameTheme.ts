// Contrast fixes for the app components shown in the home walkthrough frames (06 §3: text at least 4.5:1).
// Scoped to `.wt-frame` only: the app's own token values and app pages are unchanged. The dark app tokens come
// from `.app-dark` in app/globals.css; these re-declare the two whose text falls short there, and
// FRAME_ROW_BG is the background agent rows sit on (the dark --app), for the agents' derived text colours.
// The shrink chips' colours are fixed in globals.css (`.wt-frame [data-shrink]`). components/site/home/
// contrast.test.ts checks every text/background pair against these values.

export const FRAME_TOKEN_OVERRIDES = {
  /** Was #807e76 (3.25:1 on --surface). */
  "--faint": "#a09c93",
  /** Was #e0563f (3.51:1 on --surface): FixCard's root-cause text. */
  "--accent": "#ff7a5f",
} as const;

export const FRAME_ROW_BG = "#262624";
