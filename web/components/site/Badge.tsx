import type { ReactNode } from "react";

const TONES = {
  neutral: "border-site-line bg-site-raised text-site-muted",
  accent: "border-site-accent/40 bg-site-accent/10 text-site-accent",
  good: "border-site-good/40 bg-site-good/10 text-site-good",
  warn: "border-site-warn/40 bg-site-warn-soft text-site-warn",
} as const;

export type BadgeTone = keyof typeof TONES;

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}
