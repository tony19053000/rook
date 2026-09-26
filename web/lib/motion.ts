"use client";

// Motion hooks: the prefers-reduced-motion media query and a frame ticker for the sprite animation.

import { useEffect, useState, useSyncExternalStore } from "react";
import { FPS } from "./sprite";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

function snapshot(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(QUERY).matches;
}

/** True when the user asked for reduced motion. The server render assumes reduced (a static first paint). */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => true);
}

/** A counter that advances at `fps` while `enabled`; it stops (and the interval is cleared) otherwise. */
export function useFrame(enabled: boolean, fps: number = FPS): number {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => setFrame((f) => f + 1), 1000 / fps);
    return () => clearInterval(id);
  }, [enabled, fps]);
  return frame;
}
