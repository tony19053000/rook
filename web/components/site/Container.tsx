import type { ReactNode } from "react";
import { container, narrow } from "./tokens";

export function Container({ children, width = "wide", className = "" }: { children: ReactNode; width?: "wide" | "narrow"; className?: string }) {
  return <div className={`${width === "wide" ? container : narrow} ${className}`}>{children}</div>;
}

/** A responsive grid of 1 → 2 → 3 columns. */
export function Grid({ children, columns = 3, className = "" }: { children: ReactNode; columns?: 2 | 3; className?: string }) {
  const cols = columns === 2 ? "md:grid-cols-2" : "md:grid-cols-2 lg:grid-cols-3";
  return <div className={`grid grid-cols-1 gap-4 sm:gap-5 ${cols} ${className}`}>{children}</div>;
}
