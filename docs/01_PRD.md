# 01 · Product Requirements Document: Rook

| | |
|---|---|
| Product | **Rook**, CLI command `rook` (working title was "Counterexample") |
| Tagline | **Find the smallest sequence that breaks your software, before your users do.** |
| One-liner | Bob finds the rules. The engine tries to break them. Proof decides. |
| Event | IBM Bob 2.0 Hackathon (lablab.ai), 25–27 Sep 2026. Deadline **27 Sep 15:00 UTC / 20:30 IST** |
| Owner | Aayush (solo) + 2 Claude Code accounts |
| Status | Design locked 26 Sep 2026. Build in progress (see `STATUS.md`) |

---

## 1. Problem

Developers test the scenarios they think of: buy an item, refund it, apply a coupon. Each test passes. Real, expensive bugs come from **unexpected sequences of valid actions**:

> Buy for ₹100 → refund ₹60 → refund ₹50 → the customer got **₹110** back on a ₹100 order.

Nobody wrote a test for that exact sequence. The code looks fine, and code review and AI reviewers say "looks correct" or "might have a bug". Neither gives proof.

**Who gets hurt:** fintech, e-commerce, SaaS billing and any API with money, stock, permissions or state machines. The results are money loss, negative stock, double refunds, permission bypasses and broken subscription state.

## 2. Solution

Rook reads a repository and uses **IBM Bob agents** to work out the business rules that must **always** hold (invariants). A human approves them. Then Rook's **deterministic engine** runs thousands of valid action sequences against the **real running app**, checks every rule after every step, and when a rule breaks:

1. **shrinks** the failing sequence to the smallest one (12 steps → 3)
2. **replays** it to prove it's real (10/10)
3. saves it as a **permanent regression test**
4. has Bob **diagnose** the root cause and **write the fix**
5. **verifies** the fix: exact replay + existing tests + a fresh search
6. opens a **pull request** with the evidence

**Principles** (these are non-negotiable):
1. **Proof over prediction.** Every finding is a reproducible execution, never "might fail".
2. **Minimal reproduction.** Always shrink to the smallest failing sequence.
3. **Bob thinks, the engine proves.** The LLM never judges pass or fail.
4. **Humans own the rules.** Bob proposes, the developer approves.
5. **Bob is central and meaningful.** 12 specialised Bob agents, not a thin wrapper.
6. **Build what really works.** No faked capabilities.

## 3. Users

| User | Need | How Rook helps |
|---|---|---|
| Backend developer (primary) | Catch logic bugs before release | `rook` in the terminal, every day |
| Team lead / reviewer | Stop regressions in pull requests | Rook runs in CI and comments the minimal steps |
| Developers using AI coding agents | Trust code they didn't write | Rook tries to break the agent's changes |
| QA / security engineer | Find permission and state bugs | Rule-based exploration of APIs |
| Hackathon judges | Try it in 2 minutes | Web app at a URL, with demo repos and no install |

## 4. Product surfaces

1. **`rook` CLI**: the **hero** of the product and the demo video. It's an interactive, Claude Code-style terminal session with an animated logo, sign-in, a chat prompt, slash commands and **animated agent characters** that appear while they work. It has non-interactive modes for CI.
2. **Web app**: must be fully working at a public URL. It uses a Claude Code web-style layout: sidebar with recents, a greeting, a composer with "Select repository…", and a chat column with the same agent characters. Results appear as inline cards, and questions become buttons.
3. **Backend**: one engine and one Bob agent system, shared by both surfaces.

## 5. The core flow (user journey)

1. **Install:** `pipx install rook-cli` or `uv tool install rook-cli`, then type `rook`.
2. **First run:** animated logo → **sign in with Google** in the browser → **connect GitHub** (a GitHub App; pick the repos, private repos work). The login is saved, so after that `rook` opens straight into the chat.
3. **Ask:** type "find bugs in my app", or use `/run`. Rook asks **which repo**: a local folder, a connected GitHub repo, or a pasted URL.
4. **Understand:** the **Scout** reads the repo, the **Mechanic** starts the app in a Docker sandbox, and the **Mapper** turns endpoints into actions and state readers.
5. **Rules:** the **Lawmaker** proposes rules with evidence, and the **Rule Critic** reviews them and rejects weak ones. **The user approves or edits** the rules, which are saved in `rook/` in the repo.
6. **Search** (in the background, and the user can keep chatting): the **Test Designer** writes targeted scenarios and the **Strategist** weights risky areas. The **Runner** executes random and designed sequences, and the **Judge** checks every rule after every step.
7. **Break found:** the **Shrinker** reduces it to the minimal sequence and the **Replayer** confirms it 10/10. It's saved as a counterexample plus a regression test.
8. **Diagnose:** the **Detective** finds the root cause, and the **Diagnosis Reviewer** checks it against the evidence.
9. **Fix:** after the user approves, the **Surgeon** writes the fix and the **Fix Reviewer** checks it.
10. **Verify:** the **Verifier** replays the counterexample, runs the existing tests and runs a fresh search. It's verified only if everything passes.
11. **Ship:** a **pull request** opens with the steps, the diagnosis, the fix, the test and the verification results.
12. **Chat any time:** the **Guide** answers questions like "what are you doing?" or "why did Docker fail?" from the live run data.

Rook **only stops for decisions**: missing setup values, approving rules, what to do after a bug, applying a fix and opening a PR. `rook --auto` skips the questions, and fixes still arrive as PRs for review.

## 6. Functional requirements

### 6.1 CLI (hero)
- **FR-C1** `rook` opens an interactive session: animated logo, auth check, chat input, slash commands (`/repo /rules /run /replay /explain /verify /dashboard /login /github /logout /help`) and plain-language requests routed to Bob.
- **FR-C2** Agent characters appear inline **only while working**. Each has its own shape and color and bounces, blinks and glances. Next to it: a shimmering verb, a timer and a live detail streamed from Bob (e.g. `reading src/refunds.js`). When done, it collapses to a one-line summary. Engine workers show `■` and progress bars, with no character.
- **FR-C3** The search runs in the background with a status bar. The user can chat while it runs.
- **FR-C4** Questions are shown inline (y/n/edit and menus navigated with the arrow keys).
- **FR-C5** Non-interactive commands: `rook run --ci` (exits non-zero on a broken rule), `rook replay <id>`, `rook explain <id>`, `rook verify <id>`, `rook init`, `rook serve`.
- **FR-C6** Sign-in: Google through the browser (localhost callback, device-code fallback). Credentials are saved in `~/.rook/`.
- **FR-C7** GitHub connect: install the GitHub App, then list repos, clone and open PRs.

### 6.2 Engine (proof)
- **FR-E1** Execute action sequences over **HTTP** against the sandboxed app. This works for any language.
- **FR-E2** Check every approved rule after every step with a **safe expression evaluator**.
- **FR-E3** Seeded, reproducible random search, mixed with Bob-designed scenarios and Strategist weights.
- **FR-E4** Isolate each sequence using fresh entities (new user, order and product) and/or a reset.
- **FR-E5** Shrink: delta-debugging on steps, then value shrinking, keeping the sequence valid.
- **FR-E6** Replay N times and report reproducibility (10/10, or "flaky").
- **FR-E7** Support concurrent step groups (for races like overselling the last item).
- **FR-E8** Save counterexamples (JSON) and a native regression test (Bob writes it, and the engine checks that it fails before the fix and passes after).
- **FR-E9** Verify: exact replay + the project's own test command + a fresh search with N sequences.
- **FR-E10** Run the target in a sandbox: **Docker** locally, and **process** mode for the allowlisted demo apps on the hosted server.

### 6.3 Bob agents (intelligence)
- **FR-B1** 12 Bob agents as Bob custom modes, each with its own role, inputs, JSON output schema and tool permissions (see `02_ARCHITECTURE.md`, section 5).
- **FR-B2** Every agent output is schema-validated and checked by the engine where possible. On failure, the agent retries with the error, up to 3 times.
- **FR-B3** The Coordinator (AI) picks the next step from an allowed set. **Rails** in code enforce: no code change without approval, no PR without verification, only the engine marks found/fixed, and retry caps.
- **FR-B4** Every Bob call is streamed live (tool use → UI detail), costed and recorded. **Recorded mode** replays saved real Bob answers, always labeled "recorded".

### 6.4 Web app
- **FR-W1** Claude Code web layout: sidebar (New run, Counterexamples, Rules, Repositories, Recents with status dots), greeting, composer with "Docker sandbox" and "Select repository…" chips.
- **FR-W2** A chat column with the same agent characters, engine progress rows and inline result cards: rules (approve/edit), live search, counterexample (shrink, steps, paid/refunded), fix (diff + apply), verification (before/after + PR link).
- **FR-W3** Questions become buttons.
- **FR-W4** Google sign-in and GitHub connect, plus a **"Try the demo"** guest mode with no login.
- **FR-W5** Live updates streamed from the backend over SSE.

### 6.5 Integrations
- **FR-I1** GitHub App: repo list, clone, branch, push, PR, PR comments.
- **FR-I2** A GitHub Action (`rook run --ci`) comments the minimal counterexample on PRs.

## 7. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | The engine runs at least 500 sequences per second on in-process test targets and at least 50 per second over HTTP to a local app |
| NFR-2 | The same seed gives the same sequences and the same verdicts |
| NFR-3 | Bob spend is at most about 1.5 coins per full run. There's a hard daily cap on the hosted server |
| NFR-4 | Untrusted code runs only inside the sandbox, and secrets never leave the server (see doc 03) |
| NFR-5 | The UI shows the first agent within 2 seconds of a request. Streaming latency is under 500 ms |
| NFR-6 | The hosted demo handles 3 concurrent runs, and more are queued |
| NFR-7 | It works in any modern truecolor terminal and respects reduced motion |

## 8. Demo scenario (the video's story)

1. The shop app looks fine and all its tests pass.
2. Run `rook`: the logo, then "find bugs in my app", pick `shop-app`.
3. The agents pop in: Scout, Mechanic, Mapper, Lawmaker. The Rule Critic rejects a weak rule. You approve.
4. Background search, with a question in the chat while it runs.
5. **RULE BROKEN** → shrink 12 → 8 → 5 → 3 → **Paid ₹100, Refunded ₹110** → 10/10 replay.
6. Detective → Surgeon → **FIX VERIFIED** (20,000 sequences, 0 broken) → PR.
7. Quick hits: stock goes negative (a race) and admin export reachable by a normal user, found by the same engine on a different app/language.
8. Close: the web app at the URL, then *"Don't ask AI if your code is correct. Make the code prove it."*

## 9. Demo target apps (built separately, spec later)

There are three small apps in **different languages**, each with realistic hidden bugs whose normal tests still pass:
1. `shop-app` (Node/Express): refund > paid, stock < 0 (race), cancelled order ships, normal user reaches admin export
2. `billing-service` (Python/FastAPI): a cancelled subscription still charges, credits consumed twice, a downgrade keeps paid features
3. `wallet-api` (Go): balance goes negative, a failed transfer still moves money, a self-transfer doubles money

## 10. Out of scope (for the hackathon)

- Languages or targets without an HTTP API (libraries, pure frontends, mobile, ML notebooks)
- Running arbitrary repos on the **hosted** server. The website runs only the allowlisted demo repos, while the CLI runs any repo locally.
- Multi-tenant team billing and enterprise SSO

## 11. Success metrics

- **Hackathon:** the full flow works live, end to end, on all 3 demo apps. Judges can use the URL without help. The video is under 5 minutes.
- **Product:** time to first counterexample under 3 minutes on a new repo. No false "rule broken" (every counterexample replays). At least 80% of Bob-proposed rules are accepted by a human.

## 12. Long-term direction (for the slides)

A GitHub App running on every PR · checking AI-generated code · enterprise policy rules ("support never reads payroll", "no cross-tenant access") · continuous invariant testing · a web IDE.
