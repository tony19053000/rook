# Roook

**Roook finds the smallest sequence of actions that breaks a business rule in your backend, proves it on the real running app, and verifies the fix.** Early access, open source (MIT). Built on IBM Bob.

| | |
|---|---|
| Site and docs | <https://www.roook.dev> |
| Try it in the browser (no install, no account) | <https://www.roook.dev/app> |
| Getting started | <https://www.roook.dev/docs/getting-started> |

```
✗ RULE BROKEN   Total refunds on an order never exceed the amount paid

  1. admin: create_product(price=1, stock=1)
  2. customer: buy(quantity=1)
  3. customer: refund(amount=1)
  4. customer: refund(amount=1)

  paid 1    refunded_total 2    ✗
  Reproduced 10/10 on the real app
```

This is a recorded run on minishop, Roook's own small test shop. The site walks through it end to end, including the one-line fix and the four checks that verified it.

## The problem

Unit tests cover the scenarios you thought of. Costly bugs like double refunds, negative stock and permission bypasses come from **unexpected sequences of valid actions**. An AI reviewer that says "this might have a bug" is only guessing. Roook runs the failing sequence on your app and shows you the result.

## How it works

1. **Understand.** Bob agents read the repo, start the app in a Docker sandbox and turn its HTTP API into actions and state readers.
2. **Rules.** Bob proposes business rules with evidence from the code, a critic agent rejects weak ones, and **you approve** them. They are saved in `rook/rook.yaml`.
3. **Search.** The deterministic engine runs seeded sequences of valid actions against the **real running app** and checks every approved rule after every step with a safe expression evaluator (no `eval`).
4. **Shrink and prove.** A failing sequence is shrunk to a minimal one, replayed on the real app (10 times by default) and saved as a counterexample JSON file plus a regression test.
5. **Diagnose and fix.** Bob finds the root cause and, after you approve, writes the fix in a workspace copy. Reviewer agents check both.
6. **Verify and ship.** The fix counts only if four engine checks pass: the exact replay, your project's tests, the regression test and a fresh search with a new seed. Then it lands on a `rook/fix-*` branch.

Bob proposes and explains; the engine decides. No Bob output is ever executed as code, and only the engine marks a rule broken or a fix verified.

## Try it

- **In the browser:** open <https://www.roook.dev/app> and pick an example repo. These are recorded example runs: Bob's answers are replayed from a saved real run, and the engine runs live against the real app. Guests get 3 runs a day.
- **On your own repo:** use the CLI on your machine, below. The hosted site does not run your own repos: hosted runs of your own repos are turned off.

## Install

Needs Python 3.12+, Docker, git, and [IBM Bob Shell](https://bob.ibm.com/docs/shell) with your own `BOB_API_KEY` for live runs. Developed and tested on Linux. Not on PyPI yet (the PyPI package named `rook-cli` is a different project), so install from GitHub:

```bash
uv tool install git+https://github.com/tony19053000/rook
rook --version
```

```bash
rook                                    # interactive session
rook run ./my-app                       # a local folder (copied, never changed)
rook run ./my-app --ci --auto           # no questions; exit 1 if a rule breaks, 2 if the run did not finish
rook explain cx_001                     # a counterexample in plain words
rook replay cx_001 --base-url http://127.0.0.1:8000   # replay it on your running app
rook verify cx_001 --base-url http://127.0.0.1:8000   # exact replay + fresh search
rook init                               # add rook/ and a starter GitHub workflow
```

Roook never writes to the folder you point it at. For a local folder, `rook/rook.yaml`, `rook/counterexamples/cx_001.json`, the regression test and the `rook/fix-*` branch are in the run's workspace under `~/.rook/workspaces/`. For a GitHub repo (`rook login`, then `rook run owner/name`) the fix is pushed as a `rook/fix-*` branch and opened as a pull request, never pushed to your default branch.

Guides:

- [Getting started](https://www.roook.dev/docs/getting-started)
- [Install](https://www.roook.dev/docs/install): supported environments, IBM Bob setup, limitations, troubleshooting
- [Rules](https://www.roook.dev/docs/rules): the approval workflow and `rook/rook.yaml`
- [Counterexamples](https://www.roook.dev/docs/counterexamples): shrinking, replays and verified fixes
- [GitHub Action](https://www.roook.dev/docs/github-action)
- [Data and IBM Bob](https://www.roook.dev/docs/data): what is sent to IBM Bob, and when

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

Limitations, plainly: the action has not yet been run on a GitHub-hosted runner; live mode needs a Bob Shell package you provide (`bob-package`; Roook does not host one); replay mode only fits code that has not changed since it was recorded. Details and all inputs: the [GitHub Action guide](https://www.roook.dev/docs/github-action).

## How IBM Bob is used

- **13 Bob agents, each a Bob Shell custom mode:** a Coordinator and 12 specialists (Scout, Mechanic, Mapper, Lawmaker, Rule Critic, Test Designer, Strategist, Detective, Diagnosis Reviewer, Surgeon, Fix Reviewer, Guide). Every agent is read-only except the Mechanic (its own sandbox folder) and the Surgeon (only the approved files).
- Bob is the only AI in Roook. In a live run, repo content goes to IBM Bob as prompts; a recorded run sends nothing. See [Data and IBM Bob](https://www.roook.dev/docs/data).

## Where Roook is today

- Early access. No paid plans, no team accounts.
- HTTP APIs only: no libraries, pure frontends, mobile apps or ML notebooks.
- The hosted site offers recorded example runs of two example repos; it does not run your own repos.
- No third-party security audit. See [Security](https://www.roook.dev/security) for how code and data are handled and what is not yet true.

Roook started at the IBM Bob 2.0 Hackathon in September 2026.

## Security

- Secrets such as `BOB_API_KEY` are never committed and never logged; a redaction filter scrubs keys and tokens from events and logs.
- Your app runs in a Docker sandbox on your machine, and the engine sends HTTP only to that sandbox.
- Rules are checked by a safe expression evaluator. Bob output is never passed to `eval` or `exec`.
- Code edits happen only in a workspace copy, only by the Surgeon, and only after you approve.

Full model: [`docs/03_SECURITY_ACCESS.md`](docs/03_SECURITY_ACCESS.md).

## Repo layout

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
cd web && npm install && npm run test && npx tsc --noEmit
```

The contracts (event schema, `rook.yaml` schema and API routes) are in [`docs/02_ARCHITECTURE.md`](docs/02_ARCHITECTURE.md).

## Contact

Roook is an independent, founder-led startup, built and run by Aayush Kumar (Founder). Email <aayush@roook.dev>, or open an [issue](https://github.com/tony19053000/rook/issues) for bugs and feature requests. Website: <https://www.roook.dev>.

## License

MIT, see [`LICENSE`](LICENSE).
