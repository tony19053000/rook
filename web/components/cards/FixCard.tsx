"use client";

// FixCard (04 §3.4): the root cause `file : line` and explanation (diagnosis.ready), the diff with red `-`
// and green `+` lines (fix.ready), the reviewer pills, and the fix question's buttons.

import { Card, CardHeader, Label, Pill } from "./ui";
import { ConfirmAnswer, questionText } from "./QuestionCard";
import { diffLines, short, type DiffLineKind } from "@/lib/cardText";
import type { FixItem, QuestionItem } from "@/lib/runStore";
import { clean, cleanMultiline } from "@/lib/safeText";

const DIFF_CLASS: Record<DiffLineKind, string> = {
  add: "text-good",
  remove: "text-bad",
  meta: "text-faint",
  hunk: "text-link",
  context: "text-muted",
};

export function Diff({ diff }: { diff: string }) {
  const { lines, more } = diffLines(diff);
  if (lines.length === 0) return null;
  return (
    <pre className="overflow-x-auto rounded-lg border border-line bg-sunk px-3 py-2.5 font-mono text-[12.5px] leading-relaxed" aria-label="Diff">
      {lines.map((line, i) => (
        <span key={i} data-diff={line.kind} className={`block ${DIFF_CLASS[line.kind]}`}>
          {line.text === "" ? " " : line.text}
        </span>
      ))}
      {more > 0 && <span className="block text-faint">… {more} more lines</span>}
    </pre>
  );
}

function Reviewed({ reviewed, who }: { reviewed: boolean; who: string }) {
  return reviewed ? <Pill tone="good">✓ Reviewed by the {who}</Pill> : <Pill tone="warn">? Not reviewed</Pill>;
}

export function FixCard({ item, question = null }: { item: FixItem; question?: QuestionItem | null }) {
  const d = item.diagnosis;
  const f = item.fix;
  const where = d === null ? null : d.line !== null && Number.isFinite(d.line) ? `${clean(d.file)} : ${d.line}` : clean(d.file);
  return (
    <Card name="fix">
      <CardHeader
        label={`Root cause and fix · ${short(item.cxId, 40)}`}
        pill={d !== null ? <Reviewed reviewed={d.reviewed === true} who="Diagnosis Reviewer" /> : <Pill tone="idle">Diagnosing…</Pill>}
      />
      {d !== null && (
        <>
          <div className="font-mono text-[13px]">
            <span className="text-faint">Root cause </span>
            <span className="font-semibold text-accent">{where}</span>
          </div>
          <div className="whitespace-pre-wrap break-words text-muted">{cleanMultiline(d.explanation).trim()}</div>
        </>
      )}
      {f !== null && (
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label>Fix · {short(f.files.map((x) => clean(String(x))).join(", "), 120)}</Label>
            <Reviewed reviewed={f.reviewed === true} who="Fix Reviewer" />
          </div>
          <Diff diff={f.diff} />
        </div>
      )}
      {question !== null && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold">
            <span className="text-warn" aria-hidden>
              ?{" "}
            </span>
            {questionText(question)}
          </span>
          <ConfirmAnswer question={question} />
        </div>
      )}
    </Card>
  );
}
