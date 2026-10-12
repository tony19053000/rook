import type { ReactNode } from "react";

/** A raised surface (`.site-panel` in app/globals.css). */
export function Card({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "article" | "li" }) {
  return <Tag className={`site-panel rounded-2xl p-6 ${className}`}>{children}</Tag>;
}
