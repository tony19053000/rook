// The /docs overview copy (06 §1, §5.2; reworked in ROOK-055): the six steps, which come from ./flow.ts (one list,
// also used by the home walkthrough), the index of the guides (./docsGuides.ts) and the CLI's commands. Every
// command below is checked against the real CLI by tests/unit/test_docs_cli_commands.py and by
// components/site/site.test.tsx (the list equals the commands src/rook/cli/main.py defines).

export const docsCopy = {
  title: "Docs",
  description: "How Rook works in six steps, and guides to installing it, approving rules, reading counterexamples, the GitHub Action and what is sent to IBM Bob.",
  eyebrow: "Docs",
  heading: "Rook documentation",
  lead: "How Rook gets from your repo to a verified fix in six steps, then a guide for each part: installing, rules, counterexamples, the GitHub Action, and what is sent to IBM Bob.",
  /** In-page navigation. */
  tocLabel: "On this page",
  stepLabel: "Step",
  guideLink: "Read the guide",
} as const;

export const howItWorks = {
  id: "how-it-works",
  title: "How it works",
  intro:
    "Bob agents propose and explain; the deterministic engine decides. Only the engine marks a rule broken or a fix verified, and you approve the rules and the fix.",
} as const;

export const guidesIndex = {
  id: "guides",
  title: "Guides",
  intro: "Start with Getting started. Each guide states what Rook does today, including what is limited or not built yet.",
} as const;

export interface DocCommand {
  usage: string;
  purpose: string;
}

export const cliReference = {
  id: "cli",
  title: "CLI commands",
  intro: "Every command takes --help. The guides show each one in use.",
  items: [
    { usage: "rook", purpose: "Open the interactive session." },
    {
      usage: "rook run [repo]",
      purpose:
        "Search a repo for broken business rules. Add `--ci` for plain output, report files and exit codes (0 every approved rule held, 1 a rule is broken, 2 the run did not finish), and `--auto` to let Rook answer its own questions.",
    },
    { usage: "rook replay <cx> --base-url <url>", purpose: "Replay a counterexample against your running app (exit 1 while the rule is still broken)." },
    { usage: "rook verify <cx> --base-url <url>", purpose: "Check a fix on your running app: the exact replay plus a fresh search (exit 0 when both pass)." },
    { usage: "rook explain <cx>", purpose: "Explain a counterexample in plain words: the rule, the minimal steps and what was observed." },
    { usage: "rook init", purpose: "Set up a repo: the rook/ folder and a starter GitHub workflow that runs `rook run . --ci --auto`. It never overwrites a file that exists unless you pass `rook init --force`." },
    { usage: "rook serve", purpose: "Start the Rook API server (the web app's backend)." },
    { usage: "rook login", purpose: "Sign in with Google (saved to ~/.rook/credentials.json, readable only by you)." },
    { usage: "rook logout", purpose: "Sign out: revoke the session on the server and delete the saved credentials on this machine." },
  ] satisfies DocCommand[],
} as const;
