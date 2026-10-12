// The Roook logo (06 §3): a chess rook in a rounded square, and the wordmark. app/icon.svg is the same mark.

export const ROOK_PATH = "M9 7.5h3.25v2.75h2.25V7.5h3v2.75h2.25V7.5H23v5l-2.25 2.25v6L23 23.5v2H9v-2l2.25-2.75v-6L9 12.5z";

export function LogoMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 32 32" className={`flex-none ${className}`}>
      <rect x="0.5" y="0.5" width="31" height="31" rx="8" fill="#151412" stroke="#383531" />
      <path fill="#ff6a4d" d={ROOK_PATH} />
    </svg>
  );
}

/** The mark plus the name. The text is real text (readable and selectable), set in the serif like the app's wordmark. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="font-serif text-[1.4375rem] leading-none font-medium tracking-[-0.015em] text-site-ink">Roook</span>
    </span>
  );
}
