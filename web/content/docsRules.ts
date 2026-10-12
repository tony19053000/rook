// /docs/rules (ROOK-055): the approved-rules workflow and rook/rook.yaml. Sources: src/rook/agents/rules.py and
// src/rook/engine/sanity.py (the pipeline, already_broken), src/rook/core/session.py (auto answers),
// src/rook/cli/ci.py (what --ci answers without --auto), src/rook/model/schema.py (the file's fields),
// src/rook/model/expr.py (the safe evaluator), 02 §6 and §16. The example file itself is
// lib/fixtures/minishopRookYaml.ts, a verbatim copy of tests/fixtures/minishop/rook.yaml.

import type { DocGuide } from "./docsModel";

/** src/rook/model/expr.py `_FUNCTIONS`: the only calls a check may make. */
export const CHECK_FUNCTIONS = ["sum", "len", "min", "max", "abs", "all", "any", "round"] as const;
/** src/rook/model/schema.py MAX_CHECK_LEN. */
export const CHECK_MAX_CHARS = 500;

export const rulesGuide: DocGuide = {
  path: "/docs/rules",
  navLabel: "Rules",
  title: "Rules",
  description: "How a business rule gets proposed, checked and approved in Rook, and what rook/rook.yaml holds, with a real example file.",
  heading: "Rules",
  lead: "A rule is a business invariant that must hold after every step, such as: total refunds never exceed the amount paid. Bob proposes rules, you approve them, and the engine searches only for the ones you approved.",
  summary: "How rules are proposed, checked and approved, with a real rook/rook.yaml and its format.",
  sections: [
    {
      id: "workflow",
      title: "How a rule gets approved",
      blocks: [
        {
          kind: "list",
          ordered: true,
          items: [
            "The Lawmaker proposes rules, each with evidence from your code: the place that suggests the rule should hold.",
            "The engine checks every proposed rule. Its check must parse with the safe evaluator, use only the state and fields the model defines, and hold on a fresh app. A rule that fails is rejected with the engine's reason and goes no further.",
            "The Rule Critic judges what the remaining rules mean: a real invariant, too weak, or a duplicate. It can approve, reject or revise a rule. A revised rule is checked by the engine again, and the Critic can never rescue a rule the engine rejected.",
            "You approve all of the accepted rules, none of them, or the ones you pick. Until then they are saved with the status proposed.",
            "The rules you approved are saved in rook/rook.yaml with the status approved. The search checks these and no others.",
          ],
        },
        {
          kind: "p",
          text: "Bob's part ends at proposing and reviewing. Whether a rule is broken is decided later by the engine alone, by running your app.",
        },
      ],
    },
    {
      id: "already-broken",
      title: "Rules the app already breaks",
      blocks: [
        {
          kind: "p",
          text: "A state rule that is false on a fresh app is rejected: it is a wrong rule. A response rule is different, because it is judged on a single request. If the app breaks it on the very first request, Rook cannot tell a one-step bug from a wrong rule, so it keeps the rule and flags it `already_broken`.",
        },
        {
          kind: "p",
          text: "The flag is shown with the rule and its reason. A person may approve a flagged rule. Auto mode never does.",
        },
      ],
    },
    {
      id: "auto-mode",
      title: "Auto mode",
      blocks: [
        {
          kind: "p",
          text: "With `rook run --auto`, Rook answers its own questions inside limits that are enforced in code:",
        },
        {
          kind: "list",
          items: [
            "It approves only rules the Rule Critic approved or revised, and never one flagged `already_broken`.",
            "It applies a fix only for a diagnosis the Diagnosis Reviewer approved.",
            "The fix still lands on its own rook/fix-* branch, never on your default branch.",
            "It never invents a setup value: those come from `rook run --setup NAME` or from you.",
          ],
        },
        {
          kind: "p",
          text: "`rook run --ci` without `--auto` approves the same rules, but answers no to fixing and shipping: it reports and changes no code.",
        },
      ],
    },
    {
      id: "example",
      title: "An example rook/rook.yaml",
      blocks: [
        {
          kind: "p",
          text: "This is tests/fixtures/minishop/rook.yaml from the Rook repo, unchanged: the hand-written model of minishop, Rook's own small test shop, which Rook's engine tests run against. It has four approved rules, one for each bug planted in that shop.",
        },
        { kind: "slot", name: "rook-yaml" },
        {
          kind: "p",
          text: "In a run on your repo, the Mapper and the Lawmaker write this file and you approve its rules, so the names are theirs. The recorded run on the Counterexamples page named the same refund rule `refunded_total_le_paid`.",
        },
      ],
    },
    {
      id: "format",
      title: "The file, part by part",
      blocks: [
        {
          kind: "p",
          text: "The file is validated strictly: an unknown field, a duplicate name or a reference to an actor, action or state reader that does not exist is an error. `version` is 1.",
        },
      ],
      subsections: [
        {
          id: "format-app",
          title: "app",
          blocks: [
            {
              kind: "terms",
              items: [
                { term: "base_url", text: "Always {{sandbox.base_url}}. Rook fills it in at run time with the sandbox's address; any other value is rejected." },
                { term: "health", text: "The request Rook polls until the app is up: a method, a path and the expected status." },
                { term: "isolation", text: "fresh_entities (the default): every sequence creates its own actors and entities, so nothing is reset between sequences. restart: the sandbox is restarted instead." },
              ],
            },
          ],
        },
        {
          id: "format-actors",
          title: "actors",
          blocks: [
            {
              kind: "p",
              text: "Who sends the requests. Each actor has a name, optional `setup` requests that run at the start of a sequence to create a fresh actor (sign up, log in), a `capture` that reads values such as a token out of a response with a JSONPath, and the `auth` header its requests carry.",
            },
          ],
        },
        {
          id: "format-actions",
          title: "actions",
          blocks: [
            {
              kind: "terms",
              items: [
                { term: "name, actor", text: "What the action is called, and which actor sends it." },
                { term: "request", text: "A declarative HTTP template: method, path, and optionally json, query and headers. The path is relative to the sandbox. An absolute URL anywhere in a request is rejected." },
                { term: "params", text: "The values the search generates. `int: [lo, hi]` with optional `edges` (values tried more often), `choice` with a list of values, or `string` with a `pattern` or a list of `values`." },
                { term: "requires", text: "The captured variables that must exist before this action can run. refund requires an order_id, so it can only follow buy." },
                { term: "capture", text: "Values read from the response and added to the sequence's variables, such as the id of the order just created." },
                { term: "weight", text: "How often the search picks this action, relative to the others. The default is 1.0." },
              ],
            },
          ],
        },
        {
          id: "format-state",
          title: "state",
          blocks: [
            {
              kind: "p",
              text: "State readers are how Rook sees your app's state: plain HTTP reads. A reader has a name, `each` (the captured variable it is read for, such as every order_id the sequence created), the request, and `fields` picked out of the response with JSONPaths. Rules refer to these fields, as in order.refunded.",
            },
          ],
        },
        {
          id: "format-rules",
          title: "rules",
          blocks: [
            {
              kind: "terms",
              items: [
                { term: "id, text", text: "A short identifier, and the rule in plain words." },
                { term: "kind: state", text: "A check on state after every step. `scope` names the state reader it applies to, or global." },
                { term: "kind: response", text: "A check on the response to one action. It needs `when`: the action, and optionally the actor who sends it." },
                { term: "check", text: `The expression that must be true, at most ${CHECK_MAX_CHARS} characters.` },
                { term: "evidence", text: "Where in the code the rule comes from." },
                { term: "status", text: "proposed, approved or rejected. Only approved rules are searched." },
              ],
            },
          ],
        },
        {
          id: "format-templates",
          title: "Templates",
          blocks: [
            {
              kind: "terms",
              items: [
                { term: "{{p.name}}", text: "A generated param of this action." },
                { term: "{{ref.name}}", text: "A value captured earlier in the sequence, picked from those available." },
                { term: "{{fresh.name}}", text: "A value that is unique to the sequence, such as a new email address." },
                { term: "{{env.NAME}}", text: "A setup value from the sandbox's environment, such as an admin password. It is never written into the file." },
                { term: "{{actor.token}}", text: "A value the current actor captured in its setup." },
              ],
            },
          ],
        },
      ],
    },
    {
      id: "checks",
      title: "Check expressions and the safe evaluator",
      blocks: [
        {
          kind: "p",
          text: "A check is one expression over the values Rook read from your app. A state rule sees its state reader by name, as in `order.refunded <= order.paid`. A response rule sees `response`, as in `response.status in (401, 403)`.",
        },
        {
          kind: "list",
          items: [
            "Allowed: comparisons, `and`, `or`, `not`, `in`, arithmetic, tuples and lists, indexing, reading a field with a dot, and generator expressions and list comprehensions.",
            `Allowed calls, and no others: ${CHECK_FUNCTIONS.join(", ")}.`,
            "Refused: any other call, names starting with an underscore, lambdas, assignment, f-strings, conditional expressions, slices and the power operator.",
          ],
        },
        {
          kind: "p",
          text: "Rules come from Bob, so Rook treats them as untrusted. A check is parsed into a syntax tree, every node is compared with an allowlist, and a small interpreter inside Rook walks the tree with limits on depth and work. Python's own eval and exec are never used, on checks or on anything else Bob writes.",
        },
      ],
    },
    {
      id: "limits",
      title: "What is not built yet",
      blocks: [
        {
          kind: "list",
          items: [
            "In the web app, editing a single rule is not built yet: you approve or reject the rules as proposed.",
            "Rook does not yet read rules you wrote by hand before a run: the Lawmaker proposes them in each run, and you choose.",
          ],
        },
      ],
    },
  ],
};
