<p align="center">
  <a href="https://www.roook.dev"><img src="web/app/icon.svg" width="72" height="72" alt="Roook logo"></a>
</p>

<h1 align="center">Roook</h1>

<p align="center">Find the smallest sequence that breaks your software, before your users do.</p>

<p align="center">
  <a href="https://www.roook.dev">Website</a> ·
  <a href="https://www.roook.dev/app">Try it in the browser</a> ·
  <a href="https://www.roook.dev/docs/getting-started">Docs</a> ·
  <a href="https://www.roook.dev/security">Security</a> ·
  <a href="https://www.roook.dev/roadmap">Roadmap</a> ·
  <a href="mailto:aayush@roook.dev">Contact</a>
</p>

<p align="center">
  <a href="https://github.com/tony19053000/rook/actions/workflows/ci.yml"><img src="https://github.com/tony19053000/rook/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT licence"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12 or newer">
  <img src="https://img.shields.io/badge/status-early%20access-orange.svg" alt="Status: early access">
</p>

---

**Roook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.** Early access, open source (MIT). Built on IBM Bob.

```
✗ RULE BROKEN   Total refunds on an order never exceed the amount paid

  1. admin: create_product(price=1, stock=1)
  2. customer: buy(quantity=1)
  3. customer: refund(amount=1)
  4. customer: refund(amount=1)

  paid 1    refunded_total 2    ✗
  Reproduced 10/10 on the real app
```

This is a recorded run on minishop, Roook's own small test shop. [The site](https://www.roook.dev) walks through it end to end, including the one-line fix and the four checks that verified it.

## Contents

- [Why Roook](#why-roook)
- [How it works](#how-it-works)
- [What Roook will not do](#what-roook-will-not-do)
- [Quick start](#quick-start)
- [Documentation](#documentation)
- [GitHub Action](#github-action)
- [How IBM Bob is used](#how-ibm-bob-is-used)
- [Status and limitations](#status-and-limitations)
- [Security](#security)
- [Project layout](#project-layout)
- [Development](#development)
- [Support and contact](#support-and-contact)
- [About](#about)
- [License](#license)

## Why Roook

Unit tests cover the scenarios you thought of. Costly bugs like double refunds, negative stock and permission bypasses come from **unexpected sequences of valid actions**: each request is fine on its own, and together they break a rule the business depends on.

An AI reviewer that says "this might have a bug" is only guessing. Roook runs the failing sequence on your app, shrinks it to the smallest one that still fails, and keeps it as a test. The report is a proof, not a prediction.

## How it works

| Step | What happens | Who does it |
|---|---|---|
| 1. **Understand** | Bob agents read the repo, start the app in a Docker sandbox and turn its HTTP API into actions and state readers. | IBM Bob |
| 2. **Rules** | Bob proposes business rules with evidence from the code and a critic agent rejects weak ones. The approved rules are saved in `rook/rook.yaml`. | IBM Bob, **you approve** |
| 3. **Search** | Seeded sequences of valid actions run against the **real running app**. Every approved rule is checked after every step with a safe expression evaluator (no `eval`). | Engine |
| 4. **Shrink and prove** | A failing sequence is shrunk to a minimal one, replayed on the real app (10 times by default) and saved as a counterexample JSON file plus a regression test. | Engine |
| 5. **Diagnose and fix** | Bob finds the root cause and writes the fix in a workspace copy. Reviewer agents check both. | IBM Bob, **you approve** |
| 6. **Verify and ship** | The fix counts only if four checks pass: the exact replay, your project's tests, the regression test and a fresh search with a new seed. Then it lands on a `rook/fix-*` branch. | Engine |

Bob proposes and explains; the engine decides. No Bob output is ever executed as code, and only the deterministic engine marks a rule broken or a fix verified.

## What Roook will not do

Each of these is enforced in code, not left to a prompt.

- **Let an AI decide pass or fail.** Only the deterministic engine marks a rule broken or a fix verified.
- **Execute AI-generated code.** Rules go through a safe expression evaluator and actions are declarative HTTP templates.
- **Change your code without your approval.** Only the Surgeon agent edits, only in a workspace copy, and only in the approved files.
- **Push to your default branch.** A fix goes to a `rook/fix-*` branch: a pull request for a GitHub repo, a local branch for a folder.
- **Call anything but your sandboxed app.** The engine sends requests only to the sandbox's host and port.
- **Hand your secrets to the app or the logs.** The sandbox gets none of Roook's environment, and a redaction filter scrubs keys and tokens from events and logs.

## Quick start

### Try it in the browser

Open <https://www.roook.dev/app> and pick an example repo. No install and no account are needed.

These are recorded example runs: Bob's answers are replayed from a saved real run, and the engine runs live against the real app. Guests get 3 runs a day. The hosted site does not run your own repos: hosted runs of your own repos are turned off. Use the CLI for those.

### Install the CLI

Requirements:

- Python 3.12 or newer
- Docker
- git
- [IBM Bob Shell](https://bob.ibm.com/docs/shell) with your own `BOB_API_KEY`, for live runs

Roook is developed and tested on Linux. Not on PyPI yet (the PyPI package named `rook-cli` is a different project), so install from GitHub:

```bash
uv tool install git+https://github.com/tony19053000/rook
rook --version
```

### Run it

```bash
rook                                    # interactive session
rook run ./my-app                       # a local folder (copied, never changed)
rook run ./my-app --ci --auto           # no questions; exit 1 if a rule breaks, 2 if the run did not finish
rook explain cx_001                     # a counterexample in plain words
rook replay cx_001 --base-url http://127.0.0.1:8000   # replay it on your running app
rook verify cx_001 --base-url http://127.0.0.1:8000   # exact replay + fresh search
rook init                               # add rook/ and a starter GitHub workflow
```

Roook never writes to the folder you point it at. For a local folder, `rook/rook.yaml`, `rook/counterexamples/cx_001.json`, the regression test and the `rook/fix-*` branch are in the run's workspace under `~/.rook/workspaces/`.

For a GitHub repo (`rook login`, then `rook run owner/name`), the fix is pushed as a `rook/fix-*` branch and opened as a pull request. It is never pushed to your default branch.

## Documentation

| Guide | What it covers |
|---|---|
| [Getting started](https://www.roook.dev/docs/getting-started) | Install, your first run, and what you see |
| [Install](https://www.roook.dev/docs/install) | Supported environments, IBM Bob setup, limitations, troubleshooting |
| [Rules](https://www.roook.dev/docs/rules) | The approval workflow and `rook/rook.yaml` |
| [Counterexamples](https://www.roook.dev/docs/counterexamples) | Shrinking, replays and verified fixes |
| [GitHub Action](https://www.roook.dev/docs/github-action) | The action, its inputs and the pull-request workflow |
| [Data and IBM Bob](https://www.roook.dev/docs/data) | What is sent to IBM Bob, and when |

## GitHub Action

[`action.yml`](action.yml) runs `rook run --ci --auto` on a pull request and keeps one `rook-report.md` comment on it up to date. The job fails if an approved rule breaks (exit 1) or the run does not finish (exit 2).

```yaml
name: rook
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
      - uses: tony19053000/rook@<full-commit-sha>
        with:
          bob-mode: live
          bob-api-key: ${{ secrets.BOB_API_KEY }}
          bob-package: <url-or-path-of-the-bob-shell-package>
```

Use `pull_request` and **never** `pull_request_target`: with `pull_request_target`, a fork's code would run with your secrets.

Limitations, plainly:

- The action has not yet been run on a GitHub-hosted runner.
- Live mode needs a Bob Shell package you provide (`bob-package`). Roook does not host one.
- Replay mode only fits code that has not changed since it was recorded.

Details and all inputs are in the [GitHub Action guide](https://www.roook.dev/docs/github-action).

## How IBM Bob is used

- **13 Bob agents, each a Bob Shell custom mode:** a Coordinator and 12 specialists (Scout, Mechanic, Mapper, Lawmaker, Rule Critic, Test Designer, Strategist, Detective, Diagnosis Reviewer, Surgeon, Fix Reviewer, Guide).
- **Read-only by default.** Every agent is read-only except the Mechanic (its own sandbox folder) and the Surgeon (only the approved files).
- **Bob is the only AI in Roook.** In a live run, repo content goes to IBM Bob as prompts; a recorded run sends nothing. See [Data and IBM Bob](https://www.roook.dev/docs/data).

## Status and limitations

Roook is in early access. This is what that means today:

- No paid plans, no billing and no team accounts.
- HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.
- The hosted site offers recorded example runs of two example repos. It does not run your own repos.
- The CLI is developed and tested on Linux only.
- No third-party security audit.

The [roadmap](https://www.roook.dev/roadmap) lists what is shipped, what is limited and what is planned.

## Security

- Secrets such as `BOB_API_KEY` are never committed and never logged; a redaction filter scrubs keys and tokens from events and logs.
- Your app runs in a Docker sandbox on your machine, and the engine sends HTTP only to that sandbox.
- Rules are checked by a safe expression evaluator. Bob output is never passed to `eval` or `exec`.
- Code edits happen only in a workspace copy, only by the Surgeon, and only after you approve.

The [Security page](https://www.roook.dev/security) explains how code and data are handled and what is not yet true. The full model is in [`docs/03_SECURITY_ACCESS.md`](docs/03_SECURITY_ACCESS.md).

To report a vulnerability, email <aayush@roook.dev> instead of opening a public issue.

## Project layout

```
src/rook/
  agents/    Bob agents, prompts, custom-mode registry, record/replay
  engine/    runner, judge, shrinker, replayer, verifier (deterministic)
  model/     rook.yaml schema + safe expression evaluator
  sandbox/   sandboxes for the target app
  cli/       `rook` CLI (Typer + Textual)
  server/    FastAPI API (runs, SSE events, auth, limits)
  github/    GitHub App, PR comment, fix PRs
  store/ export/ auth/ core/
web/         Next.js site and web app
tests/       pytest (unit + marked docker/bob integration)
deploy/      server deployment
docs/        PRD, architecture and contracts, security, UI and site specs
action.yml   GitHub Action
```

## Development

```bash
uv sync                    # Python deps
uv run pytest -q           # tests (docker/bob-marked tests are skipped by default)
uv run rook --help
cd web && npm install && npm run test && npx tsc --noEmit && npm run lint
```

The contracts (event schema, `rook.yaml` schema and API routes) are in [`docs/02_ARCHITECTURE.md`](docs/02_ARCHITECTURE.md). For a code change, open an issue first to describe it, and run the checks above before sending a pull request.

## Support and contact

| For | Where |
|---|---|
| Bugs and feature requests | [GitHub Issues](https://github.com/tony19053000/rook/issues) |
| Questions, early access and privacy requests | <aayush@roook.dev> |
| Website and docs | <https://www.roook.dev> |

Please never send secrets such as API keys or tokens, by email or in an issue.

## About

Roook is an independent, founder-led startup, built and run by Aayush Kumar (Founder) and based in India. Roook started at the IBM Bob 2.0 Hackathon in September 2026.

## License

MIT. See [`LICENSE`](LICENSE).
