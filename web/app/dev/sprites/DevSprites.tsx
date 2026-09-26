"use client";

import { useState } from "react";
import { SpriteGallery } from "@/components/SpriteGallery";
import { useReducedMotion } from "@/lib/motion";

export function DevSprites() {
  const media = useReducedMotion();
  const [forced, setForced] = useState<boolean | null>(null);
  const reduced = forced ?? media;
  return (
    <main className="mx-auto flex max-w-[760px] flex-col gap-4 p-6">
      <h1 className="font-serif text-2xl">Agent sprites and rows</h1>
      <label className="flex items-center gap-2 text-[13px] text-muted">
        <input type="checkbox" checked={reduced} onChange={(e) => setForced(e.target.checked)} />
        Reduced motion {forced === null ? "(from your system setting)" : "(forced)"}
      </label>
      <SpriteGallery reducedMotion={reduced} />
    </main>
  );
}
