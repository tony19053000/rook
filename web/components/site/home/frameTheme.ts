// Contrast fixes for the app components shown in the home walkthrough frames (06 §3: text at least 4.5:1).
// Scoped to `.wt-frame` only: the app's own token values and app pages are unchanged. The dark app tokens come
// from `.app-dark` in app/globals.css; these re-declare the ones whose pairs fall short there. `--accent` itself
// is never changed (it is also a button background): accent-coloured TEXT in a frame uses --frame-accent-text
// (globals.css `.wt-frame .text-accent`), and --accent-ink is dark so text on an accent background reads too.
// FRAME_ROW_BG is the background agent rows sit on (the dark --app), for the agents' derived text colours.
// The shrink chips' colours are fixed in globals.css (`.wt-frame [data-shrink]`). components/site/home/
// contrast.test.ts checks every text/background pair against these values.

export const FRAME_TOKEN_OVERRIDES = {
  /** Was #807e76 (3.25:1 on --surface). */
  "--faint": "#a09c93",
  /** Accent text (FixCard's root cause): --accent #e0563f is 3.51:1 on --surface. */
  "--frame-accent-text": "#ff7a5f",
  /** Was #ffffff (3.77:1 on --accent): a primary button's label, should one ever render in a frame. */
  "--accent-ink": "#141413",
} as const;

export const FRAME_ROW_BG = "#262624";
