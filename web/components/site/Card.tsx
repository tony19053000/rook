import type { ReactNode } from "react";

export function Card({ children, className = "", as: Tag = "div" }: { children: ReactNode; className?: string; as?: "div" | "article" | "li" }) {
  return <Tag className={`rounded-2xl border border-site-line bg-site-card p-6 ${className}`}>{children}</Tag>;
}
