# 04 · Frontend Specification: Rook

There are two surfaces over the same event stream (`02_ARCHITECTURE.md`, section 9):
**A. the `rook` CLI (the hero of the demo video)** and **B. the web app (must work at the public URL)**.
The approved visual references are in `docs/mockups/`. Open them in a browser; they are animated. They still say "Counterexample" / `cx`: read that as **Rook** / `rook`.

| Mockup | Shows |
|---|---|
| `2-terminal-session.html` | CLI first run: logo, sign-in, GitHub, repo menu, rules, background search with chat, fix, verify, PR |
| `3-agent-characters.html` | **Approved agent style**: characters appear inline in the chat only while working, then collapse |
| `4-web-app.html` | **Approved web layout** (Claude Code web style) |
| `1-walkthrough.html` | Early overview (the dashboard part is superseded by `4-web-app.html`) |

---

## 1. Shared design language

### 1.1 Voice and copy
- Short, plain and active. Name things from the user's side ("Approve 4 rules", "Fix it", "Open PR").
- Always show **proof**: numbers, steps and values ("Paid ₹100 · Refunded ₹110"). Never "might".
- Mark AI guesses as guesses ("Strategist: focus on refunds"). Only engine rows say BROKEN or VERIFIED.
- Label recorded Bob output with a small `recorded` tag.

### 1.2 Status semantics (both surfaces)
| State | Symbol | Color token |
|---|---|---|
| Working (Bob agent) | the agent's character, animated | the agent's color |
| Working (engine) | `■`, pulsing, with a progress bar | ink |
| Done / holding / passed | `✓` | green `#62D69B` (term) / `--good` |
| Broken / rejected / failed | `✗` | red `#FF7A70` / `--bad` |
| Waiting for the user | `?` | yellow `#E9C46A` / `--warn` |
| Not started | `·` | dim |

### 1.3 Agent characters (CONTRACT for both surfaces)
There is one sprite system, ported to Python (TUI) and TypeScript (web). The grid is **12 wide × 10 tall** pixels. In the terminal, each cell pair (top/bottom pixel) is drawn with half-block characters: `▀` with fg=top and bg=bottom, `▄`, or a space.

Shape masks (x in 0..11, y in 0..9; the reference implementation is in the mockup JS `SHAPES`):
- `circle`: (x−5.5)²+(y−4.8)² ≤ 4.9²
- `small`: (x−5.5)²+(y−6)² ≤ 3.6²
- `roundsq`: |dx|≤5, |dy|≤4.6, |dx|+|dy|≤8.2 (center 5.5, 4.8)
- `tilted`: roundsq rotated −14°, with |dx|≤4.4, |dy|≤4.1, |dx|+|dy|≤7.4
- `triangle`: |x−5.5| ≤ (y+0.6)·0.62, cutting corners where y≥9 and |dx|>4.6
- `cloud`: the union of circles (3.4,5.6,r3.1), (7.6,5.6,r3.1), (5.5,3.4,r3.1), (5.5,6.4,r3.2)
- `blob`: an ellipse with center (5.5,5.2), rx 5.6, ry 4.3

Eyes are two white columns at x = 4 + look and x = 7 + look, 2 pixels tall starting at the eye row (circle 3, small 5, roundsq 3, tilted 3, triangle 6, cloud 4, blob 4).

| Agent (event `agent`) | Name shown | Shape | Color | Verb |
|---|---|---|---|---|
| `coordinator` | Coordinator | circle | `#F5B400` | Planning |
| `scout` | Scout | roundsq | `#10B99A` | Scouting |
| `mechanic` | Mechanic | cloud | `#FF8A00` | Building |
| `mapper` | Mapper | blob | `#1FA8E0` | Mapping |
| `lawmaker` | Lawmaker | tilted | `#9B1FE8` | Drafting rules |
| `rule_critic` | Rule Critic | triangle | `#FF1493` | Reviewing rules |
| `test_designer` | Test Designer | blob | `#FF5A1F` | Designing tests |
| `strategist` | Strategist | circle | `#A86B3C` | Strategizing |
| `detective` | Detective | roundsq | `#4F63FF` | Investigating |
| `diag_reviewer` | Diagnosis Reviewer | triangle | `#F05FAA` | Checking evidence |
| `surgeon` | Surgeon | tilted | `#22B868` | Operating |
| `fix_reviewer` | Fix Reviewer | triangle | `#D6247A` | Reviewing fix |
| `guide` | Guide | small | `#8E99A6` (web) / `#E9ECEF` (term, dark eyes) | Answering |
| brand mascot | (none) | cloud | `#E0563F` | (none) |

Event slugs use underscores (`rule_critic`). Bob mode slugs use hyphens (`rook-rule-critic`). The mapping lives in `agents/registry.py`.

**Animation while working**, at about 12 fps:
- **Bounce:** the sprite shifts up by one half-cell (term) or 3px (web), toggling every ~0.75 s
- **Blink:** the eyes shrink to their bottom pixel for about 4 frames out of every ~70
- **Glance:** the eyes' x-offset cycles through `[0,0,1,1,0,0,-1,-1]` every ~1.8 s
- **Shimmer:** a bright highlight wave moves across the verb text

Each agent gets a random phase seed so that two agents never move in sync. With reduced motion (`NO_MOTION=1` or a TUI flag, or `prefers-reduced-motion` on the web), all of this is static.

**Agent row lifecycle:**
- `agent.started` shows the row: `[sprite] Name  Verb… (3.2s)` and on the next line `⎿ <detail>`
- `agent.progress` updates the detail
- `agent.finished` collapses the row to `● Name ✓ <summary>` (or `✗` if `ok=false` or the verdict is a rejection)

Several agents can be visible at once (parallel phases).

**Engine rows** (no character):
- `engine.started/progress` shows `■ Runner  ████░░░░ 1,700 sequences`
- `engine.finished` shows `■ Runner ✗ Rule broken · refunds ≤ paid · 3,412 sequences`

---

## 2. A. CLI (Textual)

### 2.1 Screens and flow
1. **Launch** (`rook`): the ASCII logo **ROOK** is drawn letter by letter in `#E0563F`, then the version and tagline.
2. **First-run setup** (only if there are no credentials): `1/2 Sign in with Google` (a spinner while waiting for the browser) → `✓ Signed in as <name> (Google)`, then `2/2 Connect GitHub` → `✓ GitHub connected · N repos shared`. It's skipped on later runs.
3. **Home:** a boxed welcome (`✻ Rook · signed in as … · GitHub connected`), then the input box `> ` with the placeholder *Try "find bugs in my app" or /help*. Footer: `? for shortcuts · <repo or none> · 0.00 coins`.
4. **Run:** the transcript grows downward. Agent rows, engine rows, question prompts and cards appear inline. While the engine searches, a **status bar** above the input shows `running ◐ Searching 2,140 sequences · 1,140/s · <current sequence>`.
5. **Idle after a run:** the input box, plus a footer such as `shop-app · 4 rules · 1 fix verified`.

### 2.2 Inline components
- **Menu question** (repo picker, "What next?"): a list with `❯` on the selection, navigated with ↑/↓ and Enter. After answering it collapses to `✓ <choice>`.
- **Confirm question:** `? Approve these 4 rules? (Y / n / e to edit one)`. The typed answer shows in green.
- **Setup value:** `? Your app needs PAYMENT_API_KEY. Use a fake payment server instead? (Y/n)`, or a masked text input.
- **Rules card:** a numbered list with rule text and a dim source (`src/refunds.js · README`), plus rejected rules struck through with the critic's reason.
- **Counterexample card:** a red border with the title `COUNTEREXAMPLE #001`, the numbered minimal steps, `Paid ₹100   Refunded ₹110 ✗ rule broken`, and `Replayed 10 / 10 on the real app ✓ real bug`.
- **Shrink line:** `Shrinking  12 → 8 → 5 → 4 → 3 steps`, animated as `shrink.step` events arrive.
- **Diagnosis card:** `Root cause src/refunds.js : 42`, an explanation, and a diff with red `-` and green `+` lines.
- **Verify block:** one line per check (`✓ Replay: second refund now rejected · refunded ₹60`, and so on), then `✓ FIX VERIFIED` in bold green.
- **PR line:** `✓ PR #88 opened · <url>`.

### 2.3 Input and keys
| Key | Action |
|---|---|
| Enter | send (or answer the current question) |
| ↑/↓ | move in menus, or input history when no menu is open |
| Esc | cancel the current question, or interrupt the run (with a confirmation) |
| Ctrl+C twice | quit |
| `?` in an empty input | show shortcuts |
| Tab | autocomplete slash commands |

### 2.4 Slash commands
`/run [repo]` · `/repo` · `/rules` · `/replay <cx>` · `/explain <cx>` · `/verify <cx>` · `/dashboard` (opens the web URL for this run) · `/login` · `/github` · `/logout` · `/auto on|off` · `/help`. Plain text goes to the Coordinator (if idle) or the Guide (if a run is active).

### 2.5 Terminal requirements
Needs truecolor. If it's not detected, it falls back to 256 colors and the sprites become a single colored `●`. Minimum width is 80 columns; below that, sprites are hidden and the rows stay.

### 2.6 Non-interactive output (`rook run --ci`)
Plain Rich output with no animation. It ends with a summary table, exit code 1 if any approved rule is broken, and it writes `rook-report.json` + `rook-report.md` for the GitHub Action comment.
Exit codes: `0` every approved rule held, `1` an approved rule is broken, `2` the run failed or was stopped before it could tell (or bad arguments). With `--auto` the Session answers its questions (the rails' auto answers). Without it, CI mode approves only critic-approved rules and never one flagged `already_broken`, answers "no" to fix and PR (it changes no code), picks "report"/"stop" in a menu, and stops on a setup value not given with `--setup NAME` (read from the env var `NAME`). `rook replay|verify <cx> --base-url` use the same 0/1/2 codes and accept only a loopback URL.

---

## 3. B. Web app (Next.js)

### 3.1 Layout (see `4-web-app.html`)
```
┌ Sidebar 260px ───────────┬ Main ─────────────────────────────────────────┐
│ [mascot] Rook            │  (home) mascot + "What should we try to break  │
│ [ Home | Runs ]          │   today?" + sub-line                           │
│ + New run                │  (run)  chat column, max-width 760px, centred  │
│ ▢ Counterexamples        │         user bubbles right, agents/cards left  │
│ ≡ Rules                  │                                                │
│ ⬡ Repositories           │                                                │
│ ⌄ More                   │  ┌ composer ─────────────────────────────────┐ │
│ Recents                  │  │ [Docker sandbox] [+ Select repository…]  🟠│ │
│ ● shop-app · finding…    │  │ Describe what to check, or "find bugs"  ↵ │ │
│ ● billing · 2 broken     │  │ + Auto-approve: off     Bob · 13 agents   │ │
│ …                        │  └───────────────────────────────────────────┘ │
│ [Add to CI]  A aayush ·  │                                                │
└──────────────────────────┴────────────────────────────────────────────────┘
```
- Under 820px the sidebar becomes a drawer (hamburger). The composer is sticky at the bottom.
- Recents dots: pulsing accent = running, green = fixed/holding, red = broken.

### 3.2 Pages
| Route | Content |
|---|---|
| `/` | Home: greeting + composer. Choosing a repo and sending creates a run → `/runs/[id]` |
| `/runs/[id]` | The live run: chat column rendered from the SSE events, with the composer active for chat |
| `/login` | "Continue with Google", "Try the demo without signing in" |
| `/counterexamples`, `/rules`, `/repositories` | Simple lists (lower priority) |

### 3.3 Repo picker
A dropdown above the composer with **"Your GitHub repositories"** (after connecting) and **"Demo repositories"** (always; the only option for guests). Each item shows its name, `private/public` and the language. If GitHub isn't connected, it offers a "Connect GitHub" item.

### 3.4 Inline cards (web versions of the CLI components)
- **RulesCard:** a header pill `Needs your OK` → `Approved`, rows with rule text + source + pill (`Approved` / `Rejected` with strike-through and reason), and buttons **Approve N rules** and **Edit**. Edit makes the text editable and requires re-validation.
- **SearchCard:** three stats (Sequences, Speed, Broken x/4) that update live, and the pill `Running` → `Rule broken`.
- **CounterexampleCard:** a red border, shrink chips `12 → 8 → 5 → 3` (the current one in red), the numbered steps, a **Paid / Refunded** duo (the red box is the violated value), the reproduced pill, and the buttons **Replay** and **Download test**.
- **FixCard:** the root cause file:line + explanation, a diff block, reviewer pills, and the buttons **Apply fix and verify** / **Not now**.
- **VerifyCard:** a Before (red) / After (green) duo, rows for each verify check with pills, and after `pr.opened` a **View pull request** button.
- **QuestionCard:** a generic card for `setup_value` and `menu` questions.

The question buttons send `POST /runs/{id}/answers`, and the card then shows `✓ <answer>`. In **guest demo mode**, unanswered questions auto-answer "yes" after 6 s with a visible countdown, so judges see the full flow.

### 3.5 Visual tokens
Default is dark, with a light theme via `prefers-color-scheme` and `[data-theme]`.

| Token | Dark | Light |
|---|---|---|
| `--page` | `#0B0B0B` | `#EDEFEE` |
| `--app` | `#1A1A1A` | `#F7F8F7` |
| `--side` | `#141414` | `#EEF0EF` |
| `--surface` | `#222222` | `#FFFFFF` |
| `--ink` | `#ECECEA` | `#1A1F1D` |
| `--muted` | `#A8A8A3` | `#5E6864` |
| `--line` | `#2E2E2E` | `#DCE1DE` |
| `--accent` (brand) | `#E0563F` | `#D9452F` |
| `--good` | `#6BD9A0` | `#1C8A55` |
| `--bad` | `#FF8C83` | `#C2372F` |
| `--warn` | `#E9C46A` | `#A86A12` |

Fonts: **Newsreader** (the greeting and wordmark only), **IBM Plex Sans** (UI) and **IBM Plex Mono** (code, numbers, details). Use tabular numbers for all counters.

### 3.6 States
- **Loading** a run: skeleton rows. **Reconnecting** the SSE: a thin banner "Reconnecting…" with a retry that resumes with `after`.
- **Errors:** an inline card with a clear cause and next step (for example: "The app didn't start: port 3000 never answered. Check the logs or edit the start command.").
- **Empty recents:** "No runs yet. Pick a repository to start."
- **Guest limits reached:** "Demo limit reached for today. Install the CLI to run on your own repos: `uv tool install rook-cli`."

### 3.7 Accessibility
Keyboard navigation for the composer, picker and buttons, with a visible focus ring. `aria-live="polite"` on the chat column. Color is never the only signal (there's always a ✓/✗/? plus text). Contrast is at least 4.5:1 for text.

---

## 4. Event → UI mapping (both surfaces)

| Event | CLI | Web |
|---|---|---|
| `agent.started/progress/finished` | AgentRow | AgentRow |
| `engine.*` | EngineRow | EngineRow |
| `question.asked` | inline prompt | QuestionCard / buttons on the related card |
| `rules.proposed` + `rules.reviewed` | Rules card | RulesCard |
| `search.progress` | status bar | SearchCard |
| `violation.found`, `shrink.step`, `counterexample.saved` | shrink line + Counterexample card | CounterexampleCard |
| `diagnosis.ready`, `fix.ready` | Diagnosis card | FixCard |
| `verify.step`, `verify.done` | verify block | VerifyCard |
| `pr.opened` | PR line | VerifyCard button + recents update |
| `chat.message` | `> text` (user) / `◆ Guide` line | bubbles |
| `cost.update` | footer coins | sidebar coins |
| `log` (warn/error) | dim or red line | small inline note |
