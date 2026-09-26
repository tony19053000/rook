# CLAUDE.md: Rook project rules

These rules are **compulsory** for every Claude Code session on this repo, on either account.

## 0. Start of every session (in this order)

1. Read `HANDOFF.md`. It says exactly where the last session stopped.
2. Read `STATUS.md`, the live tracker.
3. Read the doc(s) relevant to your ticket:
   - `docs/01_PRD.md`: what we build and why
   - `docs/02_ARCHITECTURE.md`: how it's built, the contracts, and the folder layout
   - `docs/03_SECURITY_ACCESS.md`: security rules (never skip)
   - `docs/04_FRONTEND_SPEC.md`: CLI and web UI spec
   - `docs/05_FEATURE_TICKETS.md`: the ticket list, acceptance criteria and roadmap
4. Continue from **"Next session starts here"** in `HANDOFF.md`.

## 1. Context

- Product: **Rook**, CLI command `rook`. It was called "Counterexample" earlier; the mockups in `docs/mockups/` still use that name.
- Hackathon: IBM Bob 2.0 Hackathon (lablab.ai). **Deadline: 27 Sep 2026, 15:00 UTC (20:30 IST).**
- Submission: a working URL, an MP4 video of 5 minutes or less, a PDF deck, and a public GitHub repo. Bob IDE use is mandatory.
- There is one human (the user) with two Claude Code accounts, used **one after the other**. When one hits its limit, the other continues from `HANDOFF.md`.

## 2. How work is done: the ticket loop

The main session is the **orchestrator**. It never writes large features itself; it drives two sub-agents from `.claude/agents/`:

| Sub-agent | File | Job |
|---|---|---|
| **CODER** | `.claude/agents/coder.md` | Implements exactly one ticket, with tests |
| **REVIEWER / TESTER** | `.claude/agents/reviewer.md` | Independently validates it: runs the tests, checks acceptance criteria, security and these rules. Gives a PASS or FAIL verdict. It does not edit code. |

For each ticket:
1. Pick the next ticket from `STATUS.md` (respect its dependencies). Mark it `IN PROGRESS` in `STATUS.md`.
2. Send it to **CODER** with the ticket ID, its acceptance criteria and the relevant doc sections.
3. Send CODER's report to **REVIEWER**.
4. If the verdict is **FAIL**, send the findings back to CODER. After 3 FAIL rounds, stop, mark the ticket `BLOCKED` with the reason, and move on.
5. If the verdict is **PASS**, commit (one ticket per commit, message `ROOK-XXX: <title>`), mark the ticket `DONE` in `STATUS.md`, **update the progress bars** at the top of `STATUS.md` (overall, time left, milestone), and add one line to the `HANDOFF.md` log.
6. Update `HANDOFF.md` "Next session starts here" **after every ticket**, not just at the end. A session can end without warning.

Small doc fixes and status updates can be done directly without sub-agents.

## 2a. When the user says "update handoff"

This usually means the account is near its usage limit, so do it **immediately and quickly**:
1. Stop starting new work. Don't launch new sub-agents.
2. Check the real state: `git status --short` and `git log --oneline | head -5`.
3. Update `HANDOFF.md` → "Next session starts here":
   - the time (IST) and which account stopped
   - which tickets are **DONE and committed**
   - which work is **uncommitted** (ticket, its files, and whether it's coded, in review or partial), and exactly what to do with each
   - the next tickets in order
   - any lessons or gotchas from this session
   Add a line to the session log.
4. Update `STATUS.md`: ticket statuses, progress bars and "Last updated".
5. Commit **only** the docs (`HANDOFF.md`, `STATUS.md`, other docs). Never commit unreviewed ticket code. Then push.
6. Reply to the user with:
   - a 3–5 line summary of where we stopped
   - a warning to close this session before starting the other account, if background agents may still be writing files
   - a **ready-to-paste prompt for the other account** in a code block, based on the "Goal prompt" template in `HANDOFF.md`, filled in with the current state and the exact next steps

## 3. Hard rules

1. **Proof over prediction.** Only the engine (deterministic code) decides whether a rule is broken or a fix is verified. An LLM never decides pass or fail.
2. **Bob is the only AI.** All AI reasoning goes through IBM Bob (`bob run`). No Gemini or OpenAI.
3. **Never commit secrets.** That means `BOB_API_KEY`, GitHub App private keys, Supabase keys and tokens. Secrets live only in `~/.bob-key.env`, `.env` (gitignored) or host secret settings. The reviewer checks every diff for them.
4. **Never execute Bob-generated code** directly with `eval` or `exec`. Rules are checked with the safe expression evaluator (see `02_ARCHITECTURE.md`, section 6).
5. **Only the Surgeon agent edits target-app code**, only in the workspace copy, and only after the user approves.
6. **Contracts are law.** The event schema, the `rook.yaml` model schema and the API routes in `02_ARCHITECTURE.md` are shared by the CLI, the server and the web. Change them only by updating the doc first, in the same commit.
7. **Don't cut scope silently.** If something can't be done, mark it `BLOCKED` in `STATUS.md` with the reason and tell the user.
8. **Tests with every ticket.** Python uses `pytest`; web uses `vitest` and `tsc --noEmit`. A ticket isn't done if its tests don't pass.
9. Keep the code readable: typed Python (pydantic v2, type hints), small modules, no dead code, and comments only where the logic isn't obvious.

## 4. Environment facts (verified 26 Sep)

- Python 3.12 and `uv` (use `uv` for envs and deps), Node 22 (default) and Node 24 (for Bob), Docker 29 (daemon running), `gh` logged in as `tony19053000`.
- **Bob Shell 2.0.5** lives at `~/.nvm/versions/node/v24.21.0/bin/bob`. Put that folder on `PATH` before calling it.
- Bob needs `BOB_API_KEY`: run `source ~/.bob-key.env`. Never print it.
- **Always call `bob run` with stdin closed** (`< /dev/null` or `stdin=subprocess.DEVNULL`), or it hangs forever. Also pass `--trust --accept-license`.
- **Run `bob` with cwd = the workspace.** `--trust` only trusts the cwd, and custom modes load only from a trusted folder; otherwise you get `Mode with id … not found`.
- A small call costs about 0.023 Bobcoins. The budget is 40 coins in total.
- Custom modes are read from `<workspace>/.bob/custom_modes.yaml` and selected with `--mode <slug>`.

## 5. Commands

```bash
uv sync                      # install Python deps
uv run pytest -q             # Python tests
uv run rook --help           # CLI
cd web && npm install && npm run test && npx tsc --noEmit   # web
```

## 6. Commits and GitHub

- Repo: `github.com/tony19053000/rook` (public).
- Use one commit per ticket, and end each commit message with the attribution line from the system reminder.
- Push after every 2–3 tickets so work is never lost between accounts.
