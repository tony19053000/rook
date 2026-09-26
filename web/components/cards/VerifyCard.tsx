"use client";

// VerifyCard (04 §3.4): Before (the counterexample's observed values) / After (the replay on the fixed app),
// one row per verify check with a pill, then `✓ FIX VERIFIED` (only the engine says so), the ship question,
// the commit line, and after pr.opened a "View pull request" button. The PR URL is a link only when it is
// an https://github.com/ URL; anything else is shown as plain text.

import { Mark } from "../AgentRow";
import { Card, CardHeader, Label, Pill, type Tone } from "./ui";
import { ConfirmAnswer, questionText } from "./QuestionCard";
import { checkName, observedText, safeGithubUrl, short } from "@/lib/cardText";
import type { VerifyStatus } from "@/lib/events";
import type { QuestionItem, VerifyItem } from "@/lib/runStore";
import { clean } from "@/lib/safeText";

const STATUS: Record<VerifyStatus, { tone: Tone; text: string }> = {
  running: { tone: "idle", text: "Running…" },
  passed: { tone: "good", text: "✓ Passed" },
  failed: { tone: "bad", text: "✗ Failed" },
};

function statusOf(status: string): { tone: Tone; text: string } {
  return STATUS[status as VerifyStatus] ?? { tone: "idle", text: short(status, 20) };
}

export function PrLink({ url, number }: { url: string; number: number }) {
  const href = safeGithubUrl(url);
  const n = Number.isFinite(number) ? Math.trunc(number) : "?";
  return (
    <div className="flex flex-wrap items-center gap-2" data-pr>
      <span className="text-[13px]">
        <Mark ok /> PR #{n} opened
      </span>
      {href !== null ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-accent bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-ink"
        >
          View pull request
        </a>
      ) : (
        <span className="break-all font-mono text-xs text-muted" data-pr-text>
          {short(url, 200)}
        </span>
      )}
    </div>
  );
}

export function VerifyCard({
  item,
  question = null,
  before = null,
}: {
  item: VerifyItem;
  question?: QuestionItem | null;
  /** The counterexample's observed values (the "Before" box). */
  before?: unknown;
}) {
  const checks = Object.entries(item.checks);
  const replay = item.checks.replay;
  const pill =
    item.done === null ? (
      <Pill tone="warn">Checking…</Pill>
    ) : item.done.verified ? (
      <Pill tone="good">✓ Fix verified</Pill>
    ) : (
      <Pill tone="bad">✗ Not verified</Pill>
    );
  return (
    <Card name="verify">
      <CardHeader label={`Verification by the engine · ${short(item.cxId, 40)}`} pill={pill} />
      {before !== null && before !== undefined && (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          <div className="flex min-w-0 flex-col items-center gap-1 rounded-lg border border-bad bg-bad-soft px-3 py-2.5 text-center">
            <Label>Before</Label>
            <span className="num max-w-full break-words text-sm font-semibold text-bad">{observedText(before)}</span>
            <Pill tone="bad">✗ Rule broken</Pill>
          </div>
          <div
            className={`flex min-w-0 flex-col items-center gap-1 rounded-lg border px-3 py-2.5 text-center ${
              replay?.status === "passed" ? "border-good bg-good-soft" : "border-line bg-app"
            }`}
          >
            <Label>After</Label>
            <span className="max-w-full break-words text-sm">{replay?.detail ? clean(replay.detail) : "…"}</span>
            <Pill tone={replay ? statusOf(replay.status).tone : "idle"}>{replay ? statusOf(replay.status).text : "Pending"}</Pill>
          </div>
        </div>
      )}
      {checks.length > 0 && (
        <div className="rounded-lg border border-line">
          {checks.map(([check, c]) => {
            const s = statusOf(c.status);
            const fresh = check === "fresh_search" && c.status === "running" && item.freshSearch !== null;
            const detail = fresh ? `${Math.round(item.freshSearch!.sequences).toLocaleString("en-US")} sequences` : clean(c.detail);
            return (
              <div key={check} data-check={check} className="flex items-center gap-2.5 border-t border-line px-3 py-2 text-[13.5px] first:border-t-0">
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{checkName(check)}</span>
                  {detail && <span className="block truncate font-mono text-xs text-muted">{detail}</span>}
                </span>
                <Pill tone={s.tone}>{s.text}</Pill>
              </div>
            );
          })}
        </div>
      )}
      {item.done !== null &&
        (item.done.verified ? (
          <div className="font-bold text-good" data-verified>
            ✓ FIX VERIFIED
          </div>
        ) : (
          <div data-verified="false">
            <Mark ok={false} /> <b>Fix not verified</b> · {clean(item.done.summary)}
          </div>
        ))}
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
      {item.committed !== null && (
        <div className="text-[13px]" data-committed>
          <Mark ok /> Fix committed to <span className="font-mono">{short(item.committed.branch, 80)}</span> ·{" "}
          <span className="font-mono">{clean(item.committed.commit).slice(0, 7)}</span> ·{" "}
          {Array.isArray(item.committed.files) ? item.committed.files.length : 0} files
        </div>
      )}
      {item.pr !== null && <PrLink url={item.pr.url} number={item.pr.number} />}
    </Card>
  );
}
