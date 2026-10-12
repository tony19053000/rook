# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**Updated:** 12 Oct 2026. **Goal: M12 launch readiness** (user pasted an 8-part launch checklist and said "fix all of this"). Plan + tickets: doc 05 "M12" (ROOK-049–057), facts in doc 06 §4 (M12 blocks). Planning commit 8d92788.

**User decisions (12 Oct):** operator **Aayush Kumar, individual, India**; public email **c40534394@gmail.com**; CTA stays **"Try Rook"** (no visible "demo"); **hosted GitHub runs OFF**, no Docker socket on the server (ROOK-050). Contact = `mailto:` + GitHub Issues (no form backend, no new service).

**M12 order:** CI 049 · server 050 → 051 · web strictly in order 053 → 054 → 055 → 056 → 052 → 057. **053 DONE** (bfbb071), **049 DONE** (86ca683; CI goes green only after a push), **050 DONE** (9e411b2; live server changes only after `deploy/aws/deploy.sh`). **051 DONE** (ad3e6c4). Server stream done; the live server needs `deploy/aws/deploy.sh` (U10) for 048/050/051. 054 coder started. Started 12 Oct: 049, 050, 053 coders in parallel (separate dirs: `.github`+`.gitignore` / `src`+`deploy`+docs 02/03 / `web`).
**STOPPED 12 Oct (user paused, moving to Windows). Working tree clean** except the user's `docs/submission/**`, `docs/demo-apps/**`. **NOTHING IS PUSHED** since origin/main 59fd8e1: 20+ local commits exist only on this Linux machine; a Windows clone won't have them until the user approves a push.
- DONE + committed: 053 (bfbb071), 049 (86ca683), 050 (9e411b2), 051 (ad3e6c4), 054 (b91e274), **052 + 056 (56d4494, coder only, not reviewed)**.
- **ROOK-055 docs guides: PARTIAL, in 56d4494.** The coder was stopped mid-ticket. Present: `/docs/*` guide pages, `content/docs*.ts`, `components/site/docs/`, README edits, `tests/unit/test_docs_cli_commands.py` (77 pass). Tree is green (tsc, lint, 718 vitest). To finish: give a coder the ROOK-055 ticket and say "continue: check every item of the ticket against the tree" (its own vitest tests, TOC anchors, footer Docs column, `cta.docs.href` → `/docs/getting-started`, `SITEMAP_PATHS`, smoke.mjs, README, the install check, a scratch-copy build).
- **Next:** finish 055 (Opus) → 057 final verification (Sonnet 5.5) → rebuild `web/.next` so localhost:3000 shows the new site → ask the user to look at the 052 colour changes → ask to push (U11) and to redeploy the server (U10).
- Never build into `web/.next` while a preview runs on port 3000 (build in a scratch copy).

**User instruction (12 Oct, M12 only):** no REVIEWER for the remaining M12 tickets (055, 056, 052, 057): coder only, commit when the coder's tests pass. Models: Sonnet 5.5 for light tickets (056, 057), Opus 5.5 for the rest (055, 052). Mark these "coder only, not reviewed" in STATUS.

**Not doable by Claude (user tasks U10–U16 in doc 05/STATUS):** redeploy server, approve push, custom domain, trademark check (CNCF "Rook" at rook.io is a real name conflict), publish Google OAuth (Testing mode), live GitHub App PR test, lawyer review + launch feedback.

**Before M12:**  **Goal done: the public marketing website** (user request 9 Oct), spec `docs/06_PUBLIC_SITE.md`, tickets ROOK-043 → 044 → 045 (doc 05, M11), run strictly in order (they share `web/` and `next build`).

**State:** HEAD 4530044 (+ docs). ROOK-001–039, 041, 042 DONE. ROOK-040 (release polish) still open (PyPI name rook-cli taken). Web baseline before M11: 271 vitest passed, tsc clean (`npm ci` was needed: node_modules was missing).
- **ROOK-043 DONE** (reviewer PASS, committed 8976686): app home `/` → `/app`, site design system `web/components/site/`, copy `web/content/*.ts`, `/pricing` `/privacy` `/terms` 404, minimal `/`, ESLint (`npm run lint`), RTL + jsdom, `motion` dep (unused until 044). Web suite: 314 passed.
- **ROOK-044 DONE** (reviewer PASS round 2, committed bf5f61d): full home (`components/site/home/*`, `content/{home,walkthrough}.ts`), frame contrast via `frameTheme.ts` + `lib/contrast.ts` + `AgentRow` `readableOn`. Web suite 365 passed. Follow-ups: the app pages' own contrast gaps (pre-existing); in frames, `--accent` raised to #ff7a5f makes white-on-accent 2.56:1 (not rendered today; add coverage or a separate frame text token in 045).
- **ROOK-045 DONE** (reviewer PASS, committed 8e33e90): `/docs`, `/security`, `/login` (click-only states, no API calls on load), "Open workspace" hint, frame accent fix, certification copy rule. Web suite 415 passed. README hosted-runs sentence fixed (doc commit).
- **ROOK-046 DONE** (reviewer PASS, committed 45af3ae): no dead sign-in button with JS off; copy-rule negation fix. **M11 complete.** Final check 11 Oct: typecheck, lint, 419 vitest, build all pass.
- **ROOK-047 DONE** (user feedback: looked like a tablet layout at 1920 px; reviewer PASS, committed a3a89fb): full-width header, 1440 px content container, wider hero/walkthrough/grids, capped text measure. Local preview: `node node_modules/next/dist/bin/next start -p 3000` in web/ after `npm run build`.
- **ROOK-048 DONE** (user request: no visible "demo"; reviewer PASS r2, committed 4530044): CTA "Try Rook", "example apps/repos", reworded app + server messages; guards `NO_DEMO_WORD`, `noDemo.test.tsx`, `tests/unit/test_no_demo_copy.py`. API values stay `kind: "demo"`. Server wording reaches production only after the user runs `deploy/aws/deploy.sh`; the web handles both old and new guest-limit text. Known data leftovers (not Rook copy): `admin@demo.local` in the minishop fixture app; Bob text in unused wallet-api recordings.
- **PUSHED 12 Oct** (user approved): origin/main = 59fd8e1; Vercel redeployed in ~1 min; live https://rook-weld-six.vercel.app shows the marketing site, app at `/app`, all pages 200, `/api/v1/health` proxied:true. Server (EC2) still runs the old message wording until the user runs `deploy/aws/deploy.sh`.
- Follow-up for the user to decide (changes the app's look): the app pages' own contrast (--faint 3.7:1, white on accent 3.77:1, 5 agent name colours).
- Known, unrelated: `tests/unit/test_demo_apps.py` has 3 failures locally (missing Mechanic/Coordinator recording keys); they depend on the local demo builds in `~/.cache/rook/demos`, not on M11 code. Follow-up, not blocking.
- **Don't push without asking the user**: Vercel redeploys on push to main, and this changes what `/` shows on the live URL (judging may still be open).
- Untracked/modified user files (`docs/submission/**`, `docs/demo-apps/**`) are the user's video/deck work: never commit or edit them.

**LIVE (do not recreate):** web https://rook-weld-six.vercel.app (Vercel, push to main = redeploy) · API https://44-239-185-88.sslip.io (AWS EC2, Caddy) · Supabase https://nfegrmjlbwfgvcyhwddh.supabase.co (Google provider, Testing mode; redirect allowlist has `/login`, keep that route). `deploy.sh` ships the working tree: never with unreviewed code in it.

**Lessons (still true):** never `git commit -a` (always `git add <explicit paths>`); always give the reviewer attack ideas; one orchestrator session at a time.

---

## Goal prompt (paste into a fresh session)

When the user asks for a **goal prompt**, update the "Current goal" line below and give them this block:

```
You are continuing the Rook project (IBM Bob hackathon) in /home/aayush/Desktop/Counterexample.
1. Read CLAUDE.md fully and follow it as compulsory rules.
2. Read HANDOFF.md ("Next session starts here") and STATUS.md.
3. Current goal: <CURRENT GOAL>
4. Work ticket by ticket: send each ticket to the `coder` sub-agent, then the `reviewer` sub-agent; on PASS, commit, update STATUS.md, and update HANDOFF.md after every ticket.
5. Deadline: 27 Sep 2026 20:30 IST (feature freeze 15:30 IST). Don't cut scope silently; mark BLOCKED with a reason and tell me.
Start now.
```

**Current goal:** Finish + review + commit ROOK-039b and 039c (partial, uncommitted), re-record the fix path, have the user redeploy; then ROOK-039 on the 3 demo apps, ROOK-031 (GitHub App), ROOK-040 polish. Freeze 15:30 IST, deadline 20:30 IST.

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
| 12 Oct | 2 | User paused. 052 + 056 (coder only) + 055 partial committed together; 057 not started; not pushed | 56d4494 |
| 12 Oct | 2 | ROOK-054 home rework PASS r2 + committed | ROOK-054 b91e274 |
| 12 Oct | 2 | Account switched at the limit; 054 coder resumed on round 2 (copy guards) | (docs) |
| 12 Oct | – | ROOK-051 deletion + retention PASS r1 + committed (server redeploy needed: U10) | ROOK-051 ad3e6c4 |
| 12 Oct | – | ROOK-050 hosted GitHub runs off, no Docker socket PASS r1 + committed (server redeploy needed: U10) | ROOK-050 9e411b2 |
| 12 Oct | – | ROOK-049 CI fix + web job + live smoke PASS r1 + committed; actions SHA-pinned | ROOK-049 86ca683 |
| 12 Oct | – | ROOK-053 site identity/pages/SEO PASS r3 + committed (CSP matcher fixed) | ROOK-053 bfbb071 |
| 12 Oct | – | M12 launch readiness planned (049–057), user decisions recorded; 049/050/053 coders started | (docs) 8d92788 |
| 12 Oct | – | Pushed to main (user approved); Vercel live with the new site | (docs) |
| 12 Oct | – | ROOK-048 no visible "demo" PASS r2 + committed; localhost:3000 rebuilt | ROOK-048 |
| 11 Oct | – | ROOK-047 full-width layout PASS + committed (user feedback); localhost:3000 rebuilt | ROOK-047 |
| 11 Oct | – | ROOK-046 PASS + committed; M11 done (419 vitest, lint, typecheck, build green); not pushed | ROOK-046 |
| 11 Oct | – | ROOK-045 PASS r1 + committed; README fix; ROOK-046 polish started | ROOK-045 |
| 11 Oct | – | ROOK-044 PASS r2 (r1 FAIL: frame contrast) + committed; 045 coder started | ROOK-044 |
| 11 Oct | – | ROOK-043 reviewer PASS (2nd attempt; 1st cut off by usage limit) + committed; 044 coder started | ROOK-043 |
| 9 Oct | – | Public website started: docs/06_PUBLIC_SITE.md, tickets ROOK-043–045 added; 043 coder running | (docs) |
| 27 Sep 16:43 | 2 | Server live with ROOK-041 (Docker reachable; t3.small, free plan can't resize; swap 4G; coin cap 10). ROOK-042 web redesign (Claude-Code-style) PASS + committed 527c050, Vercel auto-deploys. Left: user live GitHub run test, Google OAuth publish (judges sign-in), ROOK-040 tag v0.1.0, video | ROOK-042 |
| 27 Sep 15:16 | 2 | ROOK-041 web + server PASS + committed. 40/41. User next: resize EC2 to t3.medium, `ROOK_DAILY_COIN_CAP=10 ROOK_WEB_ORIGINS=https://rook-weld-six.vercel.app deploy/aws/deploy.sh`, smoke, sign in → connect GitHub → run shop-app live. Then ROOK-040 (skip PyPI, tag v0.1.0) + video | ROOK-041 |
| 27 Sep ~14:50 | 2 | Auto-on-featured-demo fix committed 3746bbc (needs redeploy). USER DECISION: build ROOK-041 hosted runs of signed-in users' own GitHub repos (like Claude Code web); freeze moved to ~17:30. Two coders: server (routes/runs, session factory live Bob per run, DockerSandbox via docker.sock, host-path workspace volume, limits, docs/02+03) and web (picker starts GitHub runs when /me.can_run_github). Contract: /me.can_run_github; POST /runs repo.kind=github | (docs) |
| 27 Sep 14:27 | 2 | User redeployed (after .dockerignore fix 520d8fa). LIVE smoke via Vercel: minishop + shop-app both 'Fixed and verified', 0 coins. Left: ROOK-040 (PyPI rook-cli taken → skip unless user decides; v0.1.0 tag), 031 live PR test, vitest-not-found in local Docker sandbox (Node), video build after freeze | (docs) |
| 27 Sep 14:10 | 2 | ROOK-039 PASS + committed (shop-app verified on replay; billing/wallet not offered, user-approved). 39/40. Next: user runs deploy.sh + smoke; live PR test (031); vitest-not-found bug in local Docker sandbox for Node (CLI shop-app run) awaits user yes; ROOK-040 left: PyPI (rook-cli taken) + v0.1.0 tag; video build after freeze | ROOK-039 |
| 27 Sep ~13:30 | 2→(acct switch noticed) | Committed: UI polish 7aaffc1, featured rule b054314. ROOK-039 demo apps (uncommitted): 3 apps pinned/allowlisted/recorded (3.96 coins) but none verified (shop-app: flawed Lawmaker rule; billing/wallet: rules/model miss bugs). User chose: re-record shop-app, retry billing+wallet, hard stop 14:45, hide unverified apps from demos.yaml. Dockerfile patch applied by orchestrator with user approval (node_modules symlink, go cache chown, COPY hosted_* recordings). User must NOT deploy until 039 committed | (docs) |
| 27 Sep ~12:55 | 2 | ROOK-039d PASS + committed (hosted refund replay → Fixed and verified; approve-all → done, honestly unverified, patch reverted). Submission kit committed b71bdf9. Running: 039 demo apps coder, UI polish coder (+ guest default = one verifying rule) | ROOK-039d |
| 27 Sep ~12:40 | 2 | User: build freeze in ~3h (rest for deck/video). Running in parallel (all uncommitted): 039d fix path (option C/b: hosted approve-all ends `done` unverified, patch reverted) IN REVIEW; 039 demo apps coder (shop-app e92c866, billing-service 2186039, wallet-api cdfc08c; ≤5 coins); web UI polish coder (web/ only); submission kit writer (docs/submission/SUBMISSION_KIT.md). README committed 9615561. PyPI: rook-cli taken, no user answer yet → default skip | (docs) |
| 27 Sep 11:31 | 2 | ROOK-031 PASS r1 + committed. 38/40. 039d re-record running; 040 README drafted; rook-cli PyPI name taken | ROOK-031 |
| 27 Sep | 2 | ROOK-039b PASS r1 + committed (e2e both approve modes done, 0 coins). Reviewer follow-up: redact Coordinator notes at source. 031 coding | ROOK-039b |
| 27 Sep | 2 | ROOK-039c PASS r1 + committed (no new code needed; reviewer notes: conftest planting bounded by path guard; command_timeout has no ceiling). 039b coding | ROOK-039c |
| 27 Sep 10:20 | 1 | Update handoff (limit): stopped 039b + 039c coders mid-work (uncommitted, partial). User chose option A. Server + Vercel + Supabase fully live. 37/40 | (docs) |
| 27 Sep 09:11 | 1 | ROOK-030 PASS r1 + committed. 37/40. Left: 031 (U2), 039 (U5 + A/B/C), 040 | ROOK-030 |
| 27 Sep 08:08 | 1 | ROOK-039a + ROOK-038 PASS + committed. 36/40. Waiting: user deploy steps, A/B/C decision, demo apps, Supabase, GitHub App | ROOK-038 |
| 27 Sep 03:19 | 1 | ROOK-037 PASS r1 + committed (HF → AWS EC2 + Caddy; user must run create/deploy). 35/40 | ROOK-037 |
| 27 Sep 00:23 | 1 | ROOK-032 PASS r1 + committed. 34/40. Remaining 030/031/037–040 wait on U1–U5 | ROOK-032 |
| 27 Sep 00:10 | 1 | ROOK-036 PASS r2 + committed (e2e smoke, 02 §14 proxy target; 02 hunks split from 032). 032 coded, review r1. 33/40 | ROOK-036 |
| 26 Sep 23:55 | 1 | ROOK-028 PASS r1 + committed (contextvars fix for teardown LookupError). 036 r1 FAIL (E2E proof, 02 §14) → coder fixing. 32/40 | ROOK-028 |
| 26 Sep 23:16 | 2 | Update handoff (session limit): 036 coded, review not done; 028 partial (teardown-focus bug fix mid-way). 31/40 | (docs) |
| 26 Sep 21:17 | 2 | ROOK-035 PASS round 1 + committed; 036 coding; 028 coding | ROOK-035 |
| 26 Sep 21:10 | 2 | ROOK-023 PASS round 2 + committed, then 029 and 024 committed (doc hunks split per ticket). 30/40. 028 + 035 coding | ROOK-023/029/024 |
| 26 Sep 21:01 | 2 | ROOK-024 reviewer PASS (uncommitted; commit order: 023 → 029 → 024). 035 coding; 023 review r2 | (none) |
| 26 Sep 21:00 | 2 | ROOK-034 PASS round 1 + committed | ROOK-034 |
| 26 Sep 20:40 | 2 | ROOK-029 reviewer PASS (uncommitted: depends on uncommitted session.py → commit right after 023; 02/03 doc hunks are mixed: 023 = 02 §5/§9/§10 + 03 §4.1, 029 = 02 §11/§13 + 03 §8). 023 review r2; 024 coding | (none) |
| 26 Sep 20:35 | 2 | ROOK-027 PASS round 1 + committed; 029 in review r1 (replay 501 declared gap); 023 fixing; 024 coding | ROOK-027 |
| 26 Sep 20:30 | 2 | ROOK-025 PASS round 3 + committed; 027 in review r1; 023 fix + 029 coding; 024 coding | ROOK-025 |
| 26 Sep 20:15 | 2 | Resumed: suite 1137 passed / 0 failed. Coders started: 023 fix r1 findings, 025 round 3 (last), 029 server, 027 cards (all uncommitted) | (none) |
| 26 Sep 20:00 | 1 | Update handoff: stopped all coders. 023 FAIL r1 (symlink escape, flaky cancel, mypy) fix partial; 025 FAIL r2, r3 partial; 027/029 not started (no files). 24/40 | (docs) |
| 26 Sep 19:50 | 1 | ROOK-033 PASS round 1 + committed (web scaffold) | ROOK-033 |
| 26 Sep 19:40 | 1 | ROOK-026 PASS round 2 + committed; 023 (+B) and 025 fix round coding; 033 in review | ROOK-026 |
| 26 Sep 19:01 | 2 | Stopped: killed this session's 023 coder at user request. Tree has 023 files + tests/fixtures/recordings/session_minishop/ (new, unreviewed; no local paths found) + 02_ARCHITECTURE edits, all uncommitted. Check that no two orchestrators run at once | (docs) |
| 26 Sep 18:40 | 1 | Resumed: 1014 passed / 4 failed (all 023). User chose admin rule B + 3-coin cap; coder finishing 023 (+B) | (docs) |
| 26 Sep 18:25 | 2 | Update handoff: 023 coder still running (uncommitted); 22/40 done, ≈2.0 coins | (docs) |
| 26 Sep 18:10 | 1 | Account limit hit mid-023; coder resumed on account 2 | (docs) |
| 26 Sep | 1 | ROOK-021 PASS + committed (M4 done; 1.42 coins; fileRegex absolute-path bug fixed; tape-after-guard) | ROOK-021 |
| 26 Sep | 1 | ROOK-019 PASS + committed (0.04 coins; 5 vs 1903 seqs); 021 coding | ROOK-019 |
| 26 Sep | 1 | ROOK-020 PASS round 2 + committed (0.08 coins); 019 in review | ROOK-020 |
| 26 Sep | 1 | ROOK-018 PASS + committed (0.13 coins); 020 coding | ROOK-018 |
| 26 Sep | 1 | ROOK-011 PASS round 2 + committed (M2 done); 018 coding | ROOK-011 |
| 26 Sep (resume) | 1 | Resumed: suite green (825 passed); 011 fix round 2 + 018 coding in parallel | (none) |
| 26 Sep 15:30 | 2 | Stopped for account switch: 011 review FAIL (fix not applied), 018 not started; agents stopped | (docs) |
| 26 Sep 15:25 | 2 | ROOK-017 PASS + committed (first live Bob pipeline, 0.15 coins); 011 in review; 018 coding | ROOK-017 |
| 26 Sep 15:06 | 2 | ROOK-014 PASS round 3 + committed (M3 done); 011 + 017 coding | ROOK-014 |
| 26 Sep 15:05 | 2 | ROOK-010 PASS + committed; 011 coding; 014 round 3 in review | ROOK-010 |
| 26 Sep 14:54 | 2 | ROOK-009 PASS + committed; 010 coding; 014 fix round 2 | ROOK-009 |
| 26 Sep 14:52 | 2 | ROOK-012 PASS + committed; 014 fix round 2 (internal network); 009 in review | ROOK-012 |
| 26 Sep 14:38 | 2 | ROOK-007+008 PASS + committed (268 seq/s, honest ceiling = minishop); 014, 009, 012 coding | ROOK-007/008 |
| 26 Sep 14:32 | 2 | ROOK-013 PASS round 2 + committed; 007+008 in review (throughput ~270 seq/s, ceiling = minishop); 014 coding | ROOK-013 |
| 26 Sep 14:29 | 2 | ROOK-022 PASS + committed (rails in core/rails.py; for 023 feed bus events to RunState.observe + RunSnapshot); 013 in fix round 2; 007+008 coding | ROOK-022 |
| 26 Sep 14:19 | 2 | ROOK-016 fix round → reviewer PASS + committed; 007+008 coder finishing | ROOK-016 |
| 26 Sep 14:08 | 1 | ROOK-016 coded (in review), 007+008 coding; docs say 13 agents; session ended at the 90% limit | (docs) |
| 26 Sep 14:05 | 1 | ROOK-006 (round 2: gather leak fixed) and ROOK-015 (round 2: env allowlist) PASS + committed | ROOK-006/015 |
| 26 Sep 13:48 | 1 | ROOK-002, 004 (after a work-budget fix) and 005 PASS + committed; 003 in fix round | ROOK-002/004/005 |
| 26 Sep 13:36 | 1 | ROOK-001 scaffold (coder → reviewer PASS) | ROOK-001 |
| 26 Sep 13:25 | 1 | Design finalised with the user; wrote CLAUDE.md, the coder/reviewer sub-agents, docs 01–05, STATUS, HANDOFF and README; created the GitHub repo | (see git log) |
| 26 Sep 12:20 | 1 | Verified Bob Shell 2.0.5: `bob run --format json/stream-json`, custom modes via `.bob/custom_modes.yaml`, about 0.023 coins per call; the Lawmaker test found the refund invariant from code | (none) |

## Useful facts
- Mockups (the same files as in `docs/mockups/`, also published privately for the user): walkthrough, terminal session, agent characters, web app.
- The hackathon requires a URL, an MP4 of 5 minutes or less, a PDF deck, and a public repo. Bob IDE use is mandatory; Bob Shell is optional (we use both).
- The user is in IST. `gh` is logged in as `tony19053000`.
