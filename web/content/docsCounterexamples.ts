// /docs/counterexamples (ROOK-055): minimal counterexamples, replay consistency and verified fixes. Sources: 02
// §7.1 (sequence length), §7.4 (shrinker), §7.5 (replayer), §7.7 (verifier), §7.8 (regression test), §16;
// src/rook/engine/replayer.py (DEFAULT_REPLAYS, flaky), src/rook/engine/verifier.py (budget 20,000 / 120 s),
// src/rook/export/counterexample.py (the `Counterexample` model: tests/unit/test_docs_cli_commands.py checks the
// field list below against it), src/rook/cli/cx.py and the --help of the replay, verify and explain commands. The refund case is
// content/story.ts (the recorded minishop run), rendered by components/site/home/RefundStory.tsx.

import { lines, type DocGuide } from "./docsModel";
import { refundCounterexample, refundFound, storyCopy } from "./story";

/** The fields of rook/counterexamples/cx_NNN.json, in file order (the `Counterexample` pydantic model). */
export const cxFields = [
  { term: "version", text: "The file format, 1." },
  { term: "cx_id", text: "The counterexample's id, such as cx_001. It is also the file name." },
  { term: "rule", text: "The broken rule as it was when found: id, text, kind, scope, when and check." },
  {
    term: "steps",
    text: "The minimal sequence. Each step has its action, actor and the exact params, plus refs: which earlier captured value each reference used. Steps sent at the same time are grouped under parallel.",
  },
  { term: "violated_at_step", text: "The step after which the rule was false, counted from 0." },
  { term: "observed", text: "The values the engine read from your app at that point. Very large or deeply nested values are cut, and the cut is marked." },
  { term: "expected", text: "The rule's check expression: what must be true." },
  { term: "reproduced", text: "How many replays broke the rule, such as 10/10." },
  { term: "flaky", text: "True when some replays broke the rule and others did not." },
  { term: "seed", text: "The search seed the sequence was found with." },
  { term: "model_hash", text: "A hash of the rook.yaml model it was found with." },
  { term: "created_at", text: "When it was saved." },
] as const;

export const counterexamplesGuide: DocGuide = {
  path: "/docs/counterexamples",
  navLabel: "Counterexamples",
  title: "Counterexamples and verified fixes",
  description: "How Roook shrinks a failing sequence to a minimal counterexample, replays it, and verifies a fix with four engine checks, shown on one recorded case.",
  heading: "Counterexamples and verified fixes",
  lead: "A counterexample is the smallest sequence of valid actions that breaks one approved rule, replayed on the real app. This guide explains how Roook gets there and what counts as a verified fix, using one recorded case.",
  summary: "Minimal counterexamples, replay consistency and the four checks of a verified fix, on the recorded refund case.",
  sections: [
    {
      id: "minimal",
      title: "Minimal counterexamples",
      blocks: [
        {
          kind: "p",
          text: "The search runs sequences of up to 12 steps, so the first sequence that breaks a rule usually carries steps and values that have nothing to do with the bug. The shrinker removes them in two passes:",
        },
        {
          kind: "list",
          ordered: true,
          items: [
            "Steps. Delta debugging removes parts of the sequence and runs each shorter candidate for real, on fresh entities. A candidate is kept only if it still breaks the same rule. Steps whose requirements are no longer met are dropped with it.",
            "Values. Each param is moved toward its smallest or edge value for as long as the rule still breaks.",
          ],
        },
        {
          kind: "p",
          text: "The result is minimal in a precise sense: take away any single step and the rule no longer breaks. Nothing is estimated; every candidate was executed against your running app.",
        },
      ],
    },
    {
      id: "replay",
      title: "Replay consistency",
      blocks: [
        {
          kind: "p",
          text: "A sequence that failed once might have been luck or timing. So the engine replays the exact minimal sequence 10 times by default, on fresh entities each time, and reports how many replays broke the rule.",
        },
        {
          kind: "list",
          items: [
            "Every replay breaks the rule, shown as 10/10: a deterministic bug.",
            "Some replays break it and some do not: the counterexample is marked flaky and still reported, with its count. Bugs that need two requests at the same moment usually look like this.",
          ],
        },
        {
          kind: "p",
          text: "The counterexample is then saved as a JSON file together with a regression test. The test is run on the unfixed code first and must fail there, which shows it tests the bug.",
        },
      ],
    },
    {
      id: "refund-case",
      title: "The refund case, from a recorded run",
      blocks: [
        { kind: "p", text: storyCopy.intro },
        { kind: "slot", name: "refund-story" },
        {
          kind: "p",
          text: `In this run the search first broke the rule with paid ${refundFound.paid} and refunded ${refundFound.refundedTotal}. The shrinker tried shorter sequences, found that all ${refundCounterexample.steps.length} steps are needed, and cut the values down to 1. The fresh search in this recorded run used a smaller budget than the CLI's default.`,
        },
      ],
    },
    {
      id: "verified-fixes",
      title: "Verified fixes",
      blocks: [
        { kind: "p", text: "A fix counts only if four checks pass, and all four are run by the engine, not judged by an AI:" },
        {
          kind: "list",
          ordered: true,
          items: [
            "Exact replay. The counterexample's steps are replayed on the fixed app, and the rule must hold in every replay.",
            "Your project's tests. The fix must not break what already passed.",
            "The generated regression test. It failed before the fix and must pass now.",
            "A fresh search with a new seed. No approved rule may break. In the CLI the default budget is 20,000 sequences or 120 seconds, whichever comes first.",
          ],
        },
        {
          kind: "p",
          text: "When a check fails, Roook goes back to the diagnosis with the new evidence, up to 3 times, and then reports honestly that the fix is not verified. Only a verified fix is committed to a rook/fix-* branch.",
        },
      ],
    },
    {
      id: "file",
      title: "The counterexample file",
      blocks: [
        {
          kind: "p",
          text: "Every counterexample is saved as rook/counterexamples/cx_NNN.json, numbered from cx_001. It holds everything needed to replay the sequence exactly, and Roook never overwrites one that exists.",
        },
        { kind: "terms", items: [...cxFields] },
      ],
    },
    {
      id: "commands",
      title: "Replay, verify and explain",
      blocks: [
        {
          kind: "p",
          text: "Three commands work on a saved counterexample, against an app you started yourself. None of them calls IBM Bob.",
        },
        {
          kind: "code",
          code: lines(
            "rook explain cx_001",
            "rook replay cx_001 --base-url http://127.0.0.1:8000",
            "rook verify cx_001 --base-url http://127.0.0.1:8000",
          ),
        },
        {
          kind: "terms",
          items: [
            {
              term: "rook explain",
              text: "Prints the rule, the minimal steps, the step where the rule broke, the observed values and the replay count. It needs no running app.",
            },
            {
              term: "rook replay",
              text: "Runs the exact steps against your app, 10 times unless you pass `rook replay cx_001 --base-url http://127.0.0.1:8000 --times 3`. Exit code 1 while the rule is still broken, 0 when it held in every replay, 2 when the replay proves nothing or the arguments are wrong.",
            },
            {
              term: "rook verify",
              text: "Runs two of the four checks on your app: the exact replay and a fresh search (2,000 sequences or 60 seconds by default; change them with `rook verify cx_001 --base-url http://127.0.0.1:8000 --sequences 20000 --seconds 120`). Exit code 0 when both pass. Your project's tests and the regression test are not run by this command: they run inside the sandbox during `rook run`.",
            },
          ],
        },
        {
          kind: "list",
          items: [
            "The counterexample is an id, looked up in rook/counterexamples/ of the current folder, or a path to its .json file. Pass `rook explain cx_001 --repo ~/.rook/workspaces/<run-id>` to look in another folder, such as the workspace of a run on a local folder.",
            "The model is read from rook/rook.yaml in the same folder, or from the file you name: `rook explain cx_001 --model ./rook/rook.yaml`.",
            "The app address must be a loopback address on your machine, such as http://127.0.0.1:8000. Anything else is refused.",
            "Values the model reads from the environment come from variables named ROOK_ENV_ plus the name, such as ROOK_ENV_ADMIN_PASSWORD.",
          ],
        },
        {
          kind: "p",
          text: "In the web app, replaying a counterexample and downloading its test are not built yet.",
        },
      ],
    },
  ],
};
