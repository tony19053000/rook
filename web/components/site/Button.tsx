import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-[0.625rem] font-medium whitespace-nowrap transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100";

// Primary is the page's ink on its background (17:1); the accent stays for marks and the "rule broken" state.
const VARIANTS = {
  primary:
    "bg-site-ink text-site-bg shadow-[inset_0_-2px_0_rgb(0_0_0/0.12),0_10px_30px_-12px_rgb(245_243_236/0.45)] hover:bg-white",
  secondary: "border border-site-control bg-white/[0.03] text-site-ink hover:border-site-ink hover:bg-white/[0.07]",
  ghost: "text-site-muted hover:bg-white/[0.05] hover:text-site-ink",
} as const;

const SIZES = {
  sm: "h-9 px-3.5 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[0.9375rem]",
} as const;

export type ButtonVariant = keyof typeof VARIANTS;
export type ButtonSize = keyof typeof SIZES;

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md", className = ""): string {
  return `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`;
}

interface LinkProps {
  href: string;
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  /** Another site: a plain <a> instead of next/link. */
  external?: boolean;
}

/** A link styled as a button (navigation is always a link, so it works without JS). */
export function ButtonLink({ href, children, variant, size, className, external = false }: LinkProps) {
  const cls = buttonClass(variant, size, className);
  if (external) {
    return (
      <a href={href} className={cls} rel="noopener noreferrer">
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize };

/** A real <button> for actions. */
export function Button({ variant, size, className, type = "button", ...rest }: ButtonProps) {
  return <button type={type} className={buttonClass(variant, size, className)} {...rest} />;
}
