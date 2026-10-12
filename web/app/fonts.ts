import localFont from "next/font/local";

// The site and app fonts, self-hosted from the @fontsource packages (OFL-1.1; each package ships its LICENSE).
// next/font/local reads the files from node_modules at build time, so a build needs no network (a font download
// from Google at build time once failed a CI build), and the CSP needs no third-party font origin (03 §8).
// Same families, weights and Latin subset as before.

export const plexSans = localFont({
  variable: "--font-plex-sans",
  display: "swap",
  src: [
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2", weight: "600", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-700-normal.woff2", weight: "700", style: "normal" },
  ],
  fallback: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
});

export const plexMono = localFont({
  variable: "--font-plex-mono",
  display: "swap",
  src: [
    { path: "../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../node_modules/@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
});

export const newsreader = localFont({
  variable: "--font-newsreader",
  display: "swap",
  src: [
    { path: "../node_modules/@fontsource/newsreader/files/newsreader-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../node_modules/@fontsource/newsreader/files/newsreader-latin-500-normal.woff2", weight: "500", style: "normal" },
  ],
  fallback: ["Georgia", "Times New Roman", "serif"],
});
