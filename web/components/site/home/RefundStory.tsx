import type { ReactNode } from "react";
import { Badge } from "../Badge";
import { InlineCode } from "../InlineCode";
import { type } from "../tokens";
import { runScreenshot } from "@/content/home";
import {
  refundChecks,
  refundCounterexample,
  refundDiagnosis,
  refundFix,
  refundOutcome,
  refundRule,
  storyCopy,
} from "@/content/story";
import { stepText } from "@/lib/cardText";

// The refund bug, end to end (ROOK-054): the rule, the minimal sequence, the replay, the diagnosis, the fix and
// the four checks of one recorded run (content/story.ts). A server component: all of it is in the first render.
// In a wide column (the home page): the rule across the top, the sequence beside the replay and the diagnosis,
// then fix and verify. In a narrower one (a docs guide) the stages stack: the layout follows its container.

/** A sunken box inside a stage: data, code, a figure. */
const WELL = "rounded-xl border border-site-line bg-site-raised";
const MONO_BOX = `${WELL} font-mono text-[0.8125rem] leading-relaxed`;

interface StageProps {
  stage: { label: string; title: string; body: string };
  children: ReactNode;
  className?: string;
}

function Stage({ stage, children, className = "" }: StageProps) {
  return (
    <article className={`site-panel flex min-w-0 flex-col gap-6 rounded-2xl p-5 sm:p-8 ${className}`}>
      <div>
        <p className={type.label}>{stage.label}</p>
        <h3 className="mt-3 text-xl leading-snug font-semibold tracking-[-0.015em] text-site-ink">{stage.title}</h3>
        <p className={`${type.small} mt-2 max-w-xl`}>{stage.body}</p>
      </div>
      {children}
    </article>
  );
}

type DiffKind = "file" | "added" | "removed" | "context";

function diffKind(line: string): DiffKind {
  if (line.startsWith("+++") || line.startsWith("---")) return "file";
  if (line.startsWith("+")) return "added";
  if (line.startsWith("-")) return "removed";
  return "context";
}

const DIFF_CLASS: Record<DiffKind, string> = {
  file: "border-transparent text-site-faint",
  added: "border-site-good bg-site-good/10 text-site-good",
  removed: "border-site-accent bg-site-accent/10 text-site-accent",
  context: "border-transparent text-site-muted",
};

/** One diff line, verbatim (marked as run data: the copy tests check it against the recording). */
function DiffLine({ line }: { line: string }) {
  const kind = diffKind(line);
  return (
    <span data-diff={kind} data-run-data className={`block border-l-2 py-px pr-4 pl-3.5 ${DIFF_CLASS[kind]}`}>
      {line}
    </span>
  );
}

function Tick() {
  return (
    <span aria-hidden className="mt-0.5 grid size-5 flex-none place-items-center rounded-full bg-site-good/15 text-site-good">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        <path d="m2 5.25 2 2 4-4.5" />
      </svg>
    </span>
  );
}

export function RefundStory() {
  const { stages } = storyCopy;
  const cx = refundCounterexample;
  const last = cx.steps.length - 1;
  return (
    <div className="@container flex flex-col gap-6">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-site-muted">
        <Badge tone="good">{runScreenshot.label}</Badge>
        <span>{storyCopy.source}</span>
      </p>
      <div className="grid gap-4 sm:gap-5 @4xl:grid-cols-2">
        <Stage stage={stages.rule} className="@4xl:col-span-2 @4xl:grid @4xl:grid-cols-2 @4xl:items-center @4xl:gap-x-12">
          <div className="flex flex-col gap-4">
            <p className="font-serif text-[1.625rem] leading-[1.2] tracking-[-0.015em] text-balance text-site-ink sm:text-[2rem]">{refundRule.text}</p>
            <p className={`${MONO_BOX} px-4 py-3 break-words text-site-ink`}>
              <span className="text-site-faint">{storyCopy.mustHold} </span>
              {refundRule.check}
            </p>
            <p className="font-mono text-xs break-words text-site-faint">{refundRule.id}</p>
          </div>
        </Stage>

        <Stage stage={stages.sequence} className="@4xl:row-span-2">
          {/* The sequence as a trace: a rail through the step numbers, the breaking step in the accent. */}
          <ol aria-label="The minimal sequence" data-story-steps className="flex flex-col">
            {cx.steps.map((step, i) => (
              <li key={i} className="relative flex items-start gap-4 pb-3 last:pb-0">
                {i < last && <span aria-hidden className="absolute top-9 bottom-0 left-[1.0625rem] w-px bg-site-strong" />}
                <span
                  aria-hidden
                  className={`relative grid size-9 flex-none place-items-center rounded-[0.625rem] border font-mono text-xs font-medium ${
                    i === last ? "border-site-accent/50 bg-site-accent/10 text-site-accent" : "border-site-strong bg-site-raised text-site-muted"
                  }`}
                >
                  {i + 1}
                </span>
                <span
                  data-run-data
                  className={`${MONO_BOX} min-w-0 flex-1 px-4 py-2 break-words text-site-ink ${i === last ? "border-site-accent/35" : ""}`}
                >
                  {stepText(step)}
                </span>
              </li>
            ))}
          </ol>
          {/* The observed values take the height left beside the taller column, so the card has no dead space. */}
          <div className="flex flex-1 flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className={type.label}>{storyCopy.observedLabel}</p>
              <p>
                <Badge tone="accent">
                  <span aria-hidden>✗</span>
                  {storyCopy.broken}
                </Badge>
              </p>
            </div>
            <dl data-story-observed className="grid flex-1 grid-cols-2 gap-3">
              <div className={`${WELL} flex min-h-32 flex-col justify-between gap-4 px-3.5 py-4 sm:px-5`}>
                <dt className="font-mono text-[0.6875rem] text-site-faint sm:text-xs">paid</dt>
                <dd className="font-mono text-5xl leading-none font-medium text-site-ink tabular-nums sm:text-6xl">{cx.observed.paid}</dd>
              </div>
              <div className="flex min-h-32 flex-col justify-between gap-4 rounded-xl border border-site-accent/40 bg-site-accent/10 px-3.5 py-4 sm:px-5">
                <dt className="font-mono text-[0.6875rem] text-site-accent sm:text-xs">refunded_total</dt>
                <dd className="font-mono text-5xl leading-none font-medium text-site-accent tabular-nums sm:text-6xl">{cx.observed.refunded_total}</dd>
              </div>
            </dl>
          </div>
        </Stage>

        <Stage stage={stages.replay}>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-site-good/35 bg-site-good/10 px-4 py-4 sm:px-5">
              <dt className="font-mono text-xs text-site-good">{storyCopy.replayedLabel}</dt>
              <dd data-story-replayed className="mt-2 font-mono text-4xl leading-none font-medium text-site-good tabular-nums sm:text-5xl">
                {cx.reproduced}
              </dd>
            </div>
            <div className={`${WELL} min-w-0 px-4 py-4 sm:px-5`}>
              <dt className="font-mono text-xs text-site-faint">{storyCopy.regressionLabel}</dt>
              <dd className="mt-2 font-mono text-sm break-words text-site-ink">{cx.testPath}</dd>
            </div>
          </dl>
          <p className={`${MONO_BOX} px-4 py-3 break-words text-site-muted`}>
            <span className="text-site-faint">{storyCopy.testBeforeFixLabel}: </span>
            {cx.testBeforeFix}
          </p>
        </Stage>

        <Stage stage={stages.diagnosis}>
          <p className="flex">
            <span data-story-diagnosis className="rounded-lg border border-site-accent/35 bg-site-accent/10 px-3 py-1.5 font-mono text-base font-medium text-site-accent">
              {refundDiagnosis.file}:{refundDiagnosis.line}
            </span>
          </p>
          <blockquote className="border-l-2 border-site-accent/60 pl-5 text-[1.0625rem] leading-relaxed text-site-ink">
            <InlineCode text={refundDiagnosis.sentence} />
          </blockquote>
        </Stage>

        <Stage stage={stages.fix}>
          <figure className={`${WELL} flex-1 overflow-hidden`}>
            <figcaption className="border-b border-site-line bg-white/[0.02] px-4 py-2.5 font-mono text-xs text-site-faint">{storyCopy.diffLabel}</figcaption>
            <pre data-story-diff className="py-3 font-mono text-[0.78125rem] leading-[1.7] whitespace-pre-wrap break-words">
              <code>
                {refundFix.diff
                  .split("\n")
                  .filter((line) => line !== "")
                  .map((line, i) => (
                    <DiffLine key={i} line={line} />
                  ))}
              </code>
            </pre>
          </figure>
        </Stage>

        <Stage stage={stages.verify}>
          <ul data-story-checks className={`${WELL} flex flex-col divide-y divide-site-line`}>
            {refundChecks.map((check) => (
              <li key={check.id} className="flex gap-3.5 px-4 py-3.5 sm:px-5">
                <Tick />
                <div className="min-w-0">
                  <p className="text-[0.9375rem] font-semibold text-site-ink">
                    {check.label} <span className="sr-only">passed</span>
                  </p>
                  <p className="text-sm leading-relaxed text-site-muted">{check.meaning}</p>
                  <p className="mt-1.5 font-mono text-xs break-words text-site-faint">{check.detail}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <Badge tone="good">
              <span aria-hidden>✓</span>
              {refundOutcome.summary}
            </Badge>
            <span className="text-site-muted">
              {storyCopy.branchLabel} <code className="font-mono text-site-ink">{refundOutcome.branch}</code>
            </span>
          </p>
        </Stage>
      </div>
    </div>
  );
}
