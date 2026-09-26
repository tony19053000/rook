"use client";

// The chat column of a run (04 §3.1, §4): every transcript item as its row or card, in arrival order.
// Questions with a related card (approve_rules, fix, pr) are drawn on that card; the others get a
// QuestionCard. Every event string is cleaned before it is drawn, and all of it is React text.

import { AgentRow } from "./AgentRow";
import { EngineRow } from "./EngineRow";
import { CounterexampleCard } from "./cards/CounterexampleCard";
import { FixCard } from "./cards/FixCard";
import { QuestionCard } from "./cards/QuestionCard";
import { RulesCard } from "./cards/RulesCard";
import { SearchCard } from "./cards/SearchCard";
import { VerifyCard } from "./cards/VerifyCard";
import { attachQuestions } from "@/lib/questions";
import type { ChatItem, LogItem, RulesItem, RunState, TranscriptItem } from "@/lib/runStore";
import { cleanMultiline } from "@/lib/safeText";

function ChatRow({ item }: { item: ChatItem }) {
  const text = cleanMultiline(item.text).trim();
  if (item.role === "user") {
    return (
      <div data-chat="user" className="max-w-[80%] self-end whitespace-pre-wrap break-words rounded-xl border border-line bg-surface px-3.5 py-2">
        {text}
      </div>
    );
  }
  return (
    <div data-chat="guide" className="whitespace-pre-wrap break-words">
      <span className="font-semibold text-muted">◆ Guide </span>
      {text}
    </div>
  );
}

function LogRow({ item }: { item: LogItem }) {
  const color = item.level === "error" ? "text-bad" : item.level === "warn" ? "text-warn" : "text-muted";
  return (
    <div data-log={item.level} className={`whitespace-pre-wrap break-words text-[13px] ${color}`}>
      {item.level !== "info" && <span className="font-semibold">{item.level === "error" ? "✗ " : "! "}</span>}
      {cleanMultiline(item.text).trim()}
    </div>
  );
}

const NO_RULES: Omit<RulesItem, "key"> = { kind: "rules", rules: [], verdicts: {}, approvedIds: null };

export function Transcript({ state }: { state: RunState }) {
  const { byCard, attached } = attachQuestions(state.items);
  const observed = new Map<string, unknown>();
  for (const item of state.items) if (item.kind === "counterexample" && item.saved !== null) observed.set(item.saved.cx_id, item.saved.observed);
  const searching = state.phase === "SEARCH" && state.status === "running";

  const row = (item: TranscriptItem) => {
    switch (item.kind) {
      case "agent":
        return <AgentRow item={item} />;
      case "engine":
        return <EngineRow item={item} />;
      case "question":
        if (attached.has(item.key)) return null;
        // approve_rules is always answered on a RulesCard, even if no rules card came before it.
        if (item.questionKind === "approve_rules") return <RulesCard item={{ ...NO_RULES, key: item.key }} question={item} />;
        return <QuestionCard question={item} />;
      case "chat":
        return <ChatRow item={item} />;
      case "log":
        return <LogRow item={item} />;
      case "rules":
        return <RulesCard item={item} question={byCard.get(item.key) ?? null} />;
      case "search":
        return <SearchCard item={item} searching={searching && item.key === state.refs.search} />;
      case "counterexample":
        return <CounterexampleCard item={item} />;
      case "fix":
        return <FixCard item={item} question={byCard.get(item.key) ?? null} />;
      case "verify":
        return <VerifyCard item={item} question={byCard.get(item.key) ?? null} before={observed.get(item.cxId) ?? null} />;
    }
  };

  return (
    <>
      {state.items.map((item) => {
        const node = row(item);
        return node === null ? null : (
          <div key={item.key} className="flex min-w-0 flex-col" data-item={item.kind}>
            {node}
          </div>
        );
      })}
    </>
  );
}
