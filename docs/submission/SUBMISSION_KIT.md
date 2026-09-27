# Rook: hackathon submission kit

IBM Bob 2.0 Hackathon (lablab.ai). Deadline **27 Sep 2026, 20:30 IST (15:00 UTC)**.

Anything marked **[CONFIRM]** is a number or detail you must check before it goes into the video, deck or form. Everything else comes from the repo docs (`README.md`, `docs/01`–`04`, `STATUS.md`, `docs/demo-apps/`).

| Link | Value |
|---|---|
| Live web (guest demo, no sign-in) | https://rook-weld-six.vercel.app |
| API | https://44-239-185-88.sslip.io (health: `/api/v1/health`) |
| Repo | https://github.com/tony19053000/rook |
| CLI install | `uv tool install git+https://github.com/tony19053000/rook` |
| Demo apps | https://github.com/tony19053000/shop-app · https://github.com/tony19053000/billing-service · https://github.com/tony19053000/wallet-api |

---

## Before you record: two things to know

1. **To reach "Fixed and verified" on the web, approve only the main rule.** The rules card ticks every accepted rule by default, and the guest countdown sends that default. With every rule approved, the fix is made and reviewed, but VERIFY's fresh search then breaks one of the *other* planted bugs, so the run honestly ends `done` without a verified fix. For the video: pick **shop-app**, and on the rules card untick everything except **"Total refunds never exceed the amount paid"** (wording may differ slightly), then click **Approve 1 rule**. [CONFIRM on the live site before recording: the run ends with `✓ FIX VERIFIED` and the summary "Fixed and verified cx_001 …"]
2. **The hosted site runs in replay mode** (recorded Bob sessions, 0 coins). Agent rows show a small `recorded` tag. That is expected and honest; say it once in the voiceover (the script does).

---

## 1. Video script (4:55, about 560 words at ~130 wpm)

Record screen at 1920×1080, browser zoom 110–125% so cards are readable. Terminal: dark theme, at least 100 columns, font 16–18 pt.

| # | Time | On screen | Voiceover (exact) |
|---|---|---|---|
| 1 | 0:00–0:15 | Full-screen counterexample card from the web run: `buy(mug, ₹100)` → `refund(₹60)` → `refund(₹50)`, "Paid ₹100 · Refunded ₹110 ✗", "Replayed 10 / 10". Title overlay: **Rook**. | "A customer paid a hundred rupees and got a hundred and ten back. Three normal requests. Every unit test passed. This is Rook, and it found that bug by running it." (31) |
| 2 | 0:15–0:40 | shop-app repo on GitHub: README, then the `tests/` folder and a green `npm test` run. | "Developers test the cases they think of: buy, refund, cancel. The expensive bugs come from sequences nobody wrote a test for. Double refunds, negative stock, a cancelled order that still ships. Code review, and AI reviewers, can only say this might be wrong. That is a guess, not proof." (49) |
| 3 | 0:40–1:00 | Slide: "Bob thinks. The engine proves." Simple two-column graphic: left "IBM Bob agents: read code, propose rules, write fixes", right "Deterministic engine: run, judge, shrink, replay, verify". | "Rook splits the work. IBM Bob reads the code, proposes business rules and writes fixes. A deterministic engine runs real requests against the real app and decides what is broken. The language model never decides pass or fail." (38) |
| 4 | 1:00–1:25 | **Bob IDE clip.** [CONFIRM: use your real footage.] Suggested: Bob IDE open on the `rook` repo, showing `src/rook/agents/registry.py` (the 13 mode definitions) and asking Bob to explain or review one agent prompt; or Bob IDE on a demo app repo. Cut to a generated `.bob/custom_modes.yaml`. | "We built Rook with Bob IDE, and Rook runs on Bob Shell. Each of the thirteen agents is a Bob custom mode with its own role, JSON output schema and tool permissions. Every agent is read-only except two, and only the Surgeon can edit application code." (46) |
| 5 | 1:25–2:10 | **CLI clip.** Terminal: `rook` → ROOK logo draws → type `find bugs in my app` → pick the repo → Scout, Mechanic, Mapper appear as animated characters with live details (`reading src/…`) → Lawmaker proposes rules → Rule Critic rejects one (struck through with reason) → `? Approve these rules? (Y / n)` → `Y` → status bar "Searching … sequences". [CONFIRM which repo and mode you record; see §4, shots C3–C6.] | "This is the Rook command line. I ask it to find bugs. The Scout reads the repo, the Mechanic starts the app in a Docker sandbox, and the Mapper turns its HTTP API into actions. The Lawmaker proposes rules, each backed by evidence from the code. The Rule Critic challenges them and rejects a weak one. I approve the rest. Nothing runs against my rules until a human says yes. Now the search starts in the background, and I can keep chatting while it runs." (85) |
| 6 | 2:10–2:30 | Browser: https://rook-weld-six.vercel.app home, "What should we try to break today?". Open the repo picker: Demo repositories shop-app, billing-service, wallet-api, minishop. Pick **shop-app**, type "find bugs", send. | "The same core runs on the web, with no sign-in. I pick the shop app, a Node and Express store, and ask it to find bugs. This hosted demo replays recorded Bob sessions, so it costs nothing." (37) |
| 7 | 2:30–2:55 | Agent rows stream in with `recorded` tags. Rules card: untick all but the refund rule, click **Approve 1 rule**. SearchCard counts sequences live. | "Same agents, same rules card. I approve the refund rule. The engine now generates thousands of valid request sequences, runs each one on the live app, and checks every approved rule after every single step." (35) |
| 8 | 2:55–3:20 | SearchCard pill turns **Rule broken**. CounterexampleCard: shrink chips animate `12 → 8 → 5 → 3`, the three steps, Paid ₹100 / Refunded ₹110 in red, "Replayed 10 / 10". [CONFIRM the exact shrink chips shown on shop-app.] | "Rule broken. The failing run was long, so the engine shrinks it, step by step, until only the requests that matter are left. Then it replays that sequence ten times on a fresh app. Ten out of ten. This is a real bug, not a prediction." (46) |
| 9 | 3:20–3:45 | FixCard: root cause file and line, explanation, diff (refund check against `order.total` changed to the remaining amount), reviewer pills. Countdown or click **Apply fix and verify**. | "The Detective finds the root cause: each refund is checked against the order total, not what is left. A reviewer agent checks that diagnosis against the evidence. The Surgeon writes a regression test that fails, then a one-file fix, and the Fix Reviewer approves it." (45) |
| 10 | 3:45–4:05 | VerifyCard: Before (red) / After (green), rows: exact replay ✓, project tests ✓, regression test ✓, fresh search ✓, then **✓ FIX VERIFIED**. Run summary "Fixed and verified cx_001 …". | "Now the engine verifies. The exact counterexample must hold. The project's own tests must pass. The new regression test must pass. And a fresh search with a new seed must find no violation. Only then does Rook say fixed and verified." (41) |
| 11 | 4:05–4:20 | Quick cuts: billing-service (FastAPI) and wallet-api (Go) runs showing their counterexample cards: credits consumed twice; balance goes negative. | "The engine only speaks HTTP, so language does not matter. The same flow finds credits consumed twice in a Python billing service, and a negative wallet balance in a Go API." (31) |
| 12 | 4:20–4:35 | GitHub: a `rook/fix-*` pull request with steps, diagnosis and verification in the body [CONFIRM a real PR exists; if not, show `action.yml` and the README "GitHub Action" section instead]. | "From the CLI, Rook pushes a fix branch and opens a pull request with the evidence. It never touches your main branch. A GitHub Action runs it on every pull request." (32) |
| 13 | 4:35–4:47 | Slide: security + cost bullets (sandbox, no eval, secrets never in git, ~3 of 40 Bobcoins). | "Apps run in a sandbox, Bob's output is never executed, and recorded sessions kept our Bob spend to about three of forty coins." (23) |
| 14 | 4:47–4:55 | Closing card: Rook logo, URL, repo link. | "Don't ask AI if your code is correct. Make the code prove it. Rook." (14) |

Voiceover total: about 560 words, which is about 4:20 of speech at 130 wpm; the remaining ~35 s is room for card animations and pauses. Each row's words fit its time slot at 130 wpm. Keep the final cut under 5:00.

**Editing notes**
- Speed up long waits (search, shrinking) 2–4×, but never speed up the counterexample card or the VERIFIED moment.
- Keep the `recorded` tag visible in at least one web shot. Don't crop it out.
- Add lower-third captions for each agent name the first time it appears (Scout, Mechanic, Mapper, Lawmaker, Rule Critic, Detective, Diagnosis Reviewer, Surgeon, Fix Reviewer).
- Export MP4, H.264, 1080p, under 5:00.

---

## 2. Slide deck outline (12 slides)

Fonts to match the web app: Newsreader for titles, IBM Plex Sans for body, IBM Plex Mono for code and numbers. Dark background `#0B0B0B`, accent `#E0563F`, good `#6BD9A0`, bad `#FF8C83`.

### Slide 1: Rook
- Find the smallest sequence that breaks your software, before your users do.
- 13 IBM Bob agents propose; a deterministic engine proves.
- Live: rook-weld-six.vercel.app · github.com/tony19053000/rook
- IBM Bob 2.0 Hackathon, lablab.ai, Sep 2026

**Speaker note:** Rook finds business-rule bugs by running them, shrinks them to the smallest failing sequence, fixes them with Bob and proves the fix.
**Visual:** The brand mascot (orange cloud sprite) plus the counterexample card: Paid ₹100 · Refunded ₹110 ✗.

### Slide 2: The problem
- Unit tests cover the scenarios you thought of.
- Costly bugs come from unexpected sequences of valid actions: double refunds, negative stock, permission bypasses, broken subscription state.
- Example: buy ₹100 → refund ₹60 → refund ₹50 → customer gets ₹110 back.
- Code review and AI reviewers say "looks correct" or "might have a bug". Neither is proof.

**Speaker note:** Each request is valid on its own. The bug only exists in the sequence, and nobody writes a test for that exact sequence.
**Visual:** Three request chips in a row, then a red total. Next to it, a grey speech bubble "This might have a bug" crossed out.

### Slide 3: The insight: proof over prediction
- Bob thinks, the engine proves.
- Every finding is a reproducible execution on the real running app, never "might fail".
- Always shrink to the minimal failing sequence.
- Humans own the rules: Bob proposes, the developer approves.

**Speaker note:** The LLM never judges pass or fail. Only the engine's Judge can emit "rule broken", and only the Verifier can say "verified". This is enforced in code (rails), not in a prompt.
**Visual:** Split panel. Left "IBM Bob: understand, propose, explain, fix". Right "Engine: run, judge, shrink, replay, verify". An arrow labelled "proposals" goes left to right; an arrow labelled "verdicts" comes back.

### Slide 4: How it works
- Understand: Scout reads the repo, Mechanic starts the app in a sandbox, Mapper turns the HTTP API into actions.
- Rules: Lawmaker proposes invariants with code evidence, Rule Critic challenges them, the human approves.
- Break: the engine runs thousands of valid action sequences and checks every rule after every step.
- Shrink and prove: delta debugging to a 1-minimal sequence, replayed 10/10, saved as a regression test.
- Fix and verify: Detective + Diagnosis Reviewer, Surgeon + Fix Reviewer, then exact replay + project tests + regression test + fresh search.

**Speaker note:** The Coordinator agent picks the next step only at branch points and only from an allowed set. Rails in code block any fix without approval and any PR without verification.
**Visual:** Left-to-right flow diagram (from the README mermaid): Repo → Bob agents → Human approves rules → Engine search → Shrink → Replay 10/10 → Bob diagnose + fix → Engine verify → PR with evidence. Colour Bob boxes with agent colours, engine boxes in white with a `■` mark.

### Slide 5: How IBM Bob is used
- 13 agents, each a Bob Shell custom mode (`.bob/custom_modes.yaml`), called with `bob run --mode <slug> --format stream-json`.
- Coordinator + 12 specialists: Scout, Mechanic, Mapper, Lawmaker, Rule Critic, Test Designer, Strategist, Detective, Diagnosis Reviewer, Surgeon, Fix Reviewer, Guide.
- Per-agent tool permissions: all read-only except Mechanic (sandbox files) and Surgeon (only the diagnosed file and its test).
- Bob's stream-json output drives the live UI (`reading src/refunds.js`); every call is costed and recorded for replay.
- Bob IDE used during development [CONFIRM: one line on what you used it for].

**Speaker note:** Bob is the only AI in the system. Every agent must return one JSON block that matches a pydantic schema; invalid output is retried with the error, up to 3 times.
**Visual:** Grid of the 13 agent sprites with name and role (shapes and colours from `docs/04_FRONTEND_SPEC.md` §1.3), plus a small code box showing a `customModes:` YAML entry. Add a Bob IDE screenshot in the corner.

### Slide 6: Demo: the web app
- Guest demo, no sign-in: pick a demo repo and ask "find bugs".
- Rules card → live search → counterexample card → fix card → verify card.
- Hosted runs replay recorded Bob sessions: 0 coins per run, labelled `recorded`.
- Four demo apps: shop-app (Node/Express), billing-service (FastAPI), wallet-api (Go), minishop (Python).

**Speaker note:** The hosted server only runs allowlisted demo repos pinned by commit SHA. Your own repos run with the CLI.
**Visual:** 2×2 grid of screenshots W3, W5, W6, W7 from §4.

### Slide 7: Demo: the CLI
- `rook` opens an interactive session with animated agent characters.
- The search runs in the background; you can chat with the Guide while it runs.
- `rook run <repo> --ci` exits 1 if an approved rule breaks.
- `rook replay`, `rook explain`, `rook verify`, `rook init`, `rook serve`.

**Speaker note:** The CLI runs any repo with an HTTP API locally in a Docker sandbox. It is the main product surface; the web app shows the same event stream.
**Visual:** Screenshots C3 (agents working) and C6 (counterexample card in the terminal), side by side.

### Slide 8: Security
- Target apps run in a sandbox: Docker locally (non-root, cap-drop ALL, 127.0.0.1 only); allowlisted demo repos only on the hosted server.
- Bob output is never executed: rules go through a safe AST expression evaluator, actions are declarative HTTP templates.
- The engine only calls the sandbox's base URL (no SSRF); prompts mark repo content as untrusted data.
- Secrets never in git, logs, events or prompts; a redaction filter scrubs known patterns.
- Only the Surgeon edits code, only in a workspace copy, only after approval; a path guard reverts anything else. Never pushes to the default branch.

**Speaker note:** Rook runs other people's code and can open PRs, so the threat model covers host attack, prompt injection, SSRF, secret leaks and unreviewed pushes (`docs/03_SECURITY_ACCESS.md`).
**Visual:** Layered diagram: web → Vercel proxy → Caddy → Rook server → sandboxed app, with a lock icon at each boundary.

### Slide 9: Results
- 4 demo apps in 3 languages, 14 planted bugs, each app's normal tests pass (shop-app 4, billing-service 3, wallet-api 3, minishop 4).
- Refund bug: shrunk to the minimal sequence and replayed 10/10; verified by a fresh search (default 20,000 sequences or 120 s).
- Test Designer scenarios found the minishop refund bug in 5 sequences vs 1,903 with random search alone (5 seeds).
- Rule Critic: 9 of 10 Bob-proposed rules accepted on the fixed minishop.
- Total Bob spend about 2.8–3 of 40 Bobcoins [CONFIRM final]; hosted runs cost 0. Test suite: 1,467 Python + 210 web tests [CONFIRM final counts].

**Speaker note:** The shop-app refund, billing-service credits and wallet-api negative balance are each found, fixed and verified on the hosted demo from recordings [CONFIRM all three reach "Fixed and verified" on the live site]. Engine speed is about 268 sequences/s in-process on minishop [CONFIRM if you want to quote it; the target was 500].
**Visual:** Four big-number tiles (10/10 replay · 5 vs 1,903 sequences · ~3 of 40 coins · 4 apps / 3 languages), plus a small table of the planted bugs per app.

### Slide 10: Who uses it and why
- Backend developers: catch logic bugs before release, in the terminal.
- Team leads: the GitHub Action stops regressions in PRs and comments the minimal steps.
- Teams using AI coding agents: Rook tries to break code they didn't write.
- QA and security engineers: rule-based exploration of permission and state bugs.
- Fit: fintech, e-commerce, SaaS billing, any API with money, stock, permissions or state machines.

**Speaker note:** The cost of a double refund or a permission bypass in production is much higher than a CI job. Every finding arrives with a replayable test and a verified fix, so it saves review time too.
**Visual:** Four persona cards with one-line outcomes.

### Slide 11: Roadmap
- GitHub App running on every PR, with the counterexample and a fix PR.
- Checking AI-generated code as it lands.
- Enterprise policy rules: "support never reads payroll", "no cross-tenant access".
- Continuous invariant testing against staging.
- Near term: PyPI release, live Bob mode on the hosted server and in the GitHub Action.

**Speaker note:** From `docs/01_PRD.md` §12 plus the open follow-ups in `STATUS.md`. Nothing on this slide is shipped yet except what the previous slides show.
**Visual:** Simple three-column timeline: Now / Next / Later.

### Slide 12: Team and links
- Aayush Kumar, solo builder [CONFIRM name and role as you want them shown].
- Live: https://rook-weld-six.vercel.app
- Code: https://github.com/tony19053000/rook (MIT)
- CLI: `uv tool install git+https://github.com/tony19053000/rook`
- "Don't ask AI if your code is correct. Make the code prove it."

**Speaker note:** Invite judges to click "Try the demo": no sign-in, about a minute to a verified fix [CONFIRM timing on the live site].
**Visual:** QR code for the live URL, repo link, mascot.

---

## 3. lablab.ai submission fields

**Project title:** Rook: proof, not predictions, for your app's business rules

**Short description (≤255 chars):**
> Rook uses 13 IBM Bob agents to find your API's business rules. A deterministic engine breaks them with a minimal failing sequence, Bob writes the fix, and the engine proves it by replay, tests and a fresh search.

(212 characters.)

**Long description (~250 words):**
> Unit tests cover the scenarios developers think of. Costly bugs come from sequences nobody tested: two partial refunds that add up to more than the order, stock going negative under concurrent orders, a cancelled subscription that still renews. Code review and AI reviewers can only say "this might be wrong".
>
> Rook runs the bug instead. Thirteen IBM Bob agents, each a Bob Shell custom mode with its own schema and tool permissions, read the repository, start the app in a sandbox, map its HTTP API into actions and propose business rules backed by code evidence. A Rule Critic agent challenges them, and a human approves them.
>
> A deterministic engine then runs thousands of valid action sequences against the real running app and checks every rule after every step, using a safe expression evaluator. When a rule breaks, it shrinks the run to the minimal failing sequence, replays it 10/10 and saves it as a regression test. Bob agents diagnose the root cause and write a one-file fix, each step checked by a reviewer agent. The fix counts only when the engine confirms the exact replay, the project's tests, the regression test and a fresh search all pass. The language model never decides pass or fail.
>
> Rook works with any backend that has an HTTP API. The demo covers a Node/Express shop, a FastAPI billing service and a Go wallet API. Use it from the `rook` CLI, the web app (guest demo, no sign-in) or a GitHub Action on pull requests; the GitHub App opens a PR with the evidence. Recorded Bob sessions kept total spend to about 3 of 40 Bobcoins.

(about 270 words; trim the last sentence if the form is strict)

**Tags / technologies:** IBM Bob, Bob Shell, Bob IDE, AI agents, multi-agent, Python, FastAPI, Pydantic, Textual, Typer, Next.js, TypeScript, Tailwind CSS, Docker, SQLite, Supabase, GitHub App, GitHub Actions, Vercel, AWS EC2, Caddy, property-based testing, invariant testing, delta debugging, developer tools, API testing.

**Links checklist**
- [ ] Application URL: https://rook-weld-six.vercel.app (open in a private window; "Try the demo" works with no sign-in)
- [ ] Video (MP4, ≤5:00): upload, then paste the link; also replace `<VIDEO_URL>` in `README.md`
- [ ] Slide deck (PDF): export from the deck tool, upload; also replace `<DECK_URL>` in `README.md`
- [ ] Public GitHub repo: https://github.com/tony19053000/rook (check it is public and the README renders)
- [ ] Demo app repos linked in the long description or README (optional): shop-app, billing-service, wallet-api
- [ ] Bob IDE usage shown in the video (shot 4) and on slide 5
- [ ] Cover image / thumbnail: screenshot W7 (VerifyCard with FIX VERIFIED) or W5 (counterexample card)

---

## 4. Screens to capture

Capture at 1920×1080. For the web, use a fresh private window so you are a guest (guest limit: 3 runs a day per browser, 10 per IP, so plan your takes).

### Web (https://rook-weld-six.vercel.app)

| ID | Screen | How to get it |
|---|---|---|
| W1 | Home greeting + "Try the demo" | Open https://rook-weld-six.vercel.app in a private window |
| W2 | Repo picker open, "Demo repositories" listing shop-app, billing-service, wallet-api, minishop | Click "Select repository…" in the composer |
| W3 | Agent rows streaming (Scout, Mechanic, Mapper) with `recorded` tags | Pick shop-app, type `find bugs`, send; capture in the first ~20 s |
| W4 | RulesCard with checkboxes, a rejected rule struck through, "Approve 1 rule" | Untick all but the refund rule before the countdown ends |
| W5 | SearchCard "Rule broken" + CounterexampleCard (shrink chips, steps, Paid/Refunded, 10/10) | Same run, after approval |
| W6 | FixCard: root cause file:line, diff, reviewer pills | Same run |
| W7 | VerifyCard: Before/After, four check rows, `✓ FIX VERIFIED`, summary "Fixed and verified …" | Same run, at the end |
| W8 | Counterexample cards for billing-service and wallet-api | New runs: pick each repo, approve only its main rule (billing-service: credit balance matches grants minus usage; wallet-api: balance never negative) |
| W9 | Sidebar recents with status dots, `/runs` list | https://rook-weld-six.vercel.app/runs |
| W10 | Login page with "Continue with Google" and "Try the demo without signing in" | https://rook-weld-six.vercel.app/login |
| W11 | API health (optional, for the architecture slide) | https://rook-weld-six.vercel.app/api/v1/health (should show `"proxied": true`) |

### CLI (terminal)

Setup: `uv tool install git+https://github.com/tony19053000/rook`, Docker running, and for live Bob: `export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH; source ~/.bob-key.env`. A live run on a new repo spends coins (per-run budget 1.5); for 0 coins, record in replay mode against recorded sessions. [CONFIRM which repo and `ROOK_BOB_MODE` you use; a live run shows no `recorded` tag.]

| ID | Screen | Command |
|---|---|---|
| C1 | Help output | `rook --help` |
| C2 | Logo animation + home box | `rook` |
| C3 | Agents working (sprites, live details) | In `rook`: `find bugs in my app`, then pick the repo (e.g. a local clone of `tony19053000/shop-app`) |
| C4 | Rules card + critic rejection + `? Approve these rules? (Y / n)` | Same session |
| C5 | Background search status bar + chat with the Guide | Same session; type `what are you doing?` while it searches |
| C6 | Shrink line `12 → … → 3` + COUNTEREXAMPLE card + `Replayed 10 / 10` | Same session |
| C7 | Diagnosis card, diff, `✓ FIX VERIFIED` | Same session, answer yes to fix |
| C8 | CI mode summary and exit code | `rook run <repo> --ci; echo "exit $?"` |
| C9 | Plain-words explanation | `rook explain <cx-id>` (cx id from C6, e.g. `cx_001`) |
| C10 | Files Rook adds | `ls rook/ rook/counterexamples/` and `cat rook/rook.yaml` in the workspace |

### Bob (mandatory)

| ID | Screen | How |
|---|---|---|
| B1 | Bob IDE in use during development | Your own recording [CONFIRM what you show]; e.g. Bob IDE on the `rook` repo with `src/rook/agents/registry.py` open, asking Bob about an agent |
| B2 | The generated custom modes | `cat ~/.rook/workspaces/<run>/.bob/custom_modes.yaml` after a CLI run (shows `slug: rook-scout`, `groups: [read]`, the Surgeon's `edit` `fileRegex`) |
| B3 | Agent registry in code | `src/rook/agents/registry.py` in your editor |

### GitHub

| ID | Screen | URL / command |
|---|---|---|
| G1 | Repo landing page + README | https://github.com/tony19053000/rook |
| G2 | Fix PR with evidence (branch `rook/fix-*`) | [CONFIRM a real PR exists; ROOK-031's live PR test was pending a redeploy] From the CLI: `rook login`, then `rook run tony19053000/shop-app` and approve the PR |
| G3 | GitHub Action definition | https://github.com/tony19053000/rook/blob/main/action.yml |
| G4 | A demo app's green tests (to show "tests pass, bug still there") | `cd shop-app && npm test` (shop-app), `uv run pytest` (billing-service), `go test ./...` (wallet-api) |
