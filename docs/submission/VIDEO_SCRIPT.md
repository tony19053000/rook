# Rook: launch video script and production prompt

Length: **2:50** (hard limit 5:00). Format: 1920×1080, 30 fps, MP4.
Structure: a motion-graphics shell (intro, explainers, outro) wrapped around a **real, unedited-in-substance CLI run** on `shop-app` (sped up where it waits). The CLI is the hero. The web app appears once, near the end.

Facts used in this video (all true, keep them exact):
- Rook = IBM Bob agents + a deterministic engine. **Only the engine decides pass/fail.** 13 Bob agents, each a Bob Shell custom mode.
- Demo repo: `tony19053000/shop-app` (Node/Express + SQLite). Planted bug: refunds are checked against the order total, not what is still refundable, so a cancelled order can be refunded again.
- Rule: `order.refunded_total <= order.total`. Counterexample: create_product → place_order → cancel_order → refund_order(100). Refunded 200 on a 100 order.
- Root cause: `src/routes/orders.js:264`. Fix: compare against `order.total - order.refundedTotal`.
- VERIFY = 4 engine checks: exact replay 10/10, project tests, new regression test, fresh search with a new seed. Only then "Fixed and verified", then a PR on branch `rook/fix-cx-001`.
- Apps run in a Docker sandbox; Bob output is never executed; secrets never in git.
- Web: https://rook-weld-six.vercel.app · Repo: https://github.com/tony19053000/rook
- Bob usage: about 14 of 40 Bobcoins for the whole build, thanks to record/replay.

---

## Part A: record the real CLI run (do this first, ~15 min)

1. **Clean clone** of the demo app:
   ```bash
   rm -rf ~/demo && mkdir -p ~/demo && git clone -q https://github.com/tony19053000/shop-app ~/demo/shop-app
   ```
2. **Terminal setup:** one terminal, full screen (F11), dark theme, font ~16–18 pt, nothing else on screen. Close notifications.
3. **Env** (in that terminal):
   ```bash
   cd ~/Desktop/Counterexample
   source ~/.bob-key.env
   export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH
   clear
   ```
4. **Start the screen recording** from a second terminal (it records the whole screen; stop with `q` in that terminal):
   ```bash
   ffmpeg -y -f x11grab -framerate 30 -video_size 1920x1080 -i :0.0 -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p ~/Videos/rook-cli-real.mp4
   ```
5. Switch back to the full-screen terminal and run (interactive, **no** `--auto`):
   ```bash
   uv run rook run ~/demo/shop-app --request "find refund and order bugs"
   ```
6. **During the run:**
   - Let Scout / Mechanic / Mapper finish (the Docker build takes a minute the first time).
   - At the rules card: **approve only the refund rule** (the one about refunded total vs order total). Untick weak or wrong ones (e.g. "cancel a shipped order should succeed"). A human choosing rules is part of the story.
   - Say **yes** to the fix and to the PR/commit prompt.
   - Wait for the verify card and the final summary. Expect 5–12 minutes and ~1–1.5 Bobcoins.
7. Stop ffmpeg with `q`. Keep the file even if something odd happens: honest footage beats a perfect fake. If the run ends "not verified", we cut to that honestly and it still shows the engine refusing a bad fix.

What the editor needs from this file (timecodes you note while recording help): the command typed · agents appearing · rules card + your approval · "Rule broken" · the shrunk counterexample · the diagnosis · the diff · the verify checks · the final summary.

---

## Part B: style bible

**Palette** (Rook's own, from the web app): stage `#1A1918`, panel `#262624`, raised `#30302E`, hairline `#3A3936`, ink `#F0EEE6`, muted `#A8A59B`, Rook red `#E0563F`, proof green `#6BD9A0`, break red `#FF8C83`, amber `#E9C46A`. Agent colours: Scout `#5EC8B8`, Mechanic `#F0A060`, Mapper `#7FB2F0`, Lawmaker `#C98BF0`, Rule Critic `#F08BB8`, Detective `#A98BF0`, Surgeon `#6BD9A0`.

**Type:** Newsreader (serif) for statements and the wordmark · IBM Plex Sans for labels · IBM Plex Mono for terminal and code. Big statements are sentence case, never all caps. Labels: small caps-style uppercase with 0.14em tracking.

**Motion language:**
- One camera. Everything lives on one infinite dark plane; we move the camera (push, pan, rack focus) instead of cutting, except the two hard cuts marked below.
- Easing: expo-out for entrances (fast in, soft settle), power2-inOut for camera moves, springy back-out only for the agent characters and checkmarks.
- Depth: 3 layers. Background (slow drifting grain + faint red/green light blooms), midground (terminal / cards), foreground (kinetic type, flares). Parallax on every camera move.
- Rhythm: a beat every ~0.5 s during montage sections, long holds (2–3 s) only on proof moments (the broken rule, the 4-step counterexample, "Fix verified").
- Kinetic type: words enter per word or per character with 30–40 ms stagger, slight y-offset + blur-to-sharp.
- Real CLI footage always sits inside a floating terminal frame (22 px radius, soft shadow, subtle reflection), never raw full-screen. Speed it up 4–12× during waits with a small "×8" speed tag in the corner; return to 1× for the key moments.
- Proof moments get a "lock-on" treatment: the camera pushes in, the background dims to 40%, a thin red (break) or green (proof) outline traces around the element, a soft glow pulses once.

**Sound design:** a minimal, modern electronic bed (~100 BPM, warm synth pads + tight percussion), ducked under the voiceover. SFX: soft keyboard ticks on typing, a low "thud + glitch" on "Rule broken", rising whoosh on camera pushes, crisp "tick" per green check, a warm major chord on "Fix verified". No stock "tech" beeps.

**Voice:** calm, confident, slightly fast (≈150 wpm). Short sentences. No hype words.

---

## Part C: shot-by-shot script

`[MG]` = motion graphics built from scratch. `[REAL]` = the real CLI recording from Part A, placed in the floating terminal frame. Timecodes are targets.

### 1 · Cold open: the bug (0:00–0:14) [MG]
- Pure black. A single blinking caret, centre. SFX: room tone.
- Three HTTP calls type in, one per beat, mono, left-aligned in the centre column:
  `POST /orders {total: 100}` → `201` (green) · `POST /orders/7/cancel` → `200` · `POST /orders/7/refund {amount: 100}` → `200`.
- Each status code pops with a tiny scale bounce. On the third, the camera slowly dollies in.
- A ledger slides up beneath: "Order total ₹100". A counter "Refunded" spins 0 → 100 → **200**, the digits flip like a split-flap board, the number turns break-red and gets a red underline trace.
- Beat. Top right, a small green badge fades in: "✓ 14/14 tests passing". It flickers once, like it's lying.
- **VO:** "Three normal requests. The customer paid a hundred, and got two hundred back. And every test still passes."

### 2 · The thesis (0:14–0:30) [MG]
- The ledger shatters into particles that drift up and re-form as the line **"AI reviewers guess."** (serif, 140 px, muted ink).
- Under it, three chat-bubble fragments float by at different depths with real-sounding hedges: "this *might* be wrong…", "*possibly* a race…", "*consider* checking…". They blur and fade.
- A break-red pen stroke strikes "guess." The word flips (3D card flip on the x-axis) into **"Rook proves."**, "proves" in italic Rook red.
- Hard cut to black, then the logo build: the rook glyph assembles from 5 extruded blocks (bottom up, springy), the wordmark "Rook" writes on letter by letter, tagline fades in: "Proof over prediction · powered by IBM Bob".
- **VO:** "AI reviewers can only say: this might be wrong. That's a guess. Rook doesn't guess. It proves."

### 3 · How it works in 10 seconds (0:30–0:44) [MG]
- The logo slides left and becomes the hub of a clean diagram drawn with animated strokes:
  left column "IBM Bob · 13 agents" (thinks: reads code, proposes rules, writes fixes),
  right column "Engine · deterministic" (runs, judges, shrinks, replays, verifies).
- A glowing packet travels left → right ("rules") and right → left ("counterexample"), twice, looping.
- A stamp slams onto the engine side: **"Only the engine decides pass or fail."**
- **VO:** "Rook splits the work. IBM Bob's agents read your code and propose rules. A deterministic engine runs your real app and decides what's broken. The model never grades itself."

### 4 · The hero: the real CLI (0:44–1:10) [REAL + MG overlays]
- The diagram folds away; the camera flies into a floating terminal. Inside it: **the real recording**, starting with the typed command `uv run rook run ~/demo/shop-app`.
- Speed ×1 for the command, ×8 while Scout / Mechanic / Mapper work (speed tag in the corner).
- Each time an agent line appears in the real footage, an MG **agent card** pops out beside the terminal (springy): a coloured blob character with eyes, its name, a one-line job: Scout "reads the repo", Mechanic "starts it in a Docker sandbox", Mapper "turns the API into actions". Cards stack, then collapse into small chips along the top.
- Lower-third: "Real run · shop-app · Node/Express · live IBM Bob".
- **VO:** "Here's a real run. One command. The Scout reads the repo. The Mechanic starts the app in a Docker sandbox. The Mapper turns its API into actions Rook can call."

### 5 · Rules and the human (1:10–1:28) [REAL]
- Camera pushes into the rules card of the real footage (lock-on treatment). A Rule Critic rejection is circled in red; the approved refund rule is highlighted in green.
- MG callout draws from the approved rule: "refunded total ≤ order total".
- The real keystroke approving the rules gets a subtle keycap overlay (↵).
- **VO:** "The Lawmaker proposes business rules straight from the code. The Rule Critic throws out weak ones. And nothing runs until a human approves."

### 6 · The break (1:28–1:50) [REAL + MG]
- Real footage at ×12 while the search runs; an MG counter in the corner mirrors "sequences" climbing.
- The moment the real terminal shows the violation: freeze-frame, chromatic-aberration glitch (3 frames), SFX thud. Giant serif **"Rule broken."** slams in across the frame in break red, then shrinks into a pill that docks on the terminal.
- The shrink: MG strip of chips `11 → 7 → 4` compressing like an accordion, then the 4 real steps appear large, one per beat:
  `create_product` · `place_order` · `cancel_order` · `refund_order(100)`.
- Ledger returns: Total 100 · Refunded **200** · "Replayed 10/10 · real bug" stamp in green.
- **VO:** "The engine fires thousands of real request sequences and checks every rule after every step. It catches the break, shrinks it to just four steps, and replays it ten times. Ten out of ten. A real bug, not a prediction."

### 7 · Root cause and fix (1:50–2:10) [REAL + MG]
- Camera pans to the diagnosis in the real footage; MG magnifier zooms onto `src/routes/orders.js : 264`.
- The diff is rebuilt large in MG: the red line `if (numAmount > order.total)` slides out left, the green line `if (numAmount > order.total - order.refundedTotal)` wipes in from the left with a green scanline. Two small reviewer pills tick on: "Diagnosis Reviewer ✓", "Fix Reviewer ✓".
- **VO:** "The Detective finds the root cause, line two-sixty-four. A reviewer checks it against the evidence. The Surgeon writes a regression test, then a one-line fix."

### 8 · Verification (2:10–2:30) [REAL + MG]
- Four large check rows build one per beat, each with a crisp tick SFX, synced to the real verify output: **Exact replay 10/10 · Project tests · New regression test · Fresh search, new seed.**
- On the fourth tick: the background blooms green, **"✓ Fix verified"** in big serif, then the real final summary line from the terminal is highlighted. A small card flips in: "branch rook/fix-cx-001 · PR opened with the evidence".
- **VO:** "Now the engine verifies. The exact replay must hold. Your tests must pass. The new test must pass. And a fresh search must find nothing. Only then does Rook say: fixed and verified."

### 9 · Also on the web (2:30–2:40) [MG, or a real screen capture of the site]
- The terminal frame morphs (corner radius + size tween) into a browser frame showing the Rook web app: sidebar with recents, "What should Rook check next?", the "Select repository…" chip listing GitHub repos.
- Quick 3-beat montage: connect GitHub → pick repo → the same rules card in the browser.
- **VO:** "The same agents run on the web. Sign in, connect GitHub, pick a repo."

### 10 · Close (2:40–2:50) [MG]
- Everything pulls back into the rook glyph. Line: **"Don't ask AI if your code is correct. Make the code prove it."** ("Make the code prove it." in Rook red italic).
- Links: `rook-weld-six.vercel.app` · `github.com/tony19053000/rook`. Small line: "Built with IBM Bob · 13 agents · ~14 of 40 Bobcoins".
- Final beat: the red rook glyph pulses once. Cut to black.
- **VO:** "Don't ask AI if your code is correct. Make the code prove it. Rook."

---

## Part D: master prompt (paste into a motion/video tool or give to an editor)

> Create a 2 minute 50 second, 1920×1080, 30 fps product launch video for **Rook**, a developer tool that finds business-logic bugs by proof instead of prediction. IBM Bob AI agents read a codebase and propose business rules; a deterministic engine runs the real app, finds the smallest sequence of API calls that breaks a rule, replays it 10/10, and verifies a fix with four checks before calling it fixed. The **command-line tool is the hero**; the web app appears once near the end.
>
> **Look:** premium, calm, technical. Dark warm-neutral stage `#1A1918` with subtle film grain and two very soft light blooms (Rook red `#E0563F` top-right, proof green `#6BD9A0` bottom-left). Panels `#262624`/`#30302E`, hairlines `#3A3936`, text `#F0EEE6`, muted `#A8A59B`, break red `#FF8C83`, amber `#E9C46A`. Typefaces: Newsreader serif for statements and the wordmark, IBM Plex Sans for labels, IBM Plex Mono for terminal and code. No neon, no purple gradients, no stock tech HUDs, no emoji.
>
> **Motion:** one continuous camera over an infinite dark plane: pushes, pans, rack-focus, parallax across three depth layers. Expo-out entrances, power2 in-out camera moves, springy overshoot only for characters and checkmarks. Kinetic typography: per-word entrances with 35 ms stagger, blur-to-sharp, slight rise. Proof moments get a "lock-on": camera push, background dims to 40%, a thin outline traces the element (red for a break, green for proof), one soft glow pulse, a 2–3 s hold. Montage sections cut on a ~0.5 s beat.
>
> **Real footage:** place the supplied real terminal recording inside a floating terminal window (22 px radius, soft deep shadow, faint reflection). Speed it up 4–12× during waits with a small "×8" tag in the corner; return to 1× on key moments. When an agent line appears in the footage, pop a small character card beside the terminal: a round blob with two eyes in the agent's colour (Scout `#5EC8B8`, Mechanic `#F0A060`, Mapper `#7FB2F0`, Lawmaker `#C98BF0`, Rule Critic `#F08BB8`, Detective `#A98BF0`, Surgeon `#6BD9A0`), its name and a one-line job.
>
> **Scenes:** (1) cold open: three API calls type in (`POST /orders {total: 100}` 201, `POST /orders/7/cancel` 200, `POST /orders/7/refund {amount: 100}` 200), a split-flap counter shows ₹200 refunded on a ₹100 order in red, a "14/14 tests passing" badge flickers; (2) "AI reviewers guess." with hedging chat fragments drifting by, struck through in red, flipping to "Rook proves."; logo builds from five blocks, wordmark writes on; (3) a two-column diagram, IBM Bob agents (think) vs deterministic engine (judge), packets flowing between them, stamp "Only the engine decides pass or fail."; (4) fly into the real CLI run of `rook run shop-app`, agent cards pop out; (5) push into the rules card, a rejected rule circled red, the approved refund rule green, a ↵ keycap; (6) glitch freeze and a giant serif "Rule broken." that docks as a pill, an accordion shrink 11 → 7 → 4 steps, the four steps big (create_product, place_order, cancel_order, refund_order(100)), "Refunded 200 of 100", stamp "Replayed 10/10 · real bug"; (7) magnifier onto `src/routes/orders.js : 264`, diff where `if (numAmount > order.total)` slides out and `if (numAmount > order.total - order.refundedTotal)` wipes in green, reviewer pills tick; (8) four check rows tick one per beat (Exact replay 10/10, Project tests, New regression test, Fresh search) then a green bloom and big "✓ Fix verified", card "PR opened on rook/fix-cx-001"; (9) the terminal morphs into a browser showing the Rook web app (sidebar with recents, "What should Rook check next?", a "Select repository…" chip listing GitHub repos); (10) end card: "Don't ask AI if your code is correct. Make the code prove it." with the links rook-weld-six.vercel.app and github.com/tony19053000/rook and "Built with IBM Bob".
>
> **Sound:** minimal modern electronic bed at ~100 BPM (warm pads, tight percussion) ducked under a calm, confident voiceover at ~150 wpm. SFX: soft key ticks on typing, a low thud + glitch on "Rule broken", whooshes on camera pushes, a crisp tick per green check, a warm major chord on "Fix verified". Subtitles in IBM Plex Sans on a translucent dark pill, bottom centre.
>
> **Voiceover:** use the VO lines from the script in Part C, in order.
