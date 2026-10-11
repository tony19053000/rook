// WCAG 2 contrast helpers: the contrast ratio of two #rrggbb colours, and a readable text colour derived from a
// brand colour (mixed toward white until it reaches the ratio). Used by the home walkthrough frames.

export const MIN_TEXT_CONTRAST = 4.5;

function channels(hex: string): [number, number, number] {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const n = parseInt(m[1]!, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

function mix(hex: string, toward: string, t: number): string {
  const a = channels(hex);
  const b = channels(toward);
  return `#${a.map((c, i) => Math.round(c + (b[i]! - c) * t).toString(16).padStart(2, "0")).join("")}`;
}

/** `color` itself if it reads on `background`, else the least mix toward white that does. */
export function readableColor(color: string, background: string, min = MIN_TEXT_CONTRAST): string {
  for (let step = 0; step <= 20; step += 1) {
    const candidate = mix(color, "#ffffff", step / 20);
    if (contrastRatio(candidate, background) >= min) return candidate;
  }
  return "#ffffff";
}
