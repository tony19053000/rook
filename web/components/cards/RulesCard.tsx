"use client";

// RulesCard (04 §3.4): the proposed rules with their sources, the engine/critic verdicts (rejected rules
// struck through with the reason), and, while the approve_rules question is open, a checkbox per rule and
// "Approve N rules". A rule flagged already_broken reads "possibly already broken", starts unticked and is
// approved only by an explicit tick. The answer is always the explicit id list, never "all".

import { useState } from "react";
import { Mark } from "../AgentRow";
import { Button, Card, CardHeader, ClosedAnswer, Countdown, Note, Pill, useAnswer, useCountdown, useRunActions } from "./ui";
import {
  choosable,
  describeRulesAnswer,
  guestRulesAnswer,
  initialSelection,
  ruleRows,
  rulesApproval,
  type RuleRow,
} from "@/lib/questions";
import type { QuestionItem, RulesItem } from "@/lib/runStore";

function RowPill({ row }: { row: RuleRow }) {
  if (row.status === "rejected") return <Pill tone="bad">Rejected</Pill>;
  if (row.approved === true) return <Pill tone="good">Approved</Pill>;
  if (row.approved === false) return <Pill tone="idle">Not approved</Pill>;
  if (row.alreadyBroken) return <Pill tone="warn">Possibly already broken</Pill>;
  if (row.featured) return <Pill tone="idle">Demo rule</Pill>;
  return null;
}

function RuleLine({
  row,
  index,
  asking,
  checked,
  disabled,
  onToggle,
  inputId,
}: {
  row: RuleRow;
  index: number;
  asking: boolean;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
  inputId: string;
}) {
  const rejected = row.status === "rejected";
  const box = asking && choosable(row);
  return (
    <div className="flex items-start gap-2.5 border-t border-line px-3 py-2 text-[13.5px] first:border-t-0" data-rule={row.id} data-status={row.status}>
      {box ? (
        <input
          id={inputId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={onToggle}
          className="mt-1 size-4 flex-none accent-[var(--accent)]"
        />
      ) : (
        <span className="mt-px w-4 flex-none text-center" aria-hidden={row.approved === null && !rejected}>
          {rejected ? <Mark ok={false} /> : row.approved === true ? <Mark ok /> : <span className="text-faint">·</span>}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <label htmlFor={box ? inputId : undefined} className={`block ${rejected ? "text-faint line-through" : ""}`}>
          <span className="num mr-1.5 text-faint">{index + 1}</span>
          {row.text}
        </label>
        {row.sources.length > 0 && <span className="block truncate font-mono text-xs text-faint">{row.sources.join(" · ")}</span>}
        {row.alreadyBroken && !rejected && (
          <span className="block text-xs text-warn" data-already-broken>
            <span aria-hidden>? </span>Possibly already broken · needs your explicit OK
          </span>
        )}
        {row.reason && (rejected || row.alreadyBroken) && <span className="block break-words text-xs text-muted">{row.reason}</span>}
      </span>
      <RowPill row={row} />
    </div>
  );
}

function headerPill(rows: RuleRow[], asking: boolean, decided: boolean) {
  if (asking) return <Pill tone="warn">Needs your OK</Pill>;
  if (decided) {
    const n = rows.filter((r) => r.approved === true).length;
    return n > 0 ? <Pill tone="good">Approved {n}</Pill> : <Pill tone="bad">None approved</Pill>;
  }
  return <Pill tone="idle">Proposed</Pill>;
}

function Approval({ question, rows }: { question: QuestionItem; rows: RuleRow[] }) {
  const { guest, autoSeconds } = useRunActions();
  const { state, submit, locked } = useAnswer(question);
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const selected = picked ?? new Set(initialSelection(rows, guest));
  const ids = rulesApproval(rows, selected);
  const countdown = useCountdown(
    guest && picked === null && guestRulesAnswer(rows) !== null && !locked && state.status !== "error",
    autoSeconds,
    () => {
      const auto = guestRulesAnswer(rows);
      if (auto !== null) void submit(auto, describeRulesAnswer(auto));
    },
  );

  const open = !(question.answered || state.status === "sent" || state.status === "closed");
  const toggle = (id: string) => {
    countdown.stop();
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setPicked(next);
  };

  return (
    <>
      <div className="rounded-lg border border-line">
        {rows.map((row, i) => (
          <RuleLine
            key={row.id}
            row={row}
            index={i}
            asking={open}
            checked={selected.has(row.id)}
            disabled={locked}
            onToggle={() => toggle(row.id)}
            inputId={`rule-${question.questionId}-${i}`}
          />
        ))}
      </div>
      {open ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            primary
            disabled={locked || ids.length === 0}
            onClick={() => {
              countdown.stop();
              void submit(ids, describeRulesAnswer(ids));
            }}
          >
            {ids.length === 1 ? "Approve 1 rule" : `Approve ${ids.length} rules`}
          </Button>
          <Button
            disabled={locked}
            onClick={() => {
              countdown.stop();
              void submit("none", describeRulesAnswer("none"));
            }}
          >
            Reject all
          </Button>
          <Countdown left={countdown.left} onStop={countdown.stop} what="approving the ticked rules" />
          {state.status === "error" && <Note tone="bad">{state.message}</Note>}
        </div>
      ) : (
        <ClosedAnswer question={question} state={state} describe={describeRulesAnswer} />
      )}
    </>
  );
}

export function RulesCard({ item, question = null }: { item: RulesItem; question?: QuestionItem | null }) {
  const rows = ruleRows(item, question);
  const asking = question !== null && !question.answered;
  const decided = rows.some((r) => r.approved !== null);
  return (
    <Card name="rules">
      <CardHeader label="Rules · proposed by Lawmaker, reviewed by Rule Critic" pill={headerPill(rows, asking, decided)} />
      {question !== null ? (
        <Approval question={question} rows={rows} />
      ) : (
        <div className="rounded-lg border border-line">
          {rows.map((row, i) => (
            <RuleLine key={row.id} row={row} index={i} asking={false} checked={false} disabled onToggle={() => {}} inputId="" />
          ))}
        </div>
      )}
    </Card>
  );
}
