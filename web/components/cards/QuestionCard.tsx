"use client";

// Question prompts (04 §2.2, §3.4), the twin of the TUI's prompts.py: a confirm (fix, pr), a menu, and a
// masked setup value. The approve_rules prompt lives on the RulesCard. Answers go to POST answers; once
// answered the controls collapse to `✓ <answer>`.

import { useState, type FormEvent } from "react";
import { Button, Card, ClosedAnswer, Countdown, Note, useAnswer, useCountdown, useRunActions } from "./ui";
import { short } from "@/lib/cardText";
import { cleanOptions, confirmChoices, describeAnswer, guestAutoAnswer, questionUi, valueQuestion } from "@/lib/questions";
import type { QuestionItem } from "@/lib/runStore";
import { clean, cleanMultiline } from "@/lib/safeText";

export function questionText(question: QuestionItem): string {
  return clean(cleanMultiline(question.text).trim());
}

function describeFor(question: QuestionItem) {
  return (answer: unknown) => describeAnswer(answer, question.options);
}

/** Yes / no buttons, e.g. "Fix it" / "Not now". In guest demo mode "yes" is sent after the countdown. */
export function ConfirmAnswer({ question }: { question: QuestionItem }) {
  const { guest, autoSeconds } = useRunActions();
  const { state, submit, locked } = useAnswer(question);
  const [yes, no] = confirmChoices(question);
  const auto = guestAutoAnswer(question);
  const countdown = useCountdown(guest && auto !== null && !locked && state.status !== "error", autoSeconds, () => {
    if (auto !== null) void submit(auto, yes.label);
  });
  const closed = <ClosedAnswer question={question} state={state} describe={describeFor(question)} />;
  if (question.answered || state.status === "sent" || state.status === "closed") return closed;

  const choose = (option: { id: string; label: string }) => {
    countdown.stop();
    void submit(option.id, option.label);
  };
  return (
    <div className="flex flex-wrap items-center gap-2" data-question={question.questionId}>
      <Button primary disabled={locked} onClick={() => choose(yes)}>
        {yes.label}
      </Button>
      <Button disabled={locked} onClick={() => choose(no)}>
        {no.label}
      </Button>
      <Countdown left={countdown.left} onStop={countdown.stop} what={`“${yes.label}”`} />
      {state.status === "error" && <Note tone="bad">{state.message}</Note>}
    </div>
  );
}

/** One button per option (the repo picker, "What next?"). */
export function MenuAnswer({ question }: { question: QuestionItem }) {
  const { state, submit, locked } = useAnswer(question);
  const closed = <ClosedAnswer question={question} state={state} describe={describeFor(question)} />;
  if (question.answered || state.status === "sent" || state.status === "closed") return closed;
  return (
    <div className="flex flex-col items-start gap-1.5" role="group" aria-label="Choose one" data-question={question.questionId}>
      {cleanOptions(question.options).map((option, i) => (
        <Button key={option.id} primary={i === 0} disabled={locked} onClick={() => void submit(option.id, option.label)}>
          {option.label}
        </Button>
      ))}
      {state.status === "error" && <Note tone="bad">{state.message}</Note>}
    </div>
  );
}

/**
 * A typed setup value. Masked unless the payload says `secret: false`. The value is cleared from the input
 * as soon as it is sent and is never drawn: the card then reads `NAME provided`.
 */
export function ValueAnswer({ question }: { question: QuestionItem }) {
  const { state, submit, locked } = useAnswer(question);
  const { name, secret } = valueQuestion(question);
  const [value, setValue] = useState("");
  const [empty, setEmpty] = useState(false);
  const closed = <ClosedAnswer question={question} state={state} describe={describeFor(question)} />;
  if (question.answered || state.status === "sent" || state.status === "closed") return closed;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (locked) return;
    if (value.trim() === "") {
      setEmpty(true);
      return;
    }
    const sent = value;
    setValue("");
    setEmpty(false);
    void submit(sent, secret ? `${name || "Value"} provided` : short(sent, 120));
  };
  const inputId = `q-${question.questionId}`;
  return (
    <form className="flex flex-wrap items-center gap-2" onSubmit={onSubmit} data-question={question.questionId}>
      <label htmlFor={inputId} className="sr-only">
        {name || "Value"}
      </label>
      <input
        id={inputId}
        type={secret ? "password" : "text"}
        autoComplete="off"
        spellCheck={false}
        maxLength={10000}
        value={value}
        disabled={locked}
        placeholder={secret ? "hidden value" : "value"}
        onChange={(e) => setValue(e.target.value)}
        className="min-w-0 flex-1 rounded-lg border border-line bg-app px-3 py-1.5 font-mono text-[13px] text-ink outline-none placeholder:text-faint"
      />
      <Button primary type="submit" disabled={locked}>
        Send
      </Button>
      {empty && <Note tone="warn">Enter a value first.</Note>}
      {state.status === "error" && <Note tone="bad">{state.message}</Note>}
    </form>
  );
}

/** The controls for a question, picked like the TUI's make_prompt (the rules prompt is on the RulesCard). */
export function QuestionControls({ question }: { question: QuestionItem }) {
  switch (questionUi(question)) {
    case "confirm":
      return <ConfirmAnswer question={question} />;
    case "menu":
      return <MenuAnswer question={question} />;
    case "value":
      return <ValueAnswer question={question} />;
    case "rules":
      return null; // approve_rules is always answered on a RulesCard (the Transcript makes one if needed)
  }
}

/** A standalone question: `? text` and its controls (setup_value, menu, or any question with no card). */
export function QuestionCard({ question }: { question: QuestionItem }) {
  return (
    <Card name="question">
      <div className="font-semibold">
        <span className="text-warn" aria-hidden>
          ?
        </span>
        <span className="sr-only">Question:</span> {questionText(question)}
      </div>
      <QuestionControls question={question} />
    </Card>
  );
}
