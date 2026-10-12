// Decorative line icons for the home page's "What you get" cells, in the order of `features` (content/home.ts).
// One 24 px grid, 1.5 px strokes. A cell past the end of the list gets the first icon.

const PATHS: readonly string[][] = [
  // Proof, not a guess: a shield with a tick.
  ["M12 3.25 5 6v5.5c0 4.2 2.8 7.6 7 9.25 4.2-1.65 7-5.05 7-9.25V6l-7-2.75Z", "m9 11.75 2.25 2.25L15.25 10"],
  // The smallest reproduction: arrows closing in on a point.
  ["M4 4l5 5M9 5.25V9H5.25", "M20 20l-5-5M15 18.75V15h3.75", "M20 4l-5 5M18.75 9H15V5.25", "M4 20l5-5M5.25 15H9v3.75"],
  // A failing test you can keep: a file with a tick.
  ["M13.5 3.25H7.25a1.5 1.5 0 0 0-1.5 1.5v14.5a1.5 1.5 0 0 0 1.5 1.5h9.5a1.5 1.5 0 0 0 1.5-1.5V8l-4.75-4.75Z", "M13.5 3.5V8h4.5", "m9.25 14 2 2 3.5-3.75"],
  // A fix that is checked: four ticked rows.
  ["m4 6.5 1.5 1.5L8 5.25", "m4 13 1.5 1.5L8 11.75", "m4 19.25 1.5 1.5L8 18", "M11.5 6.75H20M11.5 13.25H20M11.5 19.5H20"],
  // Rules you approve: a rule sheet and a pen.
  ["M6 3.75h9.5a1.5 1.5 0 0 1 1.5 1.5V10", "M6 3.75a1.5 1.5 0 0 0-1.5 1.5v13.5a1.5 1.5 0 0 0 1.5 1.5h5", "M8 8.5h5.5M8 12h3", "m14.25 20.25.5-2.75 4.6-4.6a1.24 1.24 0 0 1 1.75 1.75l-4.6 4.6-2.25 1Z"],
  // The fix lands on its own branch: a branch.
  ["M7 4.75a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5Z", "M7 15.75a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5Z", "M17 6.75a1.75 1.75 0 1 0 0 3.5 1.75 1.75 0 0 0 0-3.5Z", "M7 8.25v7.5", "M17 10.25c0 3-4 2.75-7.5 3.75"],
  // In your terminal and your pull requests: a terminal.
  ["M4.75 4.75h14.5a1.5 1.5 0 0 1 1.5 1.5v11.5a1.5 1.5 0 0 1-1.5 1.5H4.75a1.5 1.5 0 0 1-1.5-1.5V6.25a1.5 1.5 0 0 1 1.5-1.5Z", "m7.25 9.5 2.75 2.5-2.75 2.5", "M12.5 14.75h4"],
  // Any backend with an HTTP API: braces.
  ["M9 4.25c-1.75 0-2.5.9-2.5 2.5v2.5c0 1.25-.75 2.25-2 2.75 1.25.5 2 1.5 2 2.75v2.5c0 1.6.75 2.5 2.5 2.5", "M15 4.25c1.75 0 2.5.9 2.5 2.5v2.5c0 1.25.75 2.25 2 2.75-1.25.5-2 1.5-2 2.75v2.5c0 1.6-.75 2.5-2.5 2.5", "M10.75 12h.01M13.25 12h.01"],
];

export function FeatureIcon({ index }: { index: number }) {
  const paths = PATHS[index] ?? PATHS[0]!;
  return (
    <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
