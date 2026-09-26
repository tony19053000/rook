# 05 · Feature Tickets & Roadmap: Rook

The ticket status lives in **`STATUS.md`**; this file holds the scope and acceptance criteria (AC).
Each ticket goes through CODER → REVIEWER (see `CLAUDE.md`, section 2). `P0` is the critical path for the demo. `P1` is needed for the full product we promised. Nothing is dropped silently.

**Deadline: 27 Sep 2026, 20:30 IST (15:00 UTC). Feature freeze: 27 Sep, 15:30 IST.**

---

## Roadmap (IST)

| Block | When | Milestones |
|---|---|---|
| B0 | 26 Sep 13:00–15:00 | M0 docs, repo, sub-agents ✅ |
| B1 | 26 Sep 15:00–20:00 | M1 foundation, M2 engine on the fixture app (**the heart; it must be solid**) |
| B2 | 26 Sep 20:00–27 Sep 01:00 | M3 sandbox, M4 Bob agents, M5 session/conductor |
| B3 | 27 Sep 01:00–06:00 | M6 CLI (hero) |
| B4 | 27 Sep 06:00–10:00 | M7 server, M9 web |
| B5 | 27 Sep 10:00–13:00 | M8 auth + GitHub, M10 deploy |
| B6 | 27 Sep 13:00–15:30 | Demo apps integration, recordings, bug bash → **FREEZE 15:30** |
| B7 | 27 Sep 15:30–19:30 | Video, deck, README polish, submit (target 19:30, a 1 h buffer before 20:30) |

The user works in parallel on the **U-tasks** at the bottom (accounts, demo apps via Antigravity, Bob IDE clips, video, deck).

---

## M1 · Foundation

**ROOK-001 · Project scaffold** · P0 · deps: none
- `pyproject.toml` for the `rook-cli` package, `src/rook/` layout, entry point `rook = rook.cli.main:app`. Dependencies: pydantic, httpx, fastapi, uvicorn, sse-starlette, typer, textual, rich, pyyaml, pyjwt. Dev dependencies: pytest, pytest-asyncio, ruff.
- `.gitignore` (per 03 §2), `.env.example`, pytest config with `docker` and `bob` markers excluded by default, GitHub Actions CI running `uv run pytest -q`.
- **AC:** `uv sync` works; `uv run rook --version` prints `rook 0.1.0`; `uv run pytest -q` passes (a smoke test); CI workflow file present.

**ROOK-002 · Event bus, event models, redaction, store** · P0 · deps: 001
- pydantic models for **every** event in 02 §9 plus the envelope. `EventBus` (async pub/sub, per-run strictly increasing `seq`). `redact()` per 03 §2. The SQLite store (02 §10) persists events, and `events_after(run_id, seq)`.
- **AC:** unit tests cover every event type round-tripping to JSON; seq is monotonic under concurrent publishes; redaction scrubs all listed patterns; the store resumes from `after`.

**ROOK-003 · Model schema, loader, templating** · P0 · deps: 001
- pydantic schema for `rook.yaml` (02 §6): actors, actions, params (`int` range + edges, `choice`, `string`), `requires`, `capture` (JSONPath subset `$.a.b[0]`), state readers (`each`), rules (state/response). Template rendering for `{{p.* ref.* fresh.* env.* actor.*}}`. Reject absolute URLs.
- **AC:** valid and invalid YAML fixtures are tested; the templates render; an unknown variable is a clear error; `yaml.safe_load` only.

**ROOK-004 · Safe expression evaluator** · P0 · deps: 001
- As in 02 §6.1: an AST whitelist, attribute access mapped to dict keys, allowed functions only, a length cap.
- **AC:** evaluates the sample rules; rejects `__import__`, dunder attributes, lambdas, unknown calls, assignment and walrus (with tests); never uses eval/exec (the reviewer greps for it).

## M2 · Engine (proof)

**ROOK-005 · Fixture app "minishop"** · P0 · deps: 001
- `tests/fixtures/minishop/`: a small FastAPI app (in-memory or SQLite) with signup/login, products (the admin creates them with stock), orders (buy), refunds, cancel, ship and admin export. Known bugs: **refund checks each refund alone**, **stock check-then-decrement race** (with a small await in between), **ship ignores cancelled**, **admin export only checks login, not role**. A `MINISHOP_FIXED=1` env var fixes them all. Its own `rook.yaml` with the 4 rules. Normal tests that pass on the buggy version.
- **AC:** the fixture's own tests pass; the bugs reproduce with manual scripted sequences; the fixed mode removes them.

**ROOK-006 · HTTP executor** · P0 · deps: 003, 005
- An async httpx executor. Transport is either **ASGI (in-process)** or real HTTP. Runs actor setup, adds auth headers, captures values, reads state entities. **Egress guard** (03 §5), timeouts, size cap.
- **AC:** runs sequences on minishop in-process; captures work; any request to another host is refused (tested); per-request errors are recorded, not raised.

**ROOK-007 · Generator + Runner** · P0 · deps: 006
- A seeded random walk (02 §7.1), edge-value bias, `requires` satisfaction, weights, designed scenarios + mutation, N concurrent sequences, budget (count/time), and `engine.*` + `search.progress` events (throttled).
- **AC:** the same seed gives an identical sequence list (tested); ≥500 sequences/s in-process on minishop; stops at budget.

**ROOK-008 · Judge** · P0 · deps: 004, 007
- State rules per scoped entity after each step, and response rules for matching action and actor. It is the only emitter of `violation.found`.
- **AC:** finds the minishop refund bug within 20,000 sequences for 5 different seeds; finds the admin-export bug; reports no violation on `MINISHOP_FIXED=1` for 20,000 sequences.

**ROOK-009 · Shrinker** · P0 · deps: 008
- ddmin + a requires-repair pass + value shrinking. Real re-execution with fresh entities. `shrink.step` events.
- **AC:** the refund violation shrinks to exactly 3 steps (buy, refund, refund) plus the actor setup; the result is 1-minimal (tested); values shrink toward edges.

**ROOK-010 · Replayer** · P0 · deps: 009
- Replays N times and reports `k/N`, with a flaky flag.
- **AC:** the refund counterexample gives 10/10; a deliberately nondeterministic fixture reports flaky.

**ROOK-011 · Counterexample export + Verifier + Test Runner** · P0 · deps: 010
- `cx_NNN.json` (02 §7.8), the fallback HTTP-level pytest generator, TestRunner (runs a command in the sandbox and captures its exit code), Verifier (02 §7.7) with `verify.step/done` events.
- **AC:** on buggy minishop, verification fails; after `MINISHOP_FIXED=1`, all 4 checks pass; the generated fallback test fails on buggy and passes on fixed.

**ROOK-012 · Parallel steps (race condition)** · P1 · deps: 008
- `{parallel: [...]}` steps sent concurrently, and the generator sometimes emits them for actions touching the same entity.
- **AC:** finds the minishop stock race (stock < 0) within budget; the replay shows `k/10` with the flaky flag when k<10.

## M3 · Sandbox

**ROOK-013 · Sandbox interface + ProcessSandbox** · P0 · deps: 006
- Interface (02 §8), ProcessSandbox with the allowlist (repo name + commit SHA → start command, port env, temp DB env), health polling, kill on stop.
- **AC:** starts minishop as a real uvicorn subprocess on a free port, the engine runs over real HTTP, and it's cleaned up on stop and on exception; a non-allowlisted repo is refused.

**ROOK-014 · DockerSandbox** · P0 · deps: 013
- compose / dockerfile / command modes from a SandboxPlan, hardening flags (03 §3), a `127.0.0.1` random port, logs, restart, cleanup on exit and signal.
- **AC** (`-m docker`): builds and runs minishop from a generated Dockerfile; health OK; `docker ps` is empty after stop and after a crash.

## M4 · Bob agents

**ROOK-015 · BobClient + recorder** · P0 · deps: 002
- As in 02 §5.1: argv, `stdin=DEVNULL`, env (key + Node 24 PATH), `--disable-mcp`, NDJSON parsing into `agent.*` events with human details, last-JSON-block extraction + pydantic validation + retries, cost events, timeouts. Recorder with live, record and replay modes.
- **AC:** unit tests with recorded NDJSON fixtures (no coins); replay mode reproduces the events; one `-m bob` smoke test works live; the key never appears in argv, logs or events.

**ROOK-016 · Agent registry, prompts, schemas, modes file** · P0 · deps: 015
- 12 `AgentSpec`s (02 §5.3): slug, id, character, role, instructions, output schema, groups, max turns. `prompts/*.md` with an untrusted-data banner and the JSON contract. A modes.yaml writer, plus `.git/info/exclude`.
- **AC:** the generated YAML matches Bob's format; the Surgeon's edit regex is built per call; every schema has an example test.

**ROOK-017 · Scout → Mechanic → Mapper pipeline** · P0 · deps: 014, 016
- Scout summary; Mechanic plan → sandbox start (loop ≤3 with logs; ASK setup value); Mapper → actions and state; engine dry-runs each action (loop ≤3 with the HTTP error).
- **AC** (`-m bob`): on minishop (as a folder), the full pipeline produces a valid `rook.yaml` whose actions all dry-run OK. A recorded replay of that run passes in the default suite.

**ROOK-018 · Lawmaker + Rule Critic + sanity checks** · P0 · deps: 017
- Rules proposed with evidence; the engine sanity-checks (parse + holds on a fresh app); the critic's verdicts; the `rules.*` events.
- **AC** (recorded): produces the refund, stock, ship and admin rules; a rule that fails on a fresh app is auto-rejected with a reason.

**ROOK-019 · Test Designer + Strategist** · P1 · deps: 018, 007
- Scenarios go into the runner seed queue, and weights go into the generator.
- **AC:** designed scenarios run first (visible in events); the refund bug is found in fewer sequences than pure random over 5 seeds (logged).

**ROOK-020 · Detective + Diagnosis Reviewer** · P0 · deps: 011, 016
- Input bundle: rule, minimal steps, per-step state, sandbox logs, related files. Output: file:line + explanation. Review loop.
- **AC** (recorded): points to the minishop refund check line; the reviewer approves.

**ROOK-021 · Surgeon (regression test, then fix) + path guard + Fix Reviewer** · P0 · deps: 020
- Test-only call writes the native test, and the engine checks it **fails**. Fix call edits only the allowed files. The diff path guard reverts anything else. The Fix Reviewer loop. Then the Verifier.
- **AC** (recorded + one live run): the minishop refund fix is verified; an edit outside the allowed paths is reverted (tested with a fake).

**ROOK-022 · Coordinator + rails + Guide** · P0 · deps: 016
- Coordinator at branch points with the allowed-steps enforcement (02 §4). Rails as pure code with unit tests. Guide answers from the run snapshot, concurrently.
- **AC:** rails tests: no SHIP without verified, no FIX without approval, retry caps, budget stop; the Guide answer arrives as `chat.message` while the runner is still running.

## M5 · Session

**ROOK-023 · Session + Conductor end to end** · P0 · deps: 011, 017–022
- Workspace prep (local folder → git worktree/copy; GitHub → clone with token; demo → allowlist). The phase machine (02 §4), questions with answer futures, `--auto`, budgets, run persistence, cancel.
- **AC:** a **recorded** full run on minishop goes from PREPARE to verified fix to SHIP (a local branch in test mode) with the correct event order; cancel stops the sandbox and Bob processes.

## M6 · CLI (hero)

**ROOK-024 · Typer commands + CI mode** · P0 · deps: 023
- `rook [run|replay|explain|verify|init|serve|login|logout|--version]`. `run --ci` writes `rook-report.json/.md` and returns exit 1 on a violation.
- **AC:** each command has a test (CliRunner); CI mode returns exit 1 on buggy minishop and 0 on fixed.

**ROOK-025 · TUI shell** · P0 · deps: 024
- A Textual app: animated ROOK logo, first-run auth steps (a stub until 030), home box, input with history, slash commands with Tab completion, transcript, status bar, footer, keys (04 §2.3).
- **AC:** Textual `pilot` tests for launch, slash completion and help; renders at 80 columns.

**ROOK-026 · AgentSprite, AgentRow, EngineRow widgets** · P0 · deps: 025
- Sprite port (04 §1.3) with half-blocks + truecolor, bounce, blink, glance, shimmer and collapse, with a reduced-motion flag.
- **AC:** a snapshot test of every character's rendering; row lifecycle tests driven by fake events.

**ROOK-027 · Question prompts + cards** · P0 · deps: 026
- Menu, confirm and setup-value prompts; rules, counterexample, diagnosis, verify and PR cards; the shrink line (04 §2.2).
- **AC:** pilot tests answer each question type; the cards render from the sample events.

**ROOK-028 · Background run + chat** · P0 · deps: 027, 022
- The engine in a worker thread, events via `call_from_thread`, chat routed to the Guide during a run.
- **AC:** pilot test: while the fake runner emits progress, a typed question gets a Guide reply and progress keeps updating.

## M7 · Server

**ROOK-029 · FastAPI server** · P0 · deps: 023
- All routes in 02 §11 except auth/GitHub (in 030/031), SSE with `after` resume, owner checks (404), guest cookie + quotas, CORS, rate limits, size limit.
- **AC:** TestClient tests for each route, SSE resume, owner isolation and guest restrictions (demo repos only).

## M8 · Auth & GitHub

**ROOK-030 · Auth** · P1 · deps: 029
- Supabase JWT verification on the server, `/auth/cli/*` + the device flow, the CLI login (localhost callback, state check) and credentials storage (chmod 600), and `rook logout`.
- **AC:** tests with a locally signed JWT; the callback rejects a bad `state`; the file mode is 600.

**ROOK-031 · GitHub App integration** · P1 · deps: 030
- The install URL, the callback that stores the installation, the App JWT → installation token, repo listing, clone, branch, push, PR with the evidence body, and `/github/token` for the CLI.
- **AC:** unit tests with mocked GitHub HTTP; one manual live test creating a PR on the demo repo (recorded in HANDOFF).

**ROOK-032 · GitHub Action** · P1 · deps: 024
- `action.yml` (composite) runs `rook run --ci --auto` with recorded/live Bob and comments `rook-report.md` on the PR.
- **AC:** a workflow example in the README; a dry run on a fixture PR comment payload.

## M9 · Web

**ROOK-033 · Web scaffold + event client** · P0 · deps: 029
- Next.js + Tailwind with the tokens (04 §3.5) and fonts, the layout shell (sidebar, main, composer), `lib/events.ts` types (mirroring 02 §9), a reconnecting SSE client, and the `runStore` reducer.
- **AC:** vitest for the reducer over a recorded event log; `tsc --noEmit` is clean.

**ROOK-034 · Web AgentSprite + rows** · P0 · deps: 033
- A canvas sprite port (04 §1.3), AgentRow, EngineRow, reduced motion.
- **AC:** a component test renders every agent; the reduced-motion story is static.

**ROOK-035 · Web cards + answers + chat** · P0 · deps: 034
- RulesCard, SearchCard, CounterexampleCard, FixCard, VerifyCard, QuestionCard; POST answers and chat; the guest auto-answer countdown.
- **AC:** tests driven by the recorded event log reach the final state with a PR button.

**ROOK-036 · Home, repo picker, runs, recents, login, guest** · P0 · deps: 035, 030
- Pages per 04 §3.2, the repo picker (GitHub + demo), recents with status dots, "Try the demo", the empty, error and limit states.
- **AC:** the E2E happy path against a local server in replay mode (a Playwright smoke test, or a documented manual check if Playwright is too slow to set up).

## M10 · Deploy & demo

**ROOK-037 · Hugging Face Space image** · P0 · deps: 029, 013
- `deploy/hf/Dockerfile`: Python 3.12, Node 22 and 24, Go, Bob Shell 2.0.5, the demo apps cloned at pinned SHAs and pre-built, a non-root user, and start.sh. The allowlist config. Secrets documented. A keep-alive workflow.
- **AC:** `docker build` works locally; the container serves `/health`; a guest demo run on shop-app completes in replay mode inside the container.

**ROOK-038 · Vercel deploy** · P0 · deps: 036
- A Vercel project, env vars, CSP headers (03 §8), the production URL in the README.
- **AC:** the public URL loads, a guest demo run streams from the Hugging Face server, and there are no console errors.

**ROOK-039 · Demo apps integration & recordings** · P0 · deps: 023, 037, U5
- Run the full flow live on shop-app, billing-service and wallet-api; fix any engine or agent issues; record the Bob runs for replay mode; tune budgets so each bug is found in under 60 s.
- **AC:** all planned bugs (PRD §9) are found, shrunk, fixed and verified at least once live, and replay runs are clean.

**ROOK-040 · Release polish** · P1 · deps: 039
- README with GIFs/screens, PyPI publish of `rook-cli`, a `v0.1.0` tag, links (video, URL, deck).
- **AC:** `uv tool install rook-cli` works from PyPI in a clean environment.

---

## U · User tasks (Aayush, in parallel)

| ID | Task | Needed by |
|---|---|---|
| U1 | Supabase project + Google OAuth client (Google Cloud Console); send the URL + anon key, and put the JWT secret in the Hugging Face secrets | ROOK-030 |
| U2 | Create the GitHub App "Rook" (permissions per 03 §6) and store the private key + app id in the Hugging Face secrets | ROOK-031 |
| U3 | Create the Hugging Face Docker Space `rook` and add the secrets | ROOK-037 |
| U4 | Create the Vercel project from `web/` | ROOK-038 |
| U5 | Build the 3 demo apps with Antigravity (prompt from Claude, on request) and push them to GitHub | ROOK-039 |
| U6 | Use Bob IDE visibly (e.g. review agent prompts, build demo app bugs) and screen-record short clips | Video |
| U7 | Record the demo video (≤5 min, MP4) | Submission |
| U8 | Slide deck (PDF) | Submission |
| U9 | Submit on lablab: URL, video, deck, repo | 27 Sep 20:30 IST |
