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

**ROOK-037 · Server image + AWS EC2 deploy** · P0 · deps: 029, 013
- Re-targeted from Hugging Face (Docker Spaces now need a paid plan) to AWS EC2 + Caddy on `https://<ip-dashes>.sslip.io` (02 §14).
- `deploy/Dockerfile`: Python 3.12 + uv, Node 22 and 24, Go, Bob Shell 2.0.5 (from the gitignored `deploy/vendor/`, packed by `deploy/pack-bob.sh`; without it the image is replay-only), the demo apps cloned at pinned SHAs and pre-built (`deploy/demos/`; interim demo `rook-demo/minishop` with its recordings), a non-root user, and start.sh. `deploy/docker-compose.yml` (rook + Caddy), the allowlist config, secrets documented (`/etc/rook/rook.env`, `deploy/aws/scripts/set-secret.sh`). `deploy/aws/` scripts: create, deploy, destroy, ssh. No keep-alive (EC2 does not sleep).
- **AC:** `docker build` works locally; the container serves `/health`; a guest demo run completes in replay mode inside the container.

**ROOK-038 · Vercel deploy** · P0 · deps: 036
- A Vercel project, env vars (`ROOK_API_PROXY_TARGET` = the EC2 server origin `https://<ip-dashes>.sslip.io` at build time, `NEXT_PUBLIC_API_URL` unset; see 02 §14), CSP headers (03 §8), the production URL in the README.
- **AC:** the public URL loads, a guest demo run streams from the EC2 server, and there are no console errors.

**ROOK-039 · Demo apps integration & recordings** · P0 · deps: 023, 037, U5
- Run the full flow live on shop-app, billing-service and wallet-api; fix any engine or agent issues; record the Bob runs for replay mode; tune budgets so each bug is found in under 60 s.
- **AC:** all planned bugs (PRD §9) are found, shrunk, fixed and verified at least once live, and replay runs are clean.

**ROOK-040 · Release polish** · P1 · deps: 039
- README with GIFs/screens, PyPI publish of `rook-cli`, a `v0.1.0` tag, links (video, URL, deck).
- **AC:** `uv tool install rook-cli` works from PyPI in a clean environment.

## M11 · Public website (spec: `docs/06_PUBLIC_SITE.md`)

**ROOK-043 · Site foundation, route move, design system, simple pages** · P1 · deps: 042
- Move the app home from `/` to `/app` and update every in-app link and redirect (06 §1); the GitHub setup return on `/` redirects in `middleware.ts`; e2e smoke and doc 04 §3.2 updated.
- Site design system (06 §3): tokens, type scale, `Section`, `Card`, `Badge`, `Button`, `CodeBlock`; SVG logo mark + wordmark + favicon; sticky translucent header with a `<details>` mobile menu and a skip link; full footer (Product, Docs, Company, Legal); the reduced-motion CSS rule.
- `web/content/*.ts` structure (one source per repeated fact); metadata (title template, OG/Twitter with an OG image, theme colour).
- Pages: `/pricing` (launch notice from `content/pricing.ts`), `/privacy` and `/terms` (draft banner + placeholders), branded 404. `/` gets a minimal home (hero text + CTAs) that ROOK-044 completes.
- Tooling: `motion`, React Testing Library + jsdom, ESLint flat config with `npm run lint`.
- **AC:** 06 §9 tests for these pages (landmarks, heading order, banned patterns, pricing notice, legal banners, skip link, 404, the reduced-motion rule); `/app` and all old app routes still work; typecheck, lint, test and build pass.

**ROOK-044 · Home page: parallax hero, walkthrough, sections** · P1 · deps: 043
- 06 §5.1 and §6: the layered parallax hero (text never moves), the walkthrough built from the app's real components with sample data, Features, "What Rook refuses to do", "Where Rook is today", FAQ, closing CTA. `motion` only in these client islands.
- **AC:** 06 §9 home tests (landmarks, heading order, walkthrough: one visible frame, no network, autoplay, step click, pause/play, reduced motion = still with no autoplay or parallax, complete with JS off); typecheck, lint, test and build pass.

**ROOK-045 · Docs, Security, Sign-in, final audit** · P1 · deps: 044
- `/docs` (flow + getting started), `/security` (data handling + "What is not yet true"), `/login` restyled with the four sign-in states (06 §7), "Open workspace" for signed-in visitors, the app's account menu with sign-out checked.
- Final audit across the site: every 06 §9 test, each rule broken once and restored, a 360 px layout check, no secrets in the client bundle.
- **AC:** all of 06 §9 passes; sign-in is never called without a click; typecheck, lint, test and build pass, with results reported.

**ROOK-046 · Site polish: no-JS sign-in, copy-rule negation** · P2 · deps: 045
- With JS off, `/login` shows no dead "Continue with Google" button (the CSP allows inline styles, so a `<noscript><style>` can hide it; or render it disabled until hydration with no layout shift). The `<noscript>` note stays.
- The certification/audit banned pattern is shielded by a negation only when the negation governs the term: "not just audited but certified" is caught; "no third-party audit or penetration test, and no certifications" still passes.
- **AC:** tests for both; typecheck, lint, test and build pass.

**ROOK-047 · Site uses the full desktop width** · P1 · deps: 046
- User feedback (11 Oct, 1920 px screen): the site looks like a tablet layout. The header spans the full width (logo at the far left, CTAs at the far right); content containers widen (about 1440 px) with larger side padding on large screens; the hero headline, product figure, walkthrough, feature grid and footer use the extra width; paragraphs keep a readable measure.
- **AC:** no horizontal scroll from 360 px to 2560 px; at 1920 px the header and content reach near the edges; existing tests pass; typecheck, lint, test and build pass.

**ROOK-048 · Remove the word "demo" from user-facing text** · P1 · deps: 047
- User request (11 Oct): no visible "demo" anywhere on the site or in the web app. CTA "Try the demo" → "Try Rook"; "demo apps/repos" → "example apps/repositories"; "guest demo" → guest runs / trying Rook without an account; app headings, the "Demo rule" pill and limit messages reworded; server messages the web app shows ("Demo limit reached…", "Guests can only run the demo repos") reworded, with the web still recognising the old server message until the server is redeployed.
- Unchanged: code identifiers, API values (`kind: "demo"`), data attributes, file names, comments, internal docs, README and the CLI.
- **AC:** a test fails if "demo" appears in any `content/*.ts` string, any rendered site page, or the app's visible strings; web and Python suites pass; typecheck, lint and build pass.

## M12 · Launch readiness (user request 12 Oct; spec: `docs/06_PUBLIC_SITE.md`, decisions in HANDOFF)

Streams: **CI** 049 · **server** 050 → 051 · **web**, strictly in order (they share `web/` and `next build`): 053 → 054 → 055 → 056 → 052 → 057.

**ROOK-049 · CI green + web checks + scheduled live smoke** · P0 · deps: none
- CI fails on every push: `.gitignore` line `rook-report.md` hides `tests/fixtures/github_action/rook-report.md`, so 2 tests in `tests/unit/test_github_action.py` fail on the runner. Un-ignore and commit that fixture (keep the root `rook-report.md` ignored).
- `ci.yml`: add a `web` job (Node 22, `npm ci`, typecheck, lint, test, build in `web/`); move actions to their Node 24 majors.
- New `.github/workflows/live-smoke.yml` (schedule every 6 h + manual): checks the live site pages (`/`, `/app`, `/docs`, `/pricing`, `/security`, `/privacy`, `/terms`, `/login`) answer 200 and `/api/v1/health` answers `ok: true` through the Vercel proxy. URL from one env value. No secrets. A failed scheduled run emails the repo owner (GitHub's default).
- **AC:** `uv run pytest -q` passes from a clean clone (`git clone` to a temp dir, then run the 2 tests); the web job's commands pass locally; `actionlint` (or `uvx` yamllint) clean on both workflows.

**ROOK-050 · Hosted GitHub runs off; no Docker socket on the server** · P0 · deps: none
- User decision (12 Oct): the hosted server runs only recorded guest runs. `deploy/docker-compose.yml` no longer mounts `/var/run/docker.sock` and has no `group_add`; `ROOK_GITHUB_RUNS_MAX` defaults to 0. Turning hosted runs on again is an explicit opt-in override file (`deploy/docker-compose.github-runs.yml`) that `deploy/aws/deploy.sh` uses only when `ROOK_GITHUB_RUNS=1`; without it, `deploy.sh` doesn't need `DOCKER_GID`.
- With runs off, `/me.can_run_github` is false and `POST /runs` with `repo.kind=github` answers a clear error that says to run the repo with the CLI (check today's behaviour first; keep status codes per 02 §11).
- Confirm guest recorded runs don't need Docker on the server (ProcessSandbox) and still work with no socket.
- Docs: 02 §8/§14, 03 §3, `deploy/README.md`.
- **AC:** tests for the off default and the github-run error; compose renders (`docker compose config`) without the socket and without `DOCKER_GID`, and with the override it has both; a guest recorded run passes in the server tests; Python suite passes.

**ROOK-051 · Data deletion and retention (server)** · P0 · deps: 050
- Contract (02 §11, doc first): `DELETE /runs/{id}` (owner, user or guest) deletes the run, its events, counterexamples and workspace files; 404 for anyone else; a running run is cancelled first. `DELETE /me/data` (user) deletes every run they own and their `users` row (GitHub link), answers `{ok, runs_deleted}`.
- Retention sweep at startup and hourly: runs older than `ROOK_RETENTION_DAYS` (default 30) with their events, counterexamples and workspaces; guest quota rows older than 2 days. Never deletes an active run.
- 03 data section updated (what is deleted, when; the Supabase account is deleted on email request).
- **AC:** route tests (owner, other user, guest, missing, running run), the sweep with a fake clock, nothing left in the DB or on disk for a deleted run; Python suite passes.

**ROOK-053 · Site identity, positioning, new pages, SEO** · P1 · deps: none (copy facts from 06 §4 M12)
- 06 §4 "Positioning", "Operator and contact", "Site URL": remove hackathon-stage positioning everywhere on the site (keep it only in the About story); `CONTACT_EMAIL`, `SITE_URL` in `content/site.ts`; Bob acknowledged, not the headline.
- New pages `/about`, `/contact`, `/roadmap`; `/pricing` becomes "Early access and open source" (06 §5.4). Header nav and footer columns per 06 §8.
- `app/sitemap.ts`, `app/robots.ts`, `metadataBase`, consistent titles, descriptions, OG/Twitter images, favicon and logo.
- Tests: the copy guards updated (no "hackathon" outside About, no `[...]` placeholders, no "demo"), every footer and header link resolves to a real route, sitemap lists exactly the site pages, robots disallows app routes.
- **AC:** 06 §9 tests for the new pages; typecheck, lint, test and build pass; no `metadataBase` warning at `next start`.

**ROOK-054 · Home page: problem-first hero, refund-bug story, 6-step diagram, screenshot** · P1 · deps: 053
- Hero headline names the customer problem and outcome in plain words; primary "Try Rook", secondary "Read the docs" + GitHub.
- The refund bug is the central story: a section that shows the real recorded case end to end (the rule, the minimal 3-step sequence with its values, the replay result, the one-line diagnosis, the fix diff, the 4 verification checks), with every value taken from the recorded run or the engine tests (cite the files in the report).
- The 6 steps as a clean, simple diagram (HTML/SVG, plain language, works at 360 px and with JS off).
- Features rewritten as developer benefits tied to verifiable facts (06 §4 only).
- A **real product screenshot** of the web app (a recorded shop-app run, captured from the running app at desktop and mobile widths with the bundled Chromium), served from `web/public/`, with alt text and labelled "Recorded example run".
- Typography, spacing, hierarchy and mobile pass (360–2560 px, no horizontal scroll).
- **AC:** home tests updated (landmarks, heading order, one h1, CTAs and targets, the story's values match their source, reduced motion still, JS off complete); typecheck, lint, test and build pass.

**ROOK-055 · Docs guides** · P1 · deps: 054
- `/docs` overview + the guides in 06 §1 (`getting-started`, `install`, `rules`, `counterexamples`, `github-action`, `data`), each with a table of contents.
- Supported environments, dependencies and limitations stated from the code (`pyproject.toml`, `action.yml`, sandbox code); the example `rook.yaml` is a real file from the repo; CLI commands match `uv run rook --help` and each subcommand's `--help`; the install command is checked to work (`uv tool install` into a temp `UV_TOOL_DIR`, or `uvx --from git+…` `rook --help`).
- When repo data goes to IBM Bob (live runs only), what is sent, and that the guest runs send nothing to Bob.
- README brought in line with the site (same claims, same install command, links to the guides).
- **AC:** each guide renders with correct landmarks and heading order; a test checks every CLI command quoted in the docs exists in the Typer app; typecheck, lint, test and build pass.

**ROOK-056 · Privacy, Terms, Security copy (in effect)** · P1 · deps: 055, 051, 050
- `/privacy` and `/terms` per 06 §5.5 (operator, email, India, effective date, no placeholders, no draft banner); privacy lists what is collected, where it is stored, recipients, retention (30 days runs, 2 days guest quota rows) and how to delete (the app buttons from ROOK-052, or email).
- `/security` updated for ROOK-050 and ROOK-051 (no Docker socket; hosted own-repo runs off; deletion), "What is not yet true" kept honest; no certification or audit claims.
- **AC:** tests: no placeholders, the operator/email/jurisdiction present, every data fact traceable to 06 §4; the certification guard still passes; typecheck, lint, test and build pass.

**ROOK-052 · Web app: deletion UI, honest run labels, states, a11y** · P1 · deps: 056
- "Delete run" on the run page (confirm step) and "Delete my data" in the account menu (confirm step, then sign out), using the ROOK-051 routes; both handle failure with a retry.
- Run labels "Recorded example run" / "Live run" (06 §4); `/app` explains what signing in adds (run history across devices, GitHub link) and that your own repos run with the CLI (hosted runs off).
- Loading, failure, quota-reached and retry states with plain explanations; no button that does nothing (hide or disable the unbuilt ones: edit one rule, replay, download test).
- The app's contrast follow-ups (HANDOFF: `--faint`, white on accent, agent name colours) reach 4.5:1 with the smallest visible change; app pages work at 360 px.
- Terminal colour codes: `lib/safeText.ts` drops the ESC byte but leaves the rest of an ANSI sequence, so the live verify card shows `[2m   Duration [22m 2.77s` (seen in a live shop-app run 12 Oct). Strip whole ANSI CSI/OSC sequences before dropping controls.
- **AC:** component tests for both deletions (confirm, success, failure + retry), the labels, the states, no dead buttons; contrast test for the app tokens; typecheck, lint, test and build pass.

**ROOK-057 · Final verification** · P1 · deps: all of M12
- Every route at 360, 768, 1440 and 1920 px in Chromium: no horizontal scroll, no broken images, screenshots in the report.
- Link check: every internal `href` resolves; every external link answers < 400.
- axe-core on every site page and the app home: no serious or critical issues.
- Build output scan: no secrets, no `[...]` placeholders, no "testimonial"/"trusted by", no "demo" in visible text.
- Security headers and HTTPS on the live URL (after deploy).
- **AC:** a repeatable script (`web/e2e/audit.mjs`) that does the above against a URL, passing on local `next start`.

---

## U · User tasks (Aayush, in parallel)

| ID | Task | Needed by |
|---|---|---|
| U1 | Supabase project + Google OAuth client (Google Cloud Console); send the URL + anon key, and put the JWT secret on the server (`deploy/aws/scripts/set-secret.sh SUPABASE_JWT_SECRET`) | ROOK-030 |
| U2 | Create the GitHub App "Rook" (permissions per 03 §6) and store the private key + app id on the server (`set-secret.sh GITHUB_APP_PRIVATE_KEY < app.pem`, `GITHUB_APP_ID`) | ROOK-031 |
| U3 | Run the AWS EC2 scripts (`deploy/README.md`: pack Bob, `create.sh`, `deploy.sh`) with the AWS profile `rook`, then add the secrets with `set-secret.sh` | ROOK-037 |
| U4 | Create the Vercel project from `web/` | ROOK-038 |
| U5 | Build the 3 demo apps with Antigravity (prompt from Claude, on request) and push them to GitHub | ROOK-039 |
| U6 | Use Bob IDE visibly (e.g. review agent prompts, build demo app bugs) and screen-record short clips | Video |
| U7 | Record the demo video (≤5 min, MP4) | Submission |
| U8 | Slide deck (PDF) | Submission |
| U9 | Submit on lablab: URL, video, deck, repo | 27 Sep 20:30 IST |
| U10 | Redeploy the server after ROOK-050 + 051 (`deploy/aws/deploy.sh`) | M12 |
| U11 | Approve the push to `main` (Vercel deploys the site) | M12 |
| U12 | Redeem the free domain and connect it in Vercel; then change `SITE_URL` | M12 |
| U13 | Trademark/name check for "Rook" (IP India, USPTO; note the CNCF project Rook at rook.io) | M12 |
| U14 | Publish the Google OAuth consent screen (it is in Testing mode, so only test users can sign in) | M12 |
| U15 | Live GitHub App PR test on a test repo of your own, with the CLI | M12 |
| U16 | Lawyer review of Privacy and Terms; launch demo + feedback from first developers | Launch |
