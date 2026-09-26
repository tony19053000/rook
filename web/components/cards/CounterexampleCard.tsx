"use client";

// CounterexampleCard (04 §3.4): a red border, the shrink chips `12 → 8 → 5 → 3` (the current one in red),
// the numbered minimal steps, the observed values against the rule, and the reproduced pill.

import { Mark } from "../AgentRow";
import { Card, CardHeader, Label, Pill } from "./ui";
import { compact, cxTitle, MAX_STEPS, observedPairs, observedText, short, stepText } from "@/lib/cardText";
import type { CounterexampleItem } from "@/lib/runStore";

export function ShrinkChips({ counts, done }: { counts: number[]; done: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 font-mono text-sm" data-shrink>
      {counts.map((count, i) => {
        const current = i === counts.length - 1;
        return (
          <span key={i} className="contents">
            {i > 0 && (
              <span className="text-faint" aria-hidden>
                →
              </span>
            )}
            <span
              data-current={current || undefined}
              className={`rounded-md border px-2.5 py-0.5 ${current ? "border-bad bg-bad text-white" : "border-line opacity-40"}`}
            >
              {count}
            </span>
          </span>
        );
      })}
      <span className="ml-1 text-[13px] text-muted">{done ? "steps · smallest found" : "steps, shrinking…"}</span>
    </div>
  );
}

export function CounterexampleCard({ item }: { item: CounterexampleItem }) {
  const saved = item.saved;
  const steps = saved !== null && Array.isArray(saved.steps) ? saved.steps : [];
  const pairs = observedPairs(item.observed);
  const ruleLabel = short(saved?.rule_text || item.ruleId, 80);
  return (
    <Card name="counterexample" alert>
      <CardHeader
        label={saved !== null ? cxTitle(saved.cx_id) : "Counterexample · shrinking"}
        labelTone="bad"
        pill={
          <Pill tone="bad">
            <Mark ok={false} /> {short(item.ruleId, 60)} · broken
          </Pill>
        }
      />
      <div className="font-semibold">{ruleLabel}</div>
      <ShrinkChips counts={item.stepCounts} done={saved !== null} />
      {steps.length > 0 && (
        <ol className="flex flex-col gap-1.5" aria-label="Minimal steps">
          {steps.slice(0, MAX_STEPS).map((step, i) => (
            <li key={i} className="flex gap-2.5 rounded-lg border border-line px-3 py-1.5 font-mono text-[13px]">
              <b className="w-5 flex-none font-medium text-faint">{i + 1}</b>
              <span className="min-w-0 break-words">{stepText(step)}</span>
            </li>
          ))}
          {steps.length > MAX_STEPS && <li className="text-xs text-faint">… {steps.length - MAX_STEPS} more steps</li>}
        </ol>
      )}
      <div className="flex flex-col gap-1">
        <Label>Observed</Label>
        {pairs !== null ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {pairs.map(([key, value]) => (
              <div key={key} className="flex min-w-0 flex-col items-center rounded-lg border border-line bg-app px-2 py-2 text-center">
                <span className="max-w-full truncate text-[11px] uppercase tracking-[.06em] text-faint">{key}</span>
                <span className="num max-w-full truncate text-lg font-semibold">{value}</span>
              </div>
            ))}
          </div>
        ) : (
          <span className="break-words font-mono text-[13px]">{observedText(item.observed)}</span>
        )}
      </div>
      {saved !== null && (
        <>
          <div className="text-[13px]">
            <span className="text-faint">Must hold </span>
            <code className="break-words font-mono">{compact(saved.expected)}</code>{" "}
            <span className="text-bad">
              <Mark ok={false} /> rule broken
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {saved.flaky ? (
              <Pill tone="warn">? Flaky · reproduced {short(saved.reproduced, 20)}</Pill>
            ) : (
              <Pill tone="good">✓ Reproduced {short(saved.reproduced, 20)} · real bug</Pill>
            )}
            {saved.test_path && (
              <span className="min-w-0 truncate font-mono text-xs text-muted">Regression test {short(saved.test_path, 90)}</span>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
