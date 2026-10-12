// /docs/data (ROOK-055): IBM Bob credentials and data flow. Sources: 06 §4 ("Recorded vs live", "Data the app
// actually processes", deletion and retention), src/rook/agents/bob.py (CHILD_ENV_ALLOWLIST, the key in the child
// env, register_secret, the record mode), src/rook/agents/understand.py (workspace_digest, MANIFESTS, mapper_files,
// FILE_MAX_CHARS, FILES_MAX_TOTAL, _tail), src/rook/agents/diagnose.py (RELATED_MAX_FILES, the
// evidence bundle), src/rook/agents/volatile.py (masking), src/rook/core/events.py (the redaction patterns),
// src/rook/core/workspace.py (COPY_IGNORE), src/rook/agents/registry.py and 03 §4 (read-only tool groups, no
// command, browser or MCP tools), 03 §2, §6 and §10, action.yml (the key in the action).

import type { DocGuide } from "./docsModel";
import { CONTACT_EMAIL } from "./site";

export const dataGuide: DocGuide = {
  path: "/docs/data",
  navLabel: "Data and IBM Bob",
  title: "Data and IBM Bob",
  description: "When Rook sends repo content to IBM Bob, what is sent and what is not, where your IBM Bob key lives, the GitHub App's permissions, and what the hosted site keeps.",
  heading: "Data and IBM Bob",
  lead: "What leaves your machine, when, and where your IBM Bob key lives. The short answer: the examples on this site send nothing to IBM Bob, and a live run on your machine sends parts of your repo to IBM Bob as prompts.",
  summary: "When repo content goes to IBM Bob, what is sent, where your key lives, and what the hosted site keeps.",
  sections: [
    {
      id: "summary",
      title: "The short version",
      blocks: [
        {
          kind: "list",
          items: [
            "A Recorded example run on this site sends nothing to IBM Bob. Bob's answers are replayed from a saved real run.",
            "A Live run, with the CLI on your machine and your own key, sends repo content and run data to IBM Bob as prompts.",
            "Your IBM Bob key stays on your machine. The hosted site never asks for it.",
            "The engine sends HTTP requests only to your sandboxed app, never anywhere else.",
          ],
        },
      ],
    },
    {
      id: "when",
      title: "When repo content goes to IBM Bob",
      blocks: [
        {
          kind: "p",
          text: "Only in a live run, and only when Rook calls a Bob agent: to understand the repo, propose and review rules, design scenarios, diagnose a counterexample, write and review a fix, or answer a question you ask the Guide. Each call starts IBM Bob Shell on your machine with a prompt Rook built.",
        },
        {
          kind: "list",
          items: [
            "The engine's work never calls Bob: the search, the shrinking, the replays and the four verification checks are plain code talking to your app.",
            "`rook replay`, `rook verify` and `rook explain` never call Bob.",
            "In a recorded run no Bob process is started at all. Every recorded run is labelled Recorded example run, and every run with real Bob calls is labelled Live run.",
          ],
        },
        {
          kind: "p",
          text: "Rook hands the prompt to IBM's software and service. What IBM does with it is governed by your agreement with IBM, not by Rook.",
        },
      ],
    },
    {
      id: "what-is-sent",
      title: "What is sent in a live run",
      blocks: [
        {
          kind: "terms",
          items: [
            {
              term: "A listing of the repo",
              text: "The path, size and content hash of up to 400 files, so the Scout knows what exists.",
            },
            {
              term: "Files Rook picks",
              text: "Build and manifest files at the repo root (such as Dockerfile, compose files, requirements.txt, pyproject.toml, package.json, go.mod, .env.example and README.md), the route and model files the Scout named, and up to 4 source files related to a broken rule. Each file is cut at 20,000 characters and one prompt carries at most 120,000 characters of files.",
            },
            {
              term: "Files Bob opens itself",
              text: "Bob's agents have a read tool over the run's workspace copy of your repo, so treat every file in that copy as readable in a live run.",
            },
            {
              term: "Run data",
              text: "The model (actions, state readers, rules), a counterexample's steps and observed values, your app's HTTP responses and state during a replay, and the tail of your app's logs.",
            },
            { term: "What you type", text: "Your request for the run, and any question you ask the Guide." },
          ],
        },
        {
          kind: "p",
          text: "The workspace copy leaves out .git, .venv, venv, node_modules and tool caches. Everything else in the folder is copied, tracked by git or not.",
        },
        {
          kind: "note",
          title: "Rook does not scan your files for secrets",
          text: "Source files go to Bob as they are. A secret that sits in the repo, or in an untracked file such as .env inside a local folder you run Rook on, is in the workspace copy and can reach IBM Bob. Keep secrets out of the folder, or run Rook on a clean clone.",
        },
      ],
    },
    {
      id: "what-is-not-sent",
      title: "What is not sent",
      blocks: [
        {
          kind: "list",
          items: [
            "Your shell's environment. The Bob process gets only a short allowlist of variables (PATH, HOME, locale and temp-folder settings) plus `BOB_API_KEY`. Nothing else from your environment reaches it.",
            "Your key inside a prompt. The key is how Bob Shell signs in to IBM; Rook never writes it into a prompt, a command-line argument, an event or a log.",
            "Anything outside the workspace copy. Bob runs in the copy, links that point outside it are removed when the copy is made, and the agents have no command, browser or MCP tools.",
            "Tokens and passing values in your app's output. Before app data and logs go into a prompt, Rook replaces tokens, credentials, timestamps and random ids with labels. Log text also goes through the redaction filter, which removes known secret values, PEM key blocks, bearer tokens, IBM Bob keys, GitHub tokens and JWTs.",
            "Your app's database or files in the sandbox. Bob sees only what your API returned and what your app logged.",
          ],
        },
        {
          kind: "p",
          text: "The same redaction filter cleans every event and log line Rook stores or shows, so a key that appears in output is replaced before it is saved.",
        },
      ],
    },
    {
      id: "key",
      title: "Where your IBM Bob key lives",
      blocks: [
        {
          kind: "list",
          items: [
            "On your machine, in the `BOB_API_KEY` environment variable of the shell that runs Rook. The install guide suggests a file only you can read.",
            "In the Bob Shell process Rook starts, through its environment only.",
            "In GitHub Actions, in a repository secret you create. The action masks it and gives it only to the step that runs Rook, and only in live mode.",
            "Never on the hosted site. The site's example runs use recorded answers, and no page or form asks for your key. If something claiming to be Rook asks for it in a browser, do not enter it.",
          ],
        },
        { kind: "links", items: [{ label: "Setting up the key", href: "/docs/install#ibm-bob" }] },
      ],
    },
    {
      id: "on-your-machine",
      title: "What stays on your machine",
      blocks: [
        {
          kind: "terms",
          items: [
            { term: "~/.rook/workspaces/", text: "The copy of your repo each run worked on, with the model, counterexamples, tests and fix branches. Rook does not delete these; remove them when you no longer need them." },
            {
              term: "~/.rook/recordings/",
              text: "Bob's saved answers, only if you turn recording on by setting ROOK_BOB_MODE to record. Recordings can contain parts of your repo, so keep them private.",
            },
            { term: "~/.rook/credentials.json", text: "Your Rook sign-in, only if you ran `rook login`, readable only by you. `rook logout` revokes the session and deletes the file." },
          ],
        },
      ],
    },
    {
      id: "github",
      title: "GitHub App permissions",
      blocks: [
        { kind: "p", text: "Only if you connect GitHub. The Rook GitHub App asks for the least it needs to clone a repo and open a pull request:" },
        {
          kind: "list",
          items: ["Contents: read and write.", "Pull requests: read and write.", "Metadata: read."],
        },
        {
          kind: "list",
          items: [
            "The Rook server keeps your installation id. The list of your repos is read from GitHub when needed.",
            "Tokens are short-lived installation tokens, made for one repo at a time, kept in memory and never written to disk, logs or events.",
            "The App's private key is only on the Rook server. Webhooks from GitHub are checked with a signature before they are read.",
            "Rook never pushes to your default branch: a fix goes to a rook/fix-* branch and a pull request.",
          ],
        },
      ],
    },
    {
      id: "hosted",
      title: "What the hosted site keeps, and deleting it",
      blocks: [
        {
          kind: "list",
          items: [
            "For each run: who owns it (your account id, or a guest cookie id), the repo, the status, times and Bob coins, its event log with secrets redacted (this includes the request text you typed), and its counterexamples.",
            "If you link GitHub: your account id, email and installation id.",
            "For guests: a daily run count, kept by guest cookie id and by client IP address.",
            "No analytics, ads or tracking scripts, on the site or in the app.",
          ],
        },
        {
          kind: "list",
          items: [
            "Runs older than 30 days are deleted automatically, with their events and counterexamples. Guest run counts older than 2 days are deleted too.",
            "You can delete a run yourself: open it in the web app and use Delete run. Its events and counterexamples go with it.",
            "Signed in, you can delete all your Rook server data, your runs and your GitHub link, with Delete my data in the account menu. You are then signed out.",
            "Your sign-in account itself is held by Supabase, the sign-in service. The Rook server cannot delete it, so it is deleted on request by email.",
          ],
        },
        { kind: "email", label: `Email ${CONTACT_EMAIL}`, subject: "Rook: privacy request" },
        {
          kind: "links",
          items: [
            { label: "Security: how data and code are handled", href: "/security" },
            { label: "Privacy", href: "/privacy" },
          ],
        },
      ],
    },
  ],
};
