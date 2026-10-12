import type { ReactNode } from "react";
import { Badge } from "../Badge";
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
// Wide screens: the rule across the top, the sequence beside the replay and the diagnosis, then fix and verify.

const MONO_BOX = "rounded-xl border border-site-line bg-site-raised font-mono text-sm";

interface StageProps {
  stage: { label: string; title: string; body: string };
  children: ReactNode;
  className?: string;
}

function Stage({ stage, children, className = "" }: StageProps) {
  return (
    <article className={`flex min-w-0 flex-col gap-4 rounded-2xl border border-site-line bg-site-card p-5 sm:p-7 ${className}`}>
      <div>
        <p className={type.eyebrow}>{stage.label}</p>
        <h3 className={`${type.h3} mt-2 text-site-ink`}>{stage.title}</h3>
        <p className={`${type.small} mt-1.5`}>{stage.body}</p>
      </div>
      {children}
    </article>
  );
}

/** Text with `code` spans, as the Detective writes it. */
function WithCode({ text }: { text: string }) {
  return (
    <>
      {text.split("`").map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="rounded bg-site-raised px-1 py-0.5 font-mono text-[0.9em] text-site-ink">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
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
  file: "text-site-faint",
  added: "bg-site-good/10 text-site-good",
  removed: "bg-site-accent/10 text-site-accent",
  context: "text-site-muted",
};

/** One diff line, verbatim (marked as run data: the copy tests check it against the recording). */
function DiffLine({ line }: { line: string }) {
  const kind = diffKind(line);
  return (
    <span data-diff={kind} data-run-data className={`block px-4 ${DIFF_CLASS[kind]}`}>
      {line}
    </span>
  );
}

export function RefundStory() {
  const { stages } = storyCopy;
  const cx = refundCounterexample;
  return (
    <div className="flex flex-col gap-6">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-site-muted">
        <Badge tone="good">{runScreenshot.label}</Badge>
        <span>{storyCopy.source}</span>
      </p>
      <div className="grid gap-4 sm:gap-5 lg:grid-cols-2">
        <Stage stage={stages.rule} className="lg:col-span-2 lg:grid lg:grid-cols-2 lg:items-center lg:gap-x-10">
          <div className="flex flex-col gap-3">
            <p className="text-lg font-semibold text-balance text-site-ink sm:text-xl">{refundRule.text}</p>
            <p className={`${MONO_BOX} px-4 py-3 break-words text-site-ink`}>
              <span className="text-site-faint">{storyCopy.mustHold} </span>
              {refundRule.check}
            </p>
            <p className="font-mono text-xs break-words text-site-faint">{refundRule.id}</p>
          </div>
        </Stage>

        <Stage stage={stages.sequence} className="lg:row-span-2">
          <ol aria-label="The minimal sequence" data-story-steps className="flex flex-col gap-2">
            {cx.steps.map((step, i) => (
              <li key={i} className={`${MONO_BOX} flex gap-3 px-4 py-2.5 break-words text-site-ink`}>
                <span aria-hidden className="text-site-faint">
                  {i + 1}
                </span>
                <span data-run-data className="min-w-0">
                  {stepText(step)}
                </span>
              </li>
            ))}
          </ol>
          <div>
            <p className={type.eyebrow}>{storyCopy.observedLabel}</p>
            <dl data-story-observed className="mt-2 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-site-line bg-site-raised px-4 py-3">
                <dt className="font-mono text-xs text-site-faint">paid</dt>
                <dd className="mt-1 font-mono text-2xl font-semibold text-site-ink tabular-nums">{cx.observed.paid}</dd>
              </div>
              <div className="rounded-xl border border-site-accent/40 bg-site-accent/10 px-4 py-3">
                <dt className="font-mono text-xs text-site-accent">refunded_total</dt>
                <dd className="mt-1 font-mono text-2xl font-semibold text-site-accent tabular-nums">{cx.observed.refunded_total}</dd>
              </div>
            </dl>
          </div>
          <p>
            <Badge tone="accent">
              <span aria-hidden>✗</span>
              {storyCopy.broken}
            </Badge>
          </p>
        </Stage>

        <Stage stage={stages.replay}>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-site-good/40 bg-site-good/10 px-4 py-3">
              <dt className="font-mono text-xs text-site-good">{storyCopy.replayedLabel}</dt>
              <dd data-story-replayed className="mt-1 font-mono text-2xl font-semibold text-site-good tabular-nums">
                {cx.reproduced}
              </dd>
            </div>
            <div className="min-w-0 rounded-xl border border-site-line bg-site-raised px-4 py-3">
              <dt className="font-mono text-xs text-site-faint">{storyCopy.regressionLabel}</dt>
              <dd className="mt-1 font-mono text-sm break-words text-site-ink">{cx.testPath}</dd>
            </div>
          </dl>
          <p className={`${MONO_BOX} px-4 py-3 break-words text-site-muted`}>
            <span className="text-site-faint">{storyCopy.testBeforeFixLabel}: </span>
            {cx.testBeforeFix}
          </p>
        </Stage>

        <Stage stage={stages.diagnosis}>
          <p data-story-diagnosis className="font-mono text-lg font-semibold text-site-accent">
            {refundDiagnosis.file}:{refundDiagnosis.line}
          </p>
          <blockquote className="border-l-2 border-site-accent/60 pl-4 text-base leading-relaxed text-site-ink">
            <WithCode text={refundDiagnosis.sentence} />
          </blockquote>
        </Stage>

        <Stage stage={stages.fix}>
          <figure className="overflow-hidden rounded-xl border border-site-line bg-site-raised">
            <figcaption className="border-b border-site-line px-4 py-2 font-mono text-xs text-site-faint">{storyCopy.diffLabel}</figcaption>
            <pre data-story-diff className="py-2 font-mono text-[0.8125rem] leading-relaxed whitespace-pre-wrap break-words">
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
          <ul data-story-checks className="flex flex-col divide-y divide-site-line rounded-xl border border-site-line bg-site-raised">
            {refundChecks.map((check) => (
              <li key={check.id} className="flex gap-3 px-4 py-3">
                <span aria-hidden className="font-mono text-site-good">
                  ✓
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-site-ink">
                    {check.label} <span className="sr-only">passed</span>
                  </p>
                  <p className="text-sm text-site-muted">{check.meaning}</p>
                  <p className="mt-1 font-mono text-xs break-words text-site-faint">{check.detail}</p>
                </div>
              </li>
            ))}
          </ul>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
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
