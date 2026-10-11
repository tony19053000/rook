// The /docs page copy (06 §5.2). The six steps themselves come from ./flow.ts (one list, also used by the home
// walkthrough). Every command and file below is checked against the code: `rook --help` (src/rook/cli/main.py),
// src/rook/cli/scaffold.py, src/rook/export/counterexample.py, action.yml and the README.

import { INSTALL_COMMAND } from "./site";

export const docsCopy = {
  title: "Docs",
  description: "How Rook works, step by step, and how to install the CLI and add the GitHub Action.",
  eyebrow: "Docs",
  heading: "How Rook works",
  lead: "From your repo to a verified fix in six steps, then how to install the rook CLI and run it on every pull request.",
  /** In-page navigation (the anchors the footer links to). */
  tocLabel: "On this page",
  stepLabel: "Step",
} as const;

export const howItWorks = {
  id: "how-it-works",
  title: "How it works",
  intro:
    "Bob agents propose and explain; the deterministic engine decides. Only the engine marks a rule broken or a fix verified, and you approve the rules and the fix.",
} as const;

export interface DocCommand {
  usage: string;
  purpose: string;
}

export const gettingStarted = {
  id: "getting-started",
  title: "Getting started",
  intro: "Rook runs on your machine as the rook command. It starts your app in a Docker sandbox and works on a copy of your repo.",
  requirements: {
    heading: "Requirements",
    items: [
      "Python 3.12 or newer.",
      "Docker (the CLI starts your app in a Docker sandbox).",
      "IBM Bob Shell with your own BOB_API_KEY, for live runs.",
    ],
  },
  install: {
    heading: "Install",
    command: INSTALL_COMMAND,
    note: "Rook is not on PyPI yet, so it installs from GitHub.",
  },
  firstRun: {
    heading: "First run",
    paragraphs: [
      "Run rook in your repo to open the interactive session in your terminal. Bob's agents appear as characters while they work, and Rook asks you before the steps that matter: approving the rules, applying a fix and opening a pull request.",
      "To check a specific repo, pass it to rook run: a local folder (Rook copies it and never changes the original) or a GitHub owner/name.",
    ],
    examples: ["rook", "rook run ./my-app", "rook run owner/name"],
  },
  commands: {
    heading: "CLI commands",
    items: [
      { usage: "rook", purpose: "Open the interactive session." },
      {
        usage: "rook run [repo]",
        purpose:
          "Search a repo for broken business rules. Add --ci for plain output, report files and exit codes (0 every approved rule held, 1 a rule is broken, 2 the run did not finish), and --auto to let Rook answer its own questions.",
      },
      { usage: "rook replay <cx> --base-url <url>", purpose: "Replay a counterexample against your running app (exit 1 while the rule is still broken)." },
      { usage: "rook verify <cx> --base-url <url>", purpose: "Check a fix on your running app: the exact replay plus a fresh search (exit 0 when both pass)." },
      { usage: "rook explain <cx>", purpose: "Explain a counterexample in plain words: the rule, the minimal steps and what was observed." },
      { usage: "rook init", purpose: "Set up a repo: the rook/ folder and a GitHub workflow that runs rook run --ci." },
      { usage: "rook serve", purpose: "Start the Rook API server (the web app's backend)." },
      { usage: "rook login", purpose: "Sign in with Google (saved to ~/.rook/credentials.json, readable only by you)." },
      { usage: "rook logout", purpose: "Sign out: revoke the session on the server and delete the saved credentials on this machine." },
    ] satisfies DocCommand[],
  },
  files: {
    heading: "Files Rook adds to your repo",
    code: [
      "rook/rook.yaml                    # approved actions, state and rules",
      "rook/counterexamples/cx_001.json  # every counterexample, replayable",
    ].join("\n"),
    note: "rook init also writes rook/README.md and a workflow at .github/workflows/rook.yml. It never overwrites a file that already exists unless you pass --force.",
  },
} as const;

export const githubAction = {
  id: "github-action",
  title: "GitHub Action",
  intro:
    "action.yml runs rook run --ci --auto on each pull request and keeps one rook-report.md comment on it up to date. The job fails if an approved rule breaks (exit 1) or the run doesn't finish (exit 2).",
  workflowLabel: ".github/workflows/rook.yml",
  workflow: `name: rook
on:
  pull_request:
permissions:
  contents: read
  pull-requests: write
jobs:
  rook:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          persist-credentials: false
      - uses: tony19053000/rook@<full-commit-sha>   # pin to a commit SHA
        with:
          bob-mode: live                            # falls back to replay without a key
          bob-api-key: \${{ secrets.BOB_API_KEY }}
          recordings: rook/recordings`,
  pinNote: "Replace <full-commit-sha> with the full commit SHA of the Rook version you want, so the action can't change under you.",
  warningTitle: "Use pull_request, never pull_request_target",
  warning:
    "With pull_request_target, a fork's code would run with your secrets. Pull requests from forks get no secrets, so the action falls back to recorded Bob answers.",
  more: { label: "All inputs in action.yml", path: "action.yml" },
} as const;
