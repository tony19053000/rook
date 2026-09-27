# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**Updated:** 27 Sep 03:19 IST. Account 1 working. ONLY ONE orchestrator session at a time.

**Committed and DONE (reviewer PASS), pushed:** ROOK-001–029, 032–037 (35 / 40). Bob coins ≈ 2.4 of 40. Full suite: 1377 passed.

**UNCOMMITTED work in the tree:** none.

**Hosting decision (user, 27 Sep ~02:00):** Hugging Face Docker Spaces are now paid → server moved to **AWS EC2** (user has $100 credits). AWS CLI profile `rook` (IAM user rook-deploy, AmazonEC2FullAccess), region us-west-2. The auto-mode classifier blocks the orchestrator/sub-agents from creating AWS resources → the USER runs, in order (see deploy/README.md): `deploy/aws/create.sh` (y/N, prints `https://<ip-dashes>.sslip.io`) → `deploy/aws/deploy.sh` → `deploy/aws/scripts/set-secret.sh BOB_API_KEY` → `uv run python deploy/smoke.py https://<host>`. Later: `ROOK_WEB_ORIGINS=https://<vercel> deploy/aws/deploy.sh`. Tear down: `deploy/aws/destroy.sh`.
**DEPLOYED 27 Sep ~03:40:** instance i-0e97c484003509f61, EIP 44.239.185.88 → **https://44-239-185-88.sslip.io** (/api/v1/health OK, replay mode, valid TLS, HSTS). Bob key set on server; direct smoke OK. **Vercel live: https://rook-weld-six.vercel.app** (Git-connected). **039a DONE + committed 7d7c052** (deterministic DIAGNOSE evidence: id aliases var[n] + clean_logs; replayed minishop run ends `done` w/ reviewed diagnosis; 0.34 coins). Fix not verified on hosted ProcessSandbox (runs app_dir, not workspace) → **user chose A (27 Sep ~10:15)**: hosted ProcessSandbox runs the workspace (patched) copy ONLY in replay mode; live mode unchanged. Before 039: id_aliases first-insertion-wins can misattribute colliding ids across entities with separate counters → add test; mask token/timestamp values in evidence. **U1 done (27 Sep ~08:30):** Supabase https://nfegrmjlbwfgvcyhwddh.supabase.co, Google provider on (Testing mode), NEXT_PUBLIC_SUPABASE_URL/ANON_KEY (sb_publishable_ key) on Vercel, SUPABASE_URL + SUPABASE_JWT_SECRET on server. User may have typed "rook-weld-slx" (wrong) in Supabase/ROOK_WEB_ORIGINS — told to fix to six. Server NOT yet redeployed with 038/039a (health lacks `proxied`); ROOK_PROXY_SECRET not set yet. **Running (uncommitted):** coder 039b (id-alias collisions, mask tokens/timestamps/seed in Bob evidence, record the browser approve-ALL path) and coder 039c (option A in sandbox/process.py + docs 03 §3; no recordings; must not touch 039b files). After both: re-record Surgeon/fix path for hosted replay → full loop verified.
**Server fully deployed 27 Sep ~10:00 with 038/039a/030** (Vercel /health proxied:true, direct false; smoke through Vercel status=done, 0 coins). All secrets set (BOB, SUPABASE_URL/JWT_SECRET/ANON_KEY, ROOK_PROXY_SECRET). Demo apps being built by the user. **ROOK-030 DONE + committed.** Server deploy (user): set-secret SUPABASE_ANON_KEY (sb_publishable_), `ROOK_WEB_ORIGINS=https://rook-weld-six.vercel.app deploy/aws/deploy.sh`, set-secret ROOK_PROXY_SECRET (after Vercel has it). NEVER let the user run deploy.sh while unreviewed code is in the tree (it ships the working tree).
**038 DONE + committed e4e2582.** User steps in order: (1) Vercel env ROOK_PROXY_SECRET (openssl rand -hex 32, Sensitive) + redeploy; (2) `ROOK_WEB_ORIGINS=https://rook-weld-six.vercel.app deploy/aws/deploy.sh`; (3) `deploy/aws/scripts/set-secret.sh ROOK_PROXY_SECRET` same value; (4) check /api/v1/health proxied true via Vercel, false direct; (5) `node web/e2e/console.mjs https://rook-weld-six.vercel.app`. For 039: browser guest approves ALL rules → no DIAGNOSE recording for that path → record it. Old note (superseded): coder ROOK-038: SSE times out through Vercel rewrite + 429 demo limit on 2nd guest run via Vercel + CSP. Then user runs `ROOK_WEB_ORIGINS=https://rook-weld-six.vercel.app deploy/aws/deploy.sh`. Local ~/.bob-key.env updated 27 Sep 06:50 (new key; it was pasted in chat → rotate after judging). Bob tgz vendored (gitignored) at deploy/vendor/.
**User's disk is full** (~400 MB free; Docker build cache 35.8 GB) — asked them to run `docker builder prune`. Don't docker build until freed.

**Next steps in order:** user deploys server (above) → 038 Vercel (U4, needs server URL) → 030 (U1 Supabase) → 031 (U2 GitHub App) → 039 (U5 demo apps; also fix DIAGNOSE replay key) → 040. The user got a full phase-by-phase guide (Phase 1 AWS ✓, 2 Vercel, 3 Supabase+Google, 4 GitHub App, 5 demo apps with the Antigravity prompt).

**Wiring notes from 036 for later tickets:** 030 → replace currentSession()/getToken() in web/lib/session.ts, SIGN_IN_AVAILABLE=true, OAuth handler in LoginView (SimpleViews.tsx). 031 → fill githubConnected from /me, pass onConnectGithub to RepoPicker (api.githubInstallUrl()). 037/038 → ROOK_API_PROXY_TARGET=https://<space>.hf.space at Vercel build time; CSP (connect-src 'self' + Supabase); verify SSE streams unbuffered through the rewrite; ROOK_TRUSTED_PROXY_HOPS on the Space.

**Follow-ups noted (non-blocking):**
- 032: user decides Bob Shell tgz hosting for live mode (`bob-package` input, licence?); fill README `@<full-commit-sha>` after a release; tighten find_rook_comment to login github-actions[bot]; consider hard-fail on pull_request_target + key; `rook init` scaffold still writes an old unpinned workflow; run once on a real runner (demo repo, 039).
- 036 E2E replay ends `failed` at DIAGNOSE: Detective recording key includes sandbox logs (recorded with in-process LocalApp vs real uvicorn). Fix: normalise logs before hashing, or re-record via the process sandbox (coins). Could fold into 039.
- Replay: `POST /counterexamples/{id}/replay` answers 501 until Session gets a replay-only mode (pass `create_app(replay_factory=...)`).
- Deploy (037): set ROOK_TRUSTED_PROXY_HOPS (probably 2), ROOK_GUEST_SECRET (≥32 chars), ROOK_WEB_ORIGINS, ROOK_DEMO_REPOS, ROOK_ALLOWLIST, ROOK_DAILY_COIN_CAP, ROOK_DB_PATH; check that the Vercel rewrite streams SSE unbuffered.
- mypy is not in dev deps (`uv run --with mypy --with types-PyYAML mypy src`): 8 pre-existing errors (sprite.py:150 + schema.py, agents/schemas.py, bob.py, executor.py, compose.py, understand.py). Small cleanup ticket candidate.
- 035: Edit-rule / Replay / Download-test buttons not built (no API); /dev/* must be gated before 038.
- 027: "e to edit one rule" not implemented (no Session answer shape; 04 §3.4).
- sprite.py:150 mypy override (026); scaffold mkdir through a symlinked .github (024); cancel latency per copy entry (023); bidi/zero-width chars pass through clean() (TUI + web).
- Older: Mechanic fileRegex `^\.rook-sandbox/` never matches (registry.py:26); per-actor cookie jars on the real-HTTP executor path; reject `inf` generator weights; wrap Guide snapshot as `<untrusted>`; CostUpdate ge=0 + monotonic cost; NFKC-normalise Surgeon paths; understand_minishop recordings hold /tmp/pytest-of-aayush paths; document cx JSON shape in 02 §7.8.

**Open decisions for the user:** ROOK-007 throughput 268 seq/s (target 500, ceiling is minishop); ROOK-014 SandboxPlan.egress for apps needing internet (not added).

**Lessons from this session:**
- NEVER `git commit -a` while a coder has uncommitted work: it swept unreviewed 039a files into a docs commit (reverted in e36e9c9). Always `git add <explicit paths>`.
- Commit order matters: 024/029 imported the uncommitted 023 session.py, so they waited for 023. Shared doc files were split per ticket with `git apply --cached --unidiff-zero` on a filtered `git diff -U0`.
- Bob matches mode `fileRegex` against ABSOLUTE paths. Record edit tapes only AFTER the path guard. Never redact file contents that must replay byte-exact.
- Always give the reviewer attack ideas. Parallel coders on separate files work; tell each which files NOT to touch.
- `ROOK_SLOW=1` enables the slow tests; Docker tests: `uv run pytest -q -m docker`. Live recordings live in `tests/fixtures/recordings/<name>/`.

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

**Current goal:** Review + commit ROOK-036 (coded, uncommitted) and finish + review + commit ROOK-028 (partial), then 032, then 030/031/037–040 as the user finishes U1–U5.

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
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
