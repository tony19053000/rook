"use client";

// The home walkthrough (06 §6): the steps of `flowSteps` as a vertical tablist on the left, one frame at a time
// on the right in a fixed-size viewport (no scrollbar). The frames sit in a track moved by `transform`.
// - Autoplay: the next frame every FRAME_MS while playing, the tab is visible, the section is on screen and
//   the pointer is not over the frame. Clicking or focusing a step stops it (WAI-ARIA carousel pattern);
//   the Pause/Play control (WCAG 2.2.2) starts and stops it.
// - Reduced motion: no autoplay unless the user presses Play, and frames switch instantly (no slide).
// - Only the active frame is exposed: the others are `aria-hidden` and `inert`. The server render (and a page
//   without JS) shows frame 1 and every step's text.

import { useEffect, useId, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { WalkthroughFrameView } from "./WalkthroughFrame";
import { flowSteps, type FlowStep } from "@/content/flow";
import { WALKTHROUGH_LABEL, walkthroughCopy, walkthroughFrames, type WalkthroughFrame } from "@/content/walkthrough";
import { useReducedMotion } from "@/lib/motion";

export const FRAME_MS = 5500;

/** True while the page is visible (the Page Visibility API). */
function usePageVisible(): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return visible;
}

/** True while the element is on screen; always true where IntersectionObserver is missing. */
function useInView(ref: RefObject<HTMLElement | null>): boolean {
  const [inView, setInView] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry?.isIntersecting ?? true));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return inView;
}

interface WalkthroughProps {
  steps?: readonly FlowStep[];
  frames?: readonly WalkthroughFrame[];
}

export function Walkthrough({ steps = flowSteps, frames = walkthroughFrames }: WalkthroughProps) {
  const uid = useId();
  const root = useRef<HTMLDivElement>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const reduced = useReducedMotion();
  const pageVisible = usePageVisible();
  const inView = useInView(root);
  const [index, setIndex] = useState(0);
  // null until the user chooses: then autoplay follows the motion preference.
  const [choice, setChoice] = useState<"play" | "pause" | null>(null);
  const [hovered, setHovered] = useState(false);
  const playing = choice === null ? !reduced : choice === "play";
  const running = playing && pageVisible && inView && !hovered;
  const count = steps.length;

  // The time left on the current frame survives a pause (hover, hidden tab) and resets on a new frame.
  const remaining = useRef(FRAME_MS);
  useEffect(() => {
    remaining.current = FRAME_MS;
  }, [index]);
  useEffect(() => {
    if (!running || count < 2) return;
    const started = Date.now();
    const timer = setTimeout(() => setIndex((i) => (i + 1) % count), remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (Date.now() - started));
    };
  }, [running, index, count]);

  const select = (i: number, focus = false) => {
    const next = (i + count) % count;
    setChoice("pause");
    setIndex(next);
    if (focus) tabs.current[next]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const keys: Record<string, number> = { ArrowDown: index + 1, ArrowRight: index + 1, ArrowUp: index - 1, ArrowLeft: index - 1, Home: 0, End: count - 1 };
    const target = keys[event.key];
    if (target === undefined) return;
    event.preventDefault();
    select(target, true);
  };

  const tabId = (i: number) => `${uid}-tab-${i}`;
  const panelId = (i: number) => `${uid}-panel-${i}`;
  const summaryId = (i: number) => `${uid}-summary-${i}`;

  return (
    <div ref={root} className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10 2xl:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] 2xl:gap-14">
      <div className="flex min-w-0 flex-col gap-4">
        <div
          role="tablist"
          aria-label={walkthroughCopy.tablistLabel}
          aria-orientation="vertical"
          className="flex flex-col gap-1.5"
        >
          {steps.map((step, i) => {
            const active = i === index;
            return (
              <button
                key={step.id}
                ref={(el) => {
                  tabs.current[i] = el;
                }}
                id={tabId(i)}
                type="button"
                role="tab"
                aria-selected={active}
                aria-controls={panelId(i)}
                aria-describedby={summaryId(i)}
                tabIndex={active ? 0 : -1}
                onClick={() => select(i)}
                onKeyDown={onKeyDown}
                onFocus={() => setChoice("pause")}
                data-step={step.id}
                className={`relative flex w-full gap-4 overflow-hidden rounded-xl border px-4 py-3 text-left transition-colors ${
                  active ? "border-site-control bg-site-card" : "border-transparent hover:bg-site-raised"
                }`}
              >
                <span aria-hidden className={`font-mono text-xs leading-6 ${active ? "text-site-accent" : "text-site-faint"}`}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className={`font-semibold ${active ? "text-site-ink" : "text-site-muted"}`}>{step.title}</span>
                  <span id={summaryId(i)} className="text-sm leading-relaxed text-site-muted">
                    {step.summary}
                  </span>
                </span>
                {active && (
                  <span
                    aria-hidden
                    data-progress
                    className="wt-progress absolute inset-x-0 bottom-0 h-0.5 bg-site-accent"
                    style={{ animationDuration: `${FRAME_MS}ms`, animationPlayState: running ? "running" : "paused" }}
                  />
                )}
              </button>
            );
          })}
        </div>
        <div>
          <button
            type="button"
            onClick={() => setChoice(playing ? "pause" : "play")}
            aria-label={`${playing ? walkthroughCopy.pause : walkthroughCopy.play}${walkthroughCopy.controlSuffix}`}
            data-autoplay={running ? "running" : "stopped"}
            className="inline-flex h-9 w-24 items-center justify-center gap-2 rounded-full border border-site-control text-sm font-medium text-site-ink transition-colors hover:bg-site-raised"
          >
            <span aria-hidden className="font-mono text-xs">
              {playing ? "❚❚" : "▶"}
            </span>
            {playing ? walkthroughCopy.pause : walkthroughCopy.play}
          </button>
        </div>
      </div>

      <div
        className="relative h-[47rem] min-w-0 overflow-hidden sm:h-[40rem]"
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
      >
        <div
          data-track
          className={`flex h-full ${reduced ? "" : "transition-transform duration-700 ease-out"}`}
          style={{ transform: `translateX(-${index * 100}%)` }}
        >
          {steps.map((step, i) => {
            const active = i === index;
            return (
              <div
                key={step.id}
                id={panelId(i)}
                role="tabpanel"
                aria-labelledby={tabId(i)}
                aria-describedby={summaryId(i)}
                aria-hidden={active ? undefined : true}
                inert={!active}
                tabIndex={active ? 0 : -1}
                data-frame={step.id}
                className="flex h-full w-full flex-none flex-col gap-2.5 rounded-2xl"
              >
                <p className="flex-none font-mono text-xs text-site-faint">{WALKTHROUGH_LABEL}</p>
                <div className="min-h-0 flex-1">
                  <WalkthroughFrameView frame={frames.find((f) => f.stepId === step.id)} active={active} reduced={reduced} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
