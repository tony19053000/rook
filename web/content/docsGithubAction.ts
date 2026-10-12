// /docs/github-action (ROOK-055): the GitHub Action and how a fix becomes a pull request. Sources: action.yml
// (inputs, outputs, steps; components/site/docs/docs.test.tsx checks the lists below against it),
// src/rook/cli/ci.py (exit codes, the reports, what --ci answers), src/rook/github/pr_comment.py (one comment,
// the marker, bot-only update), src/rook/cli/scaffold.py (`rook init`), src/rook/cli/runs.py build_session and
// src/rook/github/pr.py (the fix branch and the pull request), src/rook/cli/github.py, 03 §6 (GitHub App
// permissions, tokens), src/rook/agents/recorder.py and 02 §5.1 (recordings are keyed on the prompt), STATUS.md
// ROOK-032 ("never run on a real runner"; no hosted Bob package) and U15 (the live pull-request test is open).

import { lines, type DocGuide } from "./docsModel";

/** The workflow shown here and in the README (one text, checked by a test). */
export const actionWorkflow = lines(
  "name: rook",
  "on:",
  "  pull_request:",
  "permissions:",
  "  contents: read",
  "  pull-requests: write",
  "jobs:",
  "  rook:",
  "    runs-on: ubuntu-latest",
  "    steps:",
  "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
  "        with:",
  "          persist-credentials: false",
  "      - uses: tony19053000/rook@<full-commit-sha>",
  "        with:",
  "          bob-mode: live",
  "          bob-api-key: ${{ secrets.BOB_API_KEY }}",
  "          bob-package: <url-or-path-of-the-bob-shell-package>",
);

/** action.yml `inputs`, in file order, with their defaults. */
export const actionInputs = [
  { term: "repo-path", text: "The folder to check. Rook copies it and never changes it. Default: the repo root." },
  { term: "request", text: "What to look for. Default: find bugs in my app." },
  {
    term: "bob-mode",
    text: "replay (the default): recorded Bob answers from the recordings input. live: real Bob calls, which need bob-api-key and bob-package. Live falls back to replay when the key is empty, as on a pull request from a fork.",
  },
  { term: "bob-api-key", text: "Your IBM Bob key. Pass the repository secret, never the key itself." },
  { term: "bob-package", text: "Live mode: the Bob Shell package for npm to install, as a URL or a path." },
  { term: "recordings", text: "Replay mode: a folder of Bob recordings, copied to ~/.rook/recordings on the runner." },
  { term: "auto", text: "true (the default) adds `--auto`, so Rook answers its own questions. false runs `rook run --ci` alone." },
  { term: "budget", text: "The Bob coin budget for the run. Default: 1.5." },
  { term: "seconds", text: "The search budget in seconds. Default: 120." },
  { term: "setup", text: "Names of environment variables your app needs, separated by spaces. Each is passed to Rook as a setup value." },
  { term: "report-dir", text: "Where rook-report.json and rook-report.md are written. Default: rook-report." },
  { term: "comment", text: "true (the default) posts or updates one Rook comment on the pull request." },
  { term: "github-token", text: "The token used for the comment. Default: the workflow's own token, which needs pull-requests: write." },
] as const;

/** action.yml `outputs`. */
export const actionOutputs = [
  { term: "exit-code", text: "Rook's exit code: 0, 1 or 2, as below." },
  { term: "report", text: "The path of rook-report.md." },
  { term: "bob-mode", text: "The Bob mode actually used: live or replay." },
] as const;

export const githubActionGuide: DocGuide = {
  path: "/docs/github-action",
  navLabel: "GitHub Action",
  title: "GitHub Action and pull requests",
  description: "What Rook's GitHub Action runs on a pull request, its inputs, exit codes and limitations, and how a verified fix reaches you as a pull request.",
  heading: "GitHub Action and pull requests",
  lead: "Two separate things live here. The action checks a pull request and comments what it found. The pull-request workflow is how a verified fix from the CLI reaches your repo for review.",
  summary: "What the action runs, its inputs, exit codes and limitations, and how a fix becomes a pull request.",
  sections: [
    {
      id: "what-it-does",
      title: "What the action does",
      blocks: [
        { kind: "p", text: "The action is the file action.yml at the root of the Rook repo. On each run it:" },
        {
          kind: "list",
          ordered: true,
          items: [
            "Chooses the Bob mode. It is replay unless you ask for live, and live turns into replay when no key is present.",
            "Installs uv, then Rook itself from the action's own checkout, with Python 3.12.",
            "In live mode, sets up Node 24 and installs Bob Shell from the package you named. In replay mode, copies your recordings into place.",
            "Runs `rook run --ci --auto` on your checkout, with your request and budgets. Rook starts your app in Docker on the runner.",
            "Adds rook-report.md to the job summary, and posts it as one comment on the pull request.",
            "Fails the job when an approved rule is broken or the run did not finish.",
          ],
        },
        {
          kind: "p",
          text: "The action reports; it does not open fix pull requests. It runs on a local checkout, so even with auto on, a fix stays on a branch inside the runner's workspace, which is thrown away with the runner.",
        },
      ],
    },
    {
      id: "workflow",
      title: "A workflow",
      blocks: [
        { kind: "code", label: ".github/workflows/rook.yml", code: actionWorkflow },
        {
          kind: "list",
          items: [
            "Replace <full-commit-sha> with the full SHA of the Rook commit you want, so the action cannot change under you. Rook has no release tags yet, so there is no version tag to use instead.",
            "Replace the bob-package value with a Bob Shell package you are entitled to use, as a URL or a path npm can install. Rook does not host one. Without it, live mode stops with an error.",
            "Store your IBM Bob key as the repository secret BOB_API_KEY.",
          ],
        },
        {
          kind: "note",
          title: "Use pull_request, never pull_request_target",
          text: "With pull_request_target, a fork's code would run with your secrets. Pull requests from forks get no secrets, so the action falls back to recorded Bob answers. The key is masked in the logs and is given only to the step that runs Rook, and only in live mode.",
        },
      ],
    },
    {
      id: "inputs",
      title: "Inputs and outputs",
      blocks: [
        { kind: "terms", items: [...actionInputs] },
        { kind: "p", text: "Outputs:" },
        { kind: "terms", items: [...actionOutputs] },
      ],
    },
    {
      id: "exit-codes",
      title: "Exit codes",
      blocks: [
        {
          kind: "terms",
          items: [
            { term: "0", text: "Every approved rule held. The job passes." },
            { term: "1", text: "An approved rule is broken: the engine found a counterexample. The job fails." },
            { term: "2", text: "The run did not finish: it failed or was stopped before it could say. The job fails. This is not a verdict on your code." },
          ],
        },
        { kind: "p", text: "`rook run --ci` uses the same codes when you run it yourself." },
      ],
    },
    {
      id: "comment",
      title: "The pull request comment",
      blocks: [
        {
          kind: "p",
          text: "Rook keeps one comment on the pull request and updates it on every run, instead of adding a new one each time. It holds rook-report.md: each approved rule and its result, and for a broken rule the minimal steps, the replay count, the observed values and the expected check.",
        },
        {
          kind: "list",
          items: [
            "The workflow needs the pull-requests: write permission for the comment. Set comment to false to skip it; the report is still in the job summary.",
            "Text that comes from your app or from Bob is put in code spans in the report, so it cannot mention people or inject formatting.",
            "Only a comment written by a bot is updated, so nobody can redirect the update by copying Rook's marker into their own comment.",
          ],
        },
      ],
    },
    {
      id: "limitations",
      title: "Limitations, plainly",
      blocks: [
        {
          kind: "list",
          items: [
            "The action has not yet been run on a GitHub-hosted runner from start to finish. Its parts are covered by automated tests and a dry run of the comment step. Treat it as untested until you have seen it pass in your repo.",
            "Live mode needs a Bob Shell package you provide. Rook does not host or redistribute Bob Shell.",
            "Replay mode only fits code that has not changed. A recording is matched by the exact prompt, and the prompts include a digest of your files. A pull request that changes the code misses its recordings, and the run does not finish (exit code 2). For real pull requests, use live mode.",
            "The runner must have Docker. GitHub's ubuntu-latest runners do.",
            "`rook init` writes a different, simpler starter workflow that installs Rook with uv and runs `rook run . --ci --auto`. It does not install Bob Shell and does not use this action, so on a GitHub-hosted runner it needs a Bob Shell install step added before it can make live runs.",
          ],
        },
      ],
    },
    {
      id: "fix-pull-requests",
      title: "How a fix becomes a pull request",
      blocks: [
        { kind: "p", text: "Fix pull requests come from the CLI on your machine, for a repo on GitHub:" },
        {
          kind: "list",
          ordered: true,
          items: [
            "In the Rook web app, sign in and connect GitHub. This installs the Rook GitHub App on the repos you choose. It asks for Contents (read and write), Pull requests (read and write) and Metadata (read).",
            "On your machine, sign in with `rook login`.",
            "Run `rook run owner/name`. The CLI asks the Rook server for a short-lived token for that one repo, clones the repo into a workspace, and does everything else locally: your Docker, your IBM Bob key.",
            "When a fix is verified and you say yes, Rook pushes a rook/fix-* branch and opens a pull request.",
          ],
        },
        {
          kind: "p",
          text: "The pull request's commit holds the fix, the regression test, rook/rook.yaml and the counterexample file. Its description names the rule, the size of the counterexample and its replay count, the regression test and the verification result, and gives the command to replay it. Rook never pushes to your default branch and never force-pushes.",
        },
        {
          kind: "note",
          title: "Not yet proven against GitHub itself",
          text: "This path is covered by automated tests against a stand-in for the GitHub API. It has not yet been run from start to finish against GitHub. If it fails for you, the fix is still on its branch in the workspace on your machine.",
        },
        {
          kind: "terms",
          items: [
            {
              term: "A local folder",
              text: "No GitHub involved. The verified fix is committed to a rook/fix-* branch in the run's workspace, ~/.rook/workspaces/<run-id>/, and nothing is pushed. Read it there with git, and apply it to your repo yourself.",
            },
            {
              term: "The hosted site",
              text: "Hosted runs of your own repos are turned off. Signed-in users can connect GitHub and see their repos, and the site shows the CLI command to run a repo on their own machine.",
            },
          ],
        },
        { kind: "links", items: [{ label: "GitHub App permissions and tokens", href: "/docs/data#github" }] },
      ],
    },
  ],
};
