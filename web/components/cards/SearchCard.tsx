"use client";

// SearchCard (04 §3.4): Sequences, Speed and Broken x/N, updated live by search.progress; the pill goes
// Running -> Rule broken (or All holding once the search is over).

import { Card, CardHeader, Label, Pill } from "./ui";
import type { SearchItem } from "@/lib/runStore";
import { clean } from "@/lib/safeText";

function num(n: number): string {
  return Number.isFinite(n) ? Math.round(n).toLocaleString("en-US") : "0";
}

export function SearchCard({ item, searching }: { item: SearchItem; searching: boolean }) {
  const rules = Object.entries(item.rules);
  const broken = rules.filter(([, s]) => s === "broken").map(([id]) => clean(id));
  const pill =
    broken.length > 0 ? (
      <Pill tone="bad">✗ Rule broken</Pill>
    ) : searching ? (
      <Pill tone="idle">Running</Pill>
    ) : (
      <Pill tone="good">✓ All holding</Pill>
    );
  return (
    <Card name="search">
      <CardHeader label="Live search" pill={pill} />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        <div className="rounded-lg border border-line bg-app px-3 py-2.5">
          <Label>Sequences</Label>
          <div className="num text-[26px] font-semibold leading-tight">{num(item.sequences)}</div>
        </div>
        <div className="rounded-lg border border-line bg-app px-3 py-2.5">
          <Label>Speed</Label>
          <div className="num text-[26px] font-semibold leading-tight">
            {num(item.perSec)}
            <span className="text-xs font-normal text-faint">/s</span>
          </div>
        </div>
        <div className="rounded-lg border border-line bg-app px-3 py-2.5">
          <Label>Broken</Label>
          <div className={`num text-[26px] font-semibold leading-tight ${broken.length > 0 ? "text-bad" : "text-good"}`}>
            {broken.length}
            <span className="text-xs font-normal text-faint"> / {rules.length}</span>
          </div>
        </div>
      </div>
      {broken.length > 0 && <div className="truncate font-mono text-xs text-bad">Broken: {broken.join(", ")}</div>}
    </Card>
  );
}
