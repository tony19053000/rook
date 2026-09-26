# 02 · Technical Architecture: Rook

> **Contracts in this doc are law.** Section 6 (the model schema), section 9 (events) and section 11 (API) are shared by the CLI, the server and the web app. Change them only by editing this doc in the same commit.

---

## 1. Overview

```mermaid
flowchart LR
  subgraph Surfaces
    CLI["rook CLI (Textual TUI) - hero"]
    WEB["Web app (Next.js on Vercel)"]
  end
  subgraph Core["Rook core (Python)"]
    SES["Session + Conductor<br/>(phases, rails, event bus)"]
    AGT["Bob agent layer<br/>12 custom modes"]
    ENG["Engine<br/>Runner · Judge · Shrinker · Replayer · Test Runner · Verifier"]
    SBX["Sandbox<br/>Docker (local) · Process (hosted)"]
    STO[("SQLite store<br/>runs · events · counterexamples")]
  end
  SRV["FastAPI server<br/>REST + SSE"]
  BOB["IBM Bob Shell<br/>bob run --mode … --format stream-json"]
  APP["Target app<br/>(any language, HTTP API)"]
  GH["GitHub App"]
  SUPA["Supabase Auth (Google)"]

  CLI -->|in-process| SES
  WEB -->|HTTPS + SSE| SRV --> SES
  SES --> AGT --> BOB
  SES --> ENG --> SBX --> APP
  SES --> STO
  SES --> GH
  CLI & WEB --> SUPA
```

- **One core, two surfaces.** The CLI runs the core **in-process**. The web app talks to the **server**, which wraps the same core. Both render the **same event stream** (section 9).
- **Bob thinks, the engine proves.** Agents produce proposals (rules, actions, fixes). The engine executes and decides.

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Core, engine, server | **Python 3.12**, `uv`, pydantic v2, httpx, FastAPI, uvicorn, sse-starlette, PyYAML, PyJWT | Fast to build, strong async HTTP, one language for the whole backend |
| CLI | **Typer** (commands) + **Textual** (interactive TUI) + Rich | Smooth truecolor animation, no flicker, widgets |
| Web | **Next.js 15** (App Router) + TypeScript strict + Tailwind v4, `@supabase/supabase-js`, vitest | A familiar layout and fast to build, hosted on Vercel |
| AI | **IBM Bob Shell 2.0.5** via `bob run` | Custom modes act as agents, with streamed JSON output |
| Storage | SQLite (stdlib `sqlite3`, WAL) | Zero ops. The same schema works locally and hosted |
| Sandbox | Docker CLI (local), subprocess (hosted allowlist) | Runs any repo locally, and runs on Hugging Face without Docker-in-Docker |
| Auth | Supabase Auth (Google OAuth), GitHub App | Standard and quick |
| Hosting | Vercel (web), Hugging Face Docker Space (server + demo apps) | Both are available to us for free |

## 3. Repository layout

```
rook/                           # repo root (github.com/tony19053000/rook)
├─ CLAUDE.md  README.md  HANDOFF.md  STATUS.md
├─ docs/01_PRD.md … 05_FEATURE_TICKETS.md, docs/mockups/*.html
├─ .claude/agents/coder.md, reviewer.md
├─ pyproject.toml               # package "rook-cli", entry point: rook = rook.cli.main:app
├─ src/rook/
│  ├─ core/            session.py (Session, Conductor), phases.py, rails.py, events.py (bus + models), config.py
│  ├─ agents/          bob.py (BobClient), registry.py (AgentSpec x12), prompts/*.md, schemas.py, modes.py (writes .bob/custom_modes.yaml), recorder.py
│  ├─ model/           schema.py (rook.yaml pydantic), expr.py (safe evaluator), loader.py
│  ├─ engine/          runner.py, generator.py, executor.py (HTTP), judge.py, shrinker.py, replayer.py, verifier.py, testrunner.py, isolation.py
│  ├─ sandbox/         base.py, docker.py, process.py, allowlist.py
│  ├─ store/           db.py (schema + migrations), repo.py (queries)
│  ├─ github/          app.py (JWT, installation tokens), repos.py, pr.py
│  ├─ auth/            cli_login.py (localhost callback + device code), tokens.py, verify.py (Supabase JWT)
│  ├─ export/          counterexample.py (JSON), tests.py (native test via Bob + validation, fallback HTTP pytest)
│  ├─ server/          app.py (FastAPI), routes/*.py, sse.py, guest.py (quotas)
│  └─ cli/             main.py (Typer), tui/app.py (Textual), tui/widgets/*.py (AgentSprite, EngineRow, Question, Cards), logo.py
├─ tests/
│  ├─ fixtures/minishop/        # tiny in-repo FastAPI app with known bugs, used to test the engine (NOT a demo app)
│  └─ unit/ …, integration/ … (markers: docker, bob)
├─ web/                         # Next.js app
└─ deploy/hf/Dockerfile, deploy/hf/start.sh, deploy/vercel.md
```

Files written into the **target repo** (committed by the user, like tests):
```
<target>/rook/rook.yaml                 # actions, state readers, rules (the "model"), human-approved
<target>/rook/counterexamples/cx_001.json
<target>/<native test path>/rook_cx_001.<ext>   # regression test, e.g. tests/rook_cx_001.test.js
```
Local user data lives in `~/.rook/` with `credentials.json` (chmod 600), `rook.db`, `workspaces/<run_id>/` and `recordings/`.

## 4. Session, phases and the Conductor

A **run** is one Session. The Conductor drives these phases and emits events (section 9):

```
PREPARE      clone/copy repo into ~/.rook/workspaces/<run>/ (git worktree for local folders), write .bob/custom_modes.yaml
SCOUT        agent scout        -> RepoSummary
START_APP    agent mechanic     -> SandboxPlan; engine starts the sandbox + health check  (loop ≤3 on failure; may ASK setup value)
MAP          agent mapper       -> actions + state (rook.yaml part); engine dry-runs each action once (loop ≤3)
RULES        agent lawmaker     -> rules; engine sanity-checks (parse + holds on fresh app); agent rule_critic -> verdicts
APPROVE      ASK approve_rules  (auto mode: accept critic-approved)
DESIGN       agents test_designer + strategist (parallel) -> scenarios, weights
SEARCH       engine runner+judge (background; chat allowed) until violation or budget
  └─ on violation: SHRINK -> REPLAY -> SAVE (json + native regression test written by surgeon in test-only scope, see §7.8)
DIAGNOSE     agent detective -> Diagnosis; agent diag_reviewer -> verdict (loop ≤3)
APPROVE_FIX  ASK fix
FIX          agent surgeon (only edit-capable agent) -> patch in workspace; agent fix_reviewer -> verdict (loop ≤3)
VERIFY       engine verifier: replay + project tests + fresh search  (fail -> back to DIAGNOSE, ≤3)
APPROVE_PR   ASK pr
SHIP         push branch + open PR (or apply to local tree if local folder mode and user chooses)
DONE
```

**The Coordinator (AI) and the rails:**
- The Conductor has a **default path** (above). At **branch points** (an agent failed 3 times, the search budget ran out with no violation, verification failed, or the user sent a free-form request), it calls the **coordinator** agent with a compact state summary and the **allowed next steps** for the current phase. It gets back `{"next": <step>, "reason": str}`.
- **Rails** (`core/rails.py`) are code and cannot be overridden:
  - `next` must be in the allowed set, otherwise the default is used
  - no FIX without an answered "fix" question (or `--auto`)
  - no SHIP without `verify.done{verified:true}`
  - only engine events can mark `violation.found` or `verified`
  - at most 3 retries per agent per phase
  - a coin budget per run (default 1.5) and a hard cap per day on the hosted server
- The **Guide** agent runs **concurrently** whenever the user sends chat text. It gets a JSON snapshot of the run (phase, counters, recent events, last errors) and never changes run state.

## 5. Bob agent layer

### 5.1 BobClient (`agents/bob.py`)
```
argv = [BOB, "run", "--mode", slug, "--format", "stream-json", "--workspace", ws,
        "--max-turns", str(n), "--disable-mcp", "--trust", "--accept-license"]   # prompt passed via argv (last arg)
subprocess: stdin=DEVNULL (MANDATORY, else it hangs), cwd=workspace (MANDATORY: --trust only trusts the cwd, and workspace custom modes load only from a trusted folder), env adds BOB_API_KEY, PATH includes Node 24 bin, timeout per call
```
- It parses **NDJSON**:
  - `{"type":"message","role":"assistant","content":…}` chunks are concatenated
  - `{"type":"tool_use","tool_name":…,"parameters":…}` becomes `agent.progress` with a human detail (`read_file path` → `reading src/refunds.js`)
  - `{"type":"result","status","stats":{"session_costs","duration_ms"}}` ends the call and gives its cost
- **Output contract:** every agent must end with **one fenced ```json block** that matches its pydantic schema (`agents/schemas.py`). BobClient extracts the last JSON block and validates it. On an error, it re-prompts with the validation error, up to 3 times.
- **Recorder:** every call is stored in `~/.rook/recordings/<sha256(slug + "\0" + prompt)>.ndjson`. Callers must build deterministic prompts that include every input (file contents or a digest), so the same inputs give the same key. `ROOK_BOB_MODE=live|record|replay` controls this. Replay emits the recorded stream with the original timing (max 3×) and marks `agent.finished.recorded=true`, and the UIs show a "recorded" tag.
- **Cost:** `cost.update` events come from the `session_costs` totals.

### 5.2 Modes file
`agents/modes.py` generates `<workspace>/.bob/custom_modes.yaml` from `registry.py`. The workspace's `.git/info/exclude` gets `.bob/` so it never reaches a PR. The format is Bob's custom-mode YAML:
```yaml
customModes:
  - slug: rook-scout
    name: Rook Scout
    description: …
    roleDefinition: …
    whenToUse: …
    customInstructions: …   # includes the JSON output contract
    groups: [read]          # surgeon: [read, [edit, {fileRegex: "<approved paths>", description: "fix files"}]]
```
Tool groups are the **real permission boundary**, because `bob run` pre-approves every tool call that's allowed.

### 5.3 The 12 agents

| Slug | Character | Group | Input | Output schema (key fields) | Tools |
|---|---|---|---|---|---|
| `rook-coordinator` | Coordinator | control | state summary, allowed steps | `{next, reason}` | read |
| `rook-scout` | Scout | analyzer | workspace | `RepoSummary{language, framework, entrypoints[], routes_files[], models_files[], test_command, run_hints, business_summary}` | read |
| `rook-strategist` | Strategist | analyzer | rules, actions, search stats | `{weights:{action:float}, focus[], reason}` | read |
| `rook-detective` | Detective | analyzer | rule, minimal steps, per-step state, logs, code | `Diagnosis{file, line, explanation, evidence[]}` | read |
| `rook-mechanic` | Mechanic | maker | summary, Docker/compose/manifests, error logs | `SandboxPlan{mode: compose\|dockerfile\|command, build, start, port, health_path, env_required[], env_defaults{}}` | read, edit(`^\.rook-sandbox/`) |
| `rook-mapper` | Mapper | maker | summary, route/model files | `{actors[], actions[], state[]}` (section 6) | read |
| `rook-lawmaker` | Lawmaker | maker | model files, validation, tests, docs, actions/state | `{rules[]}` with `evidence` | read |
| `rook-test-designer` | Test Designer | maker | rules, actions | `{scenarios:[{name, rule_id, steps[]}]}` | read |
| `rook-surgeon` | Surgeon | maker | diagnosis, code, counterexample | patch applied in workspace + `{files[], summary}` | read, **edit (only the files in the diagnosis plus tests)** |
| `rook-rule-critic` | Rule Critic | reviewer | proposed rules + evidence | `{verdicts:[{rule_id, verdict: approve\|reject\|revise, reason, revised?}]}` | read |
| `rook-diag-reviewer` | Diagnosis Reviewer | reviewer | diagnosis + raw evidence | `{verdict, reason}` | read |
| `rook-fix-reviewer` | Fix Reviewer | reviewer | diff, diagnosis, rules | `{verdict, issues[]}` | read |
| `rook-guide` | Guide | helper | run snapshot + question | `{answer}` | read |

The regression test is written by the **Surgeon** in a separate, test-only call (edit limited to the test path) **before** the fix, and the engine checks that it **fails**. After the fix, it must **pass** (see section 7.8).

## 6. The model: `rook/rook.yaml` (CONTRACT)

Written by the Mapper and Lawmaker, validated by `model/schema.py`, and approved by the human.

```yaml
version: 1
app:
  base_url: "{{sandbox.base_url}}"          # injected at runtime
  health: {method: GET, path: /health, expect_status: 200}
  isolation: fresh_entities                  # fresh_entities | restart
actors:
  - name: customer
    setup:                                   # run at sequence start to create a fresh actor
      - {method: POST, path: /auth/signup, json: {email: "{{fresh.email}}", password: "pw-{{fresh.id}}"}}
      - {method: POST, path: /auth/login,  json: {email: "{{fresh.email}}", password: "pw-{{fresh.id}}"},
         capture: {token: "$.token"}}
    auth: {header: Authorization, value: "Bearer {{actor.token}}"}
  - name: admin
    setup: [{method: POST, path: /auth/login, json: {email: admin@demo.local, password: "{{env.ADMIN_PASSWORD}}"}, capture: {token: "$.token"}}]
    auth: {header: Authorization, value: "Bearer {{actor.token}}"}
actions:
  - name: buy
    actor: customer
    request: {method: POST, path: /orders, json: {product_id: "{{ref.product_id}}", price: "{{p.price}}"}}
    params: {price: {int: [1, 500], edges: [1, 100, 500]}}
    requires: [product_id]                   # captured vars that must exist
    capture: {order_id: "$.id"}              # appended to the sequence's var pool (lists allowed)
    weight: 1.0
  - name: refund
    actor: customer
    request: {method: POST, path: "/orders/{{ref.order_id}}/refunds", json: {amount: "{{p.amount}}"}}
    params: {amount: {int: [1, 500], edges: [1, 50, 60, 100]}}
    requires: [order_id]
state:
  - name: order                              # entity reader
    each: order_id                           # evaluated for every captured order_id
    request: {method: GET, path: "/orders/{{order_id}}", actor: admin}
    fields: {paid: "$.paid", refunded: "$.refunded_total", status: "$.status"}
  - name: product
    each: product_id
    request: {method: GET, path: "/products/{{product_id}}", actor: admin}
    fields: {stock: "$.stock"}
rules:
  - id: refund_le_paid
    text: "Total refunds never exceed the amount paid"
    kind: state                              # state | response
    scope: order                             # a state entity name, or "global"
    check: "order.refunded <= order.paid"
    evidence: ["src/refunds.js:42 validates each refund alone", "README: Refunds section"]
    status: approved                         # proposed | approved | rejected
  - id: admin_export_forbidden
    text: "A normal user never opens the admin export"
    kind: response
    when: {action: admin_export, actor: customer}
    check: "response.status in (401, 403)"
    status: approved
```

**Templates:** `{{p.x}}` is a generated param, `{{ref.v}}` picks a captured var (a random earlier value), `{{fresh.*}}` is a unique per-sequence value, `{{env.X}}` comes from the sandbox env, and `{{actor.token}}` is the current actor's token.
**Concurrency:** a sequence step may be `{parallel: [step, step]}`. Its steps are sent concurrently (to catch races like the last item selling twice).

### 6.1 Safe expression evaluator (`model/expr.py`)
- It parses with `ast.parse(mode="eval")`. Allowed nodes: `Expression, BoolOp, BinOp(+ - * / // %), UnaryOp(not, -), Compare (all ops incl. in / not in), Name, Constant, Tuple, List, Attribute` (reading dict keys only), `Subscript, Call, GeneratorExp, comprehension`.
- Allowed calls: `sum len min max abs all any round`.
- Names come only from the evaluation context (the entity dicts, `response`, `global`).
- No dunder attributes, no other calls, no assignment. The expression length is capped at 500 characters. **It never uses `eval` or `exec`.**

## 7. Engine (deterministic)

### 7.1 Runner and generator
- `Runner(model, sandbox, seed, budget)` produces `Sequence = list[Step]`, where `Step = {action, actor, params, parallel?}`.
- Generation is a random walk with a `random.Random(seed + i)` per sequence. At each step it picks among actions whose `requires` are satisfied, weighted by `action.weight × strategist weight`. Params are drawn from the range, with a **30% chance** of an edge value. `ref` picks from the var pool. The length is 1–12 (the default max is 12).
- **Designed scenarios** from the Test Designer are run first, then mutated (insert/delete/duplicate a step, jitter params) and mixed in at 20%.
- Execution goes through `executor.py` (an async `httpx` client). Each sequence gets **fresh actors** and a fresh var pool.
- **Speed:** async, with N concurrent sequences (default 8, isolated by fresh entities). The state is read only for entities touched by the step.

### 7.2 Judge
After **every step**, it evaluates the rules in scope: state rules for the touched entities (and global ones), and response rules for matching actions. It returns `Violation{rule_id, step_index, entity, observed, expected_expr}` on the first failure. The Judge is the **only** component that can emit `violation.found`.

### 7.3 Isolation
- `fresh_entities` (default) creates new actors and entities per sequence, so there's no global reset and it's fast. Rules must be scoped to entities that the sequence created.
- `restart` restarts the sandbox with a fresh DB volume or temp file. It's slow and used only for replay and verification when the model demands it.

### 7.4 Shrinker
1. **Step shrinking:** ddmin (delta debugging) over the step list. Each candidate is re-executed **for real** on fresh entities. It keeps candidates that still break the **same rule**, and removes steps whose `requires` became unsatisfied (a repair pass).
2. **Value shrinking:** move each param toward its smallest or edge value while the failure persists.
3. It emits `shrink.step{steps_count}` on every improvement. The result is 1-minimal (removing any single step no longer fails).

### 7.5 Replayer
It runs the exact sequence N times (default 10) with fresh entities and reports `k/N`. If k < N, it's marked `flaky` (expected for races).

### 7.6 Test Runner
It runs the project's own test command (from `RepoSummary.test_command`, confirmed by the Mechanic) inside the sandbox and records the exit code and a summary.

### 7.7 Verifier
Verification passes only if all of these hold:
1. The exact counterexample now holds the rule (N/N).
2. The project's tests pass.
3. The native regression test passes.
4. A fresh search of `verify_budget` sequences (default 20,000 or 120 s, whichever comes first) with a new seed finds **no violation** of any approved rule.

### 7.8 Regression test export
It writes `rook/counterexamples/cx_NNN.json`, which holds the steps, rule, observed and expected values, the seed and the model hash. It asks the Surgeon (test-only edit scope) to write a **native** test in the repo's framework. The engine runs it **before the fix and it must fail**. If it can't validate the test, it falls back to a generated HTTP-level pytest file that replays the JSON.

## 8. Sandbox

`Sandbox` interface: `start(plan) -> base_url`, `stop()`, `restart()`, `exec(cmd) -> result`, `logs(tail)`.
- **DockerSandbox** (local CLI): uses `docker compose` or `docker build/run` from the SandboxPlan, inside a dedicated network. No host mounts except the workspace copy. There are CPU and memory limits, and a random published port on `127.0.0.1` only.
- **ProcessSandbox** (hosted server): only for **allowlisted demo repos** (`sandbox/allowlist.py`), which are pre-installed in the image. It starts the app as a subprocess on a free port with a temp database per run, and gets killed when the run ends.
- Health check: poll `health` until it returns 200, with a 60 s timeout.

## 9. Event stream (CONTRACT)

Envelope, one JSON object per event:
```json
{"v":1, "seq": 42, "ts": "2026-09-26T08:10:00.123Z", "run_id": "r_8f2c", "type": "agent.started", "data": {…}}
```
`seq` increases strictly per run. Clients resume with `?after=<seq>`.

| type | data |
|---|---|
| `run.created` | `{repo:{kind,ref,name}, request, options:{auto,budget}}` |
| `run.phase` | `{phase}` (section 4 names) |
| `agent.started` | `{agent, call_id, detail}` where `agent` is the agent id with underscores (e.g. `scout`, `rule_critic`; Bob mode slug is `rook-` + id with hyphens) |
| `agent.progress` | `{agent, call_id, detail}` |
| `agent.finished` | `{agent, call_id, ok, summary, cost, recorded}` |
| `engine.started` | `{worker, label}` where worker is one of `runner judge shrinker replayer testrunner verifier` |
| `engine.progress` | `{worker, pct, label, count?}` (throttled to 5/s) |
| `engine.finished` | `{worker, ok, summary}` |
| `question.asked` | `{question_id, kind: approve_rules\|fix\|pr\|setup_value\|menu\|repo, text, options:[{id,label}], payload}` |
| `question.answered` | `{question_id, answer, by: user\|auto}` |
| `repo.summary` | `RepoSummary` |
| `sandbox.ready` | `{base_url_redacted, mode}` |
| `model.actions` | `{actors[], actions[], state[]}` |
| `rules.proposed` | `{rules[]}` |
| `rules.reviewed` | `{verdicts[]}` |
| `rules.approved` | `{rule_ids[]}` |
| `search.progress` | `{sequences, per_sec, rules:{rule_id: holding\|broken}}` (throttled to 5/s) |
| `violation.found` | `{violation_id, rule_id, steps_count, observed}` |
| `shrink.step` | `{violation_id, steps_count}` |
| `counterexample.saved` | `{cx_id, rule_id, rule_text, steps[], observed, expected, reproduced:"10/10", flaky, test_path}` |
| `diagnosis.ready` | `{cx_id, file, line, explanation, reviewed:bool}` |
| `fix.ready` | `{cx_id, files[], diff, reviewed:bool}` |
| `verify.step` | `{cx_id, check: replay\|project_tests\|regression_test\|fresh_search, status: running\|passed\|failed, detail}` |
| `verify.done` | `{cx_id, verified, summary}` |
| `pr.opened` | `{url, number, branch}` |
| `chat.message` | `{role: user\|guide, text}` |
| `cost.update` | `{coins_total}` |
| `log` | `{level: info\|warn\|error, text}` |
| `run.finished` | `{status: done\|failed\|cancelled, summary}` |

## 10. Storage (SQLite)

```sql
runs(id TEXT PK, user_id TEXT, repo_kind TEXT, repo_ref TEXT, status TEXT, created_at TEXT, finished_at TEXT, coins REAL)
events(run_id TEXT, seq INTEGER, ts TEXT, type TEXT, data TEXT, PRIMARY KEY(run_id, seq))
counterexamples(id TEXT PK, run_id TEXT, rule_id TEXT, json TEXT, status TEXT)   -- open|fixed|verified
users(id TEXT PK, email TEXT, github_installation_id INTEGER, created_at TEXT)
guest_quota(key TEXT PK, day TEXT, runs INTEGER, coins REAL)
```

## 11. Server API (CONTRACT), base `/api/v1`

| Method | Path | Auth | Body → Response |
|---|---|---|---|
| GET | `/health` | none | → `{ok, version, bob_mode}` |
| GET | `/me` | user | → `{id, email, github_connected}` |
| GET | `/repos` | user or guest | → `[{kind: github\|demo, ref, name, private, language}]` (guests only see demo repos) |
| POST | `/runs` | user or guest | `{repo:{kind,ref}, request, options:{auto?:bool}}` → `{run_id}` (guest: demo repos only, quota) |
| GET | `/runs` | user or guest | → `[{id, repo, status, created_at, headline}]` |
| GET | `/runs/{id}` | owner | → `{run, counterexamples[]}` |
| GET | `/runs/{id}/events?after=N` | owner | → **SSE** `text/event-stream`, each `data:` is one envelope |
| POST | `/runs/{id}/answers` | owner | `{question_id, answer}` → `{ok}` |
| POST | `/runs/{id}/chat` | owner | `{text}` → `{ok}` (the answer arrives as events) |
| POST | `/runs/{id}/cancel` | owner | → `{ok}` |
| POST | `/counterexamples/{id}/replay` | owner | → `{run_id}` |
| GET | `/auth/cli/start?port=P&state=S` | none | redirects to Supabase Google OAuth |
| GET | `/auth/cli/callback` | none | redirects to `http://127.0.0.1:P/cb?token=…&state=S` |
| POST | `/auth/device/start` · `/auth/device/poll` | none | device-code flow |
| GET | `/github/install-url` | user | → `{url}` |
| GET | `/github/callback` | user | stores the `installation_id` |
| POST | `/github/token` | user | → a short-lived installation token for the CLI (scoped to the user's installation) |
| POST | `/github/webhook` | signature | installation events |

**Auth:** `Authorization: Bearer <Supabase JWT>` (the web app and the CLI), or a `rook_guest` signed cookie. Every run route checks the owner.

## 12. CLI architecture

- `rook` (no args) starts the **Textual app**. Other subcommands come from Typer.
- The TUI subscribes to the Session's event bus and renders:
  - `AgentSprite` widget: a 12×10 pixel sprite drawn with half-block characters `▀▄` in truecolor, which bounces, blinks and glances
  - `AgentRow`, which collapses into a one-line summary when finished
  - `EngineRow`: `■` plus a progress bar
  - `QuestionPrompt`: y/n/e and menus navigated with the arrow keys
  - `CounterexampleCard`
  - a status bar and an input box
- The chat input stays active while the search runs, and messages go to the Guide.
- The engine runs in a worker thread with its own asyncio loop. Events are posted to Textual with `call_from_thread`.
- Frame rate is 12 fps, and the sprite is static when `NO_MOTION` is set or reduced motion is on.

## 13. Web architecture

- Next.js App Router with these pages: `/` (home and composer), `/runs/[id]` (the chat column with cards), `/login`.
- `lib/events.ts` holds TS types that mirror section 9, and `lib/sse.ts` handles reconnecting to the SSE stream with `after`.
- `lib/runStore.ts` is a reducer from events to UI state, the **same logic** as the TUI.
- Components: `AgentSprite` (a canvas that ports the sprite shapes), `AgentRow`, `EngineRow`, `QuestionCard`, `RulesCard`, `SearchCard`, `CounterexampleCard`, `FixCard`, `VerifyCard`, `Sidebar`, `Composer`, `RepoPicker`.
- The browser talks **directly** to the Hugging Face API (`NEXT_PUBLIC_API_URL`). Vercel only serves the UI (to avoid function timeouts).

## 14. Deployment

| Piece | Where | Notes |
|---|---|---|
| Web | Vercel project `rook` | env: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| Server | Hugging Face Docker Space | image: Python 3.12, Node 22 + 24 (Bob), Go, the Bob Shell, and the 3 demo apps pre-built. `uvicorn rook.server.app:app --port 7860`. Secrets go in the Space settings: `BOB_API_KEY`, `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_URL`, `ROOK_DAILY_COIN_CAP` |
| Keep-alive | GitHub Actions cron hitting `/health` | only during judging |
| CLI | PyPI `rook-cli` | `uv tool install rook-cli` |

## 15. Testing strategy

- **Unit:** the expression evaluator, schema validation, the generator's determinism, ddmin, templating, the event bus, rails, BobClient parsing (against recorded NDJSON fixtures) and the API routes (with a FastAPI TestClient).
- **Engine integration (default suite):** against `tests/fixtures/minishop`, served **in-process** with `httpx.ASGITransport` (fast, no network). The engine must find the refund bug, shrink it to 3 steps, replay it 10/10, and verify after the fixture is patched.
- **Marked suites:** `-m docker` (DockerSandbox on the fixture), `-m bob` (live Bob calls, which cost coins, so run them manually).
- **Web:** vitest for the event reducer and components, plus `tsc --noEmit`.

## 16. Failure modes

| Failure | Behaviour |
|---|---|
| Bob returns invalid JSON | Retry with the error (up to 3), then the Coordinator decides, then tell the user |
| The app won't start | The Mechanic loops up to 3 times with the logs, then ASK setup_value or show a clear error |
| An action dry-run fails | Back to the Mapper with the HTTP response (up to 3). If it still fails, the action is disabled |
| A rule doesn't hold on a fresh app | The rule is rejected automatically as "wrong rule" before the human sees it |
| No violation within budget | Report "no counterexample in N sequences". The Coordinator may extend the budget once |
| A flaky counterexample | It's shown as `k/10 · flaky` and still reported. Races are expected to be flaky |
| Verification fails | Back to DIAGNOSE with the new evidence (up to 3), then report honestly |
| Bob is out of coins or hits the cap | Switch to recorded mode (labeled) or stop the AI phases. The engine still works |
