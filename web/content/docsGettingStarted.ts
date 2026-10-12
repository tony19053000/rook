// /docs/getting-started (ROOK-055): the short guide. Sources: 06 §4 (install, the 6 steps, recorded vs live, the
// site's example runs), `rook --help` and `rook run --help` (src/rook/cli/main.py), src/rook/cli/runs.py
// (parse_repo, setup_values), src/rook/core/workspace.py (DEFAULT_ROOT, commit_fix_branch),
// src/rook/core/session.py (the SHIP files and "local branch … in the workspace"), 02 §7.8 (regression test).

import { lines, type DocGuide } from "./docsModel";
import { cta, INSTALL_COMMAND } from "./site";

export const gettingStartedGuide: DocGuide = {
  path: "/docs/getting-started",
  navLabel: "Getting started",
  title: "Getting started",
  description: "Try Rook in the browser with nothing to install, then install the CLI and run it on your own repo.",
  heading: "Getting started",
  lead: "Try Rook in the browser with nothing to install, then run the CLI on your own repo. This is the short version; each part links to the guide with the details.",
  summary: "Try the example on the site, install the CLI, run it on your repo, and find the results.",
  sections: [
    {
      id: "what-you-need",
      title: "What you need",
      blocks: [
        { kind: "p", text: "To try the example on this site: a browser. Nothing to install and no account." },
        { kind: "p", text: "To run Rook on your own repo, on your machine:" },
        {
          kind: "list",
          items: [
            "Python 3.12 or newer, and uv to install Rook.",
            "Docker, running. Rook starts your app in a Docker sandbox.",
            "git. Rook works on a copy of your repo and commits the fix to a branch.",
            "IBM Bob Shell with your own `BOB_API_KEY`, for live runs.",
          ],
        },
        { kind: "links", items: [{ label: "Supported environments and setup, in detail", href: "/docs/install" }] },
      ],
    },
    {
      id: "try-on-the-site",
      title: "Try the example on the site",
      blocks: [
        {
          kind: "list",
          ordered: true,
          items: [
            "Open Try Rook and pick one of the two example repos: shop-app (Node.js) or minishop (Python, Rook's own small test shop).",
            "Watch the run. It is labelled Recorded example run: Bob's answers are replayed from a saved real run, and the engine still runs live against the real app.",
            "Answer when Rook asks: which rules to approve, and whether to apply the fix.",
          ],
        },
        {
          kind: "p",
          text: "A recorded example run sends nothing to IBM Bob and needs no key. Guests get 3 runs a day. The site does not run your own repos: for those, use the CLI.",
        },
        { kind: "links", items: [{ label: cta.demo.label, href: cta.demo.href }] },
      ],
    },
    {
      id: "install",
      title: "Install the CLI",
      blocks: [
        { kind: "code", code: INSTALL_COMMAND, prompt: true },
        { kind: "p", text: "Rook is not on PyPI yet, so it installs from GitHub. Check that it is there:" },
        { kind: "code", code: "rook --version", prompt: true },
        {
          kind: "p",
          text: "For live runs, put your IBM Bob key in the `BOB_API_KEY` environment variable of the shell that runs Rook. The install guide shows how to keep it out of your shell history.",
        },
        { kind: "links", items: [{ label: "Install, upgrade, uninstall and IBM Bob setup", href: "/docs/install" }] },
      ],
    },
    {
      id: "first-run",
      title: "First run on your repo",
      blocks: [
        {
          kind: "p",
          text: "From your repo's folder, run `rook` to open the interactive session. Or name the repo with `rook run`: a local folder, or a GitHub owner/name.",
        },
        { kind: "code", code: lines("rook", "rook run ./my-app", "rook run owner/name") },
        {
          kind: "p",
          text: "A local folder is copied into a workspace under ~/.rook/workspaces/ and the original is never changed. A GitHub owner/name needs `rook login` and the Rook GitHub App on that repo first; the GitHub Action guide has the steps.",
        },
        {
          kind: "p",
          text: "If your app needs a value to start, such as an admin password, put it in an environment variable and pass the variable's name. The value is read from your environment, never from the command line.",
        },
        { kind: "code", code: "rook run ./my-app --setup ADMIN_PASSWORD", prompt: true },
        {
          kind: "p",
          text: "Rook asks before the steps that matter: approving the rules, applying a fix and opening a pull request. For a run with no questions, `rook run ./my-app --ci --auto` prints plain output, writes rook-report.json and rook-report.md, and exits 0 when every approved rule held, 1 when a rule is broken and 2 when the run did not finish.",
        },
      ],
    },
    {
      id: "what-you-see",
      title: "What you see at each step",
      blocks: [
        {
          kind: "terms",
          items: [
            {
              term: "1 · Understand",
              text: "The Scout, the Mechanic and the Mapper appear as characters while they read the repo, start the app in a Docker sandbox and map its HTTP API. If the app needs a setup value Rook was not given, it asks.",
            },
            {
              term: "2 · Rules",
              text: "The rules the Lawmaker proposed, each with its check and the Rule Critic's verdict. You approve all, none or some of them.",
            },
            {
              term: "3 · Search",
              text: "A progress row while the engine runs sequences of actions against your running app and checks every approved rule after every step.",
            },
            {
              term: "4 · Shrink and prove",
              text: "The failing sequence getting shorter, then the counterexample: the minimal steps, the values observed, and how many of the 10 replays reproduced it.",
            },
            {
              term: "5 · Diagnose and fix",
              text: "The Detective's file and line with its explanation. Rook asks before the Surgeon writes a fix, then shows the diff.",
            },
            {
              term: "6 · Verify and ship",
              text: "The four engine checks, each passed or failed, then the branch the fix was committed to, and the pull request for a GitHub repo.",
            },
          ],
        },
        {
          kind: "links",
          items: [
            { label: "The six steps in full", href: "/docs#how-it-works" },
            { label: "One recorded case, step by step", href: "/docs/counterexamples#refund-case" },
          ],
        },
      ],
    },
    {
      id: "where-results-land",
      title: "Where the results land",
      blocks: [
        {
          kind: "terms",
          items: [
            { term: "rook/rook.yaml", text: "The model of your app: actors, actions, state readers and the rules you approved." },
            { term: "rook/counterexamples/cx_001.json", text: "Each counterexample, with everything needed to replay it exactly." },
            {
              term: "A regression test",
              text: "A test in your project's own test framework, next to your existing tests, that fails on the bug and passes after the fix. If Rook cannot validate a native test, it falls back to a generated pytest file that replays the JSON.",
            },
            {
              term: "A rook/fix-* branch",
              text: "One commit with the fix, the regression test, rook/rook.yaml and the counterexample file. The branch is named after the counterexample, for example rook/fix-cx-001.",
            },
          ],
        },
        {
          kind: "note",
          title: "For a local folder, look in the workspace",
          text: "Rook never writes to the folder you pointed it at. For a local folder, these files and the rook/fix-* branch are in the run's workspace, ~/.rook/workspaces/<run-id>/, which is a git repository of its own; nothing is pushed anywhere. For a GitHub repo they reach you as a pull request.",
        },
        {
          kind: "links",
          items: [
            { label: "Rules and rook/rook.yaml", href: "/docs/rules" },
            { label: "Counterexamples, replays and verified fixes", href: "/docs/counterexamples" },
            { label: "The GitHub Action and pull requests", href: "/docs/github-action" },
            { label: "What is sent to IBM Bob", href: "/docs/data" },
          ],
        },
      ],
    },
  ],
};
