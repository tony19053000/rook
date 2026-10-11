"use client";

// One walkthrough frame (06 §6): the app's real run rows and cards, fed with the sample data in
// content/walkthrough.ts, inside an inert app window. No RunActionsContext provider is set, so the cards get
// the default read-only one (no answers can be sent), and nothing here calls the API.
// `.app-dark` keeps the app tokens dark whatever the OS theme (see app/globals.css); ./frameTheme.ts lifts the
// tokens and agent colours whose text would fall below 4.5:1.

import { AgentRow } from "@/components/AgentRow";
import { EngineRow } from "@/components/EngineRow";
import { CounterexampleCard } from "@/components/cards/CounterexampleCard";
import { FixCard } from "@/components/cards/FixCard";
import { RulesCard } from "@/components/cards/RulesCard";
import { SearchCard } from "@/components/cards/SearchCard";
import { VerifyCard } from "@/components/cards/VerifyCard";
import type { CSSProperties } from "react";
import { FRAME_ROW_BG, FRAME_TOKEN_OVERRIDES } from "./frameTheme";
import { verifyBefore, walkthroughCopy, type WalkthroughFrame, type WalkthroughItem } from "@/content/walkthrough";

/** A fixed clock, so a working agent row shows a still elapsed time. */
const STARTED_AT = 0;
const NOW = 2400;
const SPRITE_SEED = 7;

function FrameItem({ item, animate, reduced }: { item: WalkthroughItem; animate: boolean; reduced: boolean }) {
  switch (item.kind) {
    case "agent":
      // `frame={0}` stops the row's ticker (and the sprite's): only the visible frame animates, never under
      // reduced motion.
      return <AgentRow item={item} reducedMotion={reduced} frame={animate ? undefined : 0} seed={SPRITE_SEED} now={NOW} startedAt={STARTED_AT} readableOn={FRAME_ROW_BG} />;
    case "engine":
      return <EngineRow item={item} reducedMotion={reduced} />;
    case "rules":
      return <RulesCard item={item} />;
    case "search":
      return <SearchCard item={item} searching={false} />;
    case "counterexample":
      return <CounterexampleCard item={item} />;
    case "fix":
      return <FixCard item={item} />;
    case "verify":
      return <VerifyCard item={item} before={verifyBefore} />;
  }
}

export function WalkthroughFrameView({ frame, active, reduced }: { frame: WalkthroughFrame | undefined; active: boolean; reduced: boolean }) {
  return (
    <div inert style={FRAME_TOKEN_OVERRIDES as CSSProperties} className="wt-frame app-dark relative flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-app font-sans text-[14px] leading-normal text-ink">
      <div className="flex flex-none items-center gap-2 border-b border-line bg-side px-3.5 py-2.5">
        <span aria-hidden className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-line" />
          <span className="size-2.5 rounded-full bg-line" />
          <span className="size-2.5 rounded-full bg-line" />
        </span>
        <span className="ml-1.5 truncate font-mono text-xs text-muted">{walkthroughCopy.repo}</span>
        {frame && <span className="ml-auto rounded bg-sunk px-1.5 font-mono text-[11px] text-muted">{frame.phase}</span>}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 py-4">
        {frame?.items.map((item) => (
          <div key={item.key} className="flex min-w-0 flex-col" data-item={item.kind}>
            <FrameItem item={item} animate={active && !reduced} reduced={reduced} />
          </div>
        ))}
      </div>
      {/* Content that doesn't fit the fixed viewport fades out instead of being cut. */}
      <div aria-hidden className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-app to-transparent" />
    </div>
  );
}
