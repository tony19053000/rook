# STATUS: live tracker and context dashboard

> Update this file after **every** ticket (CLAUDE.md, section 2). The ticket scope and acceptance criteria are in `docs/05_FEATURE_TICKETS.md`.

**Last updated:** 2026-09-27 11:31 IST · **By:** Account 2 (031 PASS + committed aa2a4c5; 039d fix re-record running; 040 README drafted)
**Deadline:** 27 Sep 20:30 IST · **Freeze:** 27 Sep 15:30 IST
**Current block:** B3 (M6 CLI finish → M9 web)

## Progress

```
OVERALL   [████████████████████████████░░]  95%  38 / 40 tickets
TIME      [█████████████████████░░░░░░░░░]  72%   ~9.0h left (to 27 Sep 20:30 IST)

M0  Docs & setup      [██████████]  100%   done
M1  Foundation        [██████████] 100%   4 / 4    ROOK-001…004
M2  Engine            [██████████] 100%   8 / 8    ROOK-005…012
M3  Sandbox           [██████████] 100%   2 / 2    ROOK-013…014
M4  Bob agents        [██████████] 100%   8 / 8    ROOK-015…022
M5  Session           [██████████] 100%   1 / 1    ROOK-023
M6  CLI (hero)        [██████████] 100%   5 / 5    ROOK-024…028
M7  Server            [██████████] 100%   1 / 1    ROOK-029
M8  Auth & GitHub     [██████████] 100%   3 / 3    ROOK-030…032
M9  Web               [██████████] 100%   4 / 4    ROOK-033…036
M10 Deploy & demo     [█████░░░░░]  50%   2 / 4    ROOK-037…040
USER tasks            [░░░░░░░░░░]   0%   0 / 9    U1…U9
```
Bars are 10 cells for milestones and 30 for overall and time; round down. Update them with every ticket status change.

## Snapshot

| | |
|---|---|
| Product | Rook (`rook`), IBM Bob-powered invariant breaker |
| Repo | https://github.com/tony19053000/rook (public) |
| Hosted web | https://rook-weld-six.vercel.app |
| Hosted API | https://44-239-185-88.sslip.io (AWS EC2 t3.small + Caddy, replay mode) |
| Bob | Shell 2.0.5 works; key in `~/.bob-key.env`; about 0.023 coins per call. Coins used so far: about 2.01 |
| Demo apps | not built yet (U5, the prompt is given on request) |

## Tickets

| ID | Title | Pri | Status | Notes |
|---|---|---|---|---|
| ROOK-001 | Project scaffold | P0 | DONE | reviewer PASS; Python pinned to 3.12 |
| ROOK-002 | Event bus, models, redaction, store | P0 | DONE | reviewer PASS; note: register BOB_API_KEY via register_secret in ROOK-015 |
| ROOK-003 | Model schema, loader, templating | P0 | DONE | reviewer PASS on round 2 (linear parser) |
| ROOK-004 | Safe expression evaluator | P0 | DONE | reviewer PASS on round 2 (work budget added) |
| ROOK-005 | Fixture app minishop | P0 | DONE | reviewer PASS (race test 10/10) |
| ROOK-006 | HTTP executor | P0 | DONE | reviewer PASS on round 2; ~290 seq/s, tune in 007 |
| ROOK-007 | Generator + Runner | P0 | DONE | reviewer PASS; throughput 268 seq/s in-process (500 NOT met: ceiling is minishop sync current_user + O(n) user scans, engine alone ~750/s; verified by reviewer). Follow-ups: per-actor cookie jars on real-HTTP path; reject inf weights |
| ROOK-008 | Judge | P0 | DONE | reviewer PASS; refund bug seeds 1-5 found at seq 8/4/3/53/26; fixed mode clean over 20k (ROOK_SLOW=1) |
| ROOK-009 | Shrinker | P0 | DONE | reviewer PASS; shrinks to create_product, buy, refund, refund (values 1), 1-minimal tested |
| ROOK-010 | Replayer | P0 | DONE | reviewer PASS; refund 10/10, FlipApp 5/10 flaky; shared exec helper in shrinker.py |
| ROOK-011 | Export + Verifier + Test Runner | P0 | DONE | reviewer PASS on round 2 (fd-walk writes with O_NOFOLLOW, nothing created outside root; fresh_search needs a <400 response; observed capped depth 8 / 64 KB) |
| ROOK-012 | Parallel steps (race) | P1 | DONE | reviewer PASS; stock race found seeds 1-10 (≤82 seqs); replay 10/10; flaky flag validated in 010 |
| ROOK-013 | Sandbox + ProcessSandbox | P0 | DONE | reviewer PASS on round 2 (settable_env whitelist + env denylist, fullmatch SHA) |
| ROOK-014 | DockerSandbox | P0 | DONE | reviewer PASS on round 3 (internal run network + hardened 127.0.0.1 proxy; compose hostname/alias hijack closed). Proposal pending: SandboxPlan.egress field (contract change) for apps needing internet |
| ROOK-015 | BobClient + recorder | P0 | DONE | reviewer PASS on round 2 (env allowlist) |
| ROOK-016 | Agent registry, prompts, modes | P0 | DONE | reviewer PASS on round 2 (case-insensitive .git, control chars, entity tags); note: NFKC-normalise paths as hardening |
| ROOK-017 | Scout → Mechanic → Mapper | P0 | DONE | reviewer PASS; live run 0.15 coins, recorded replay in default suite. Note: dry-run treats ≥400 as fail (expected-forbidden actions need handling in 018/023) |
| ROOK-018 | Lawmaker + Rule Critic | P0 | DONE | reviewer PASS; 0.13 coins; 9/10 real rules accepted on fixed minishop; expected-403 rule judged by its check. OPEN DECISION: response rule broken on 1st request (buggy admin export) is rejected, see HANDOFF |
| ROOK-019 | Test Designer + Strategist | P1 | DONE | reviewer PASS; 0.04 coins; refund bug found in 5 seqs (designed) vs 1903 (random) over 5 seeds, median 1 vs 359. Note: adds ~30 s to default suite |
| ROOK-020 | Detective + Diagnosis Reviewer | P0 | DONE | reviewer PASS round 2 (recording paths scrubbed); 0.08 coins; points to minishop app.py:214, approved round 1. Session calls DiagnosePipeline(client, ws).run(model, cx, executor, sandbox=, summary=) |
| ROOK-021 | Surgeon + path guard + Fix Reviewer | P0 | DONE | reviewer PASS (3 review rounds: code, recording delta, tape-after-guard fix). Live run verified 4/4 (Bob test fails on buggy, 1-line fix, 1500-seq fresh search clean). 1.42 coins. Found + fixed: Bob matches fileRegex on ABSOLUTE paths. Edit tapes store only guard-approved files |
| ROOK-022 | Coordinator + rails + Guide | P0 | DONE | reviewer PASS; rails in core/rails.py. Follow-ups: wrap Guide snapshot as untrusted; CostUpdate ge=0 + monotonic cost in RunState |
| ROOK-023 | Session + Conductor end to end | P0 | DONE | reviewer PASS round 2 (symlink-escape skip + clone core.symlinks=false; cancel race fixed, 30/30; admin rule B). Recordings 0.34 coins. Follow-ups: cancel latency per copy entry (huge single file); local-copy TOCTOU accepted risk |
| ROOK-024 | Typer commands + CI mode | P0 | DONE | reviewer PASS round 1. replay/verify need loopback --base-url; login exits 1 until 030. Follow-up: scaffold mkdir through a symlinked .github |
| ROOK-025 | TUI shell | P0 | DONE | reviewer PASS round 3 (clean_multiline keeps \n for cards; control chars stripped). Follow-ups: sprite.py:150 mypy override (026); clean_data has no depth cap; bidi/zero-width pass through |
, breaks the diff card); round-3 fix partial (clean_multiline). LAST round |
| ROOK-026 | Sprite + row widgets | P0 | DONE | reviewer PASS round 2 (control chars stripped via cli/tui/safe_text.clean). Note: bidi/zero-width chars pass through; ✗ on reject guessed (no verdict field on agent.finished) |
| ROOK-027 | Question prompts + cards | P0 | DONE | reviewer PASS round 1. Follow-up: 'e to edit one rule' not implemented (no Session answer shape; 04 §3.4). 024 wires prompts.register(app) + Backend.answer Any |
| ROOK-028 | Background run + chat | P0 | DONE | reviewer PASS round 1; teardown LookupError root cause = callbacks ran in run-thread contextvars → app context captured at bind(); regression test 20x green |
| ROOK-029 | FastAPI server | P0 | DONE | reviewer PASS round 1. Follow-ups: replay → 501 until Session gets a replay-only mode; deploy must set ROOK_TRUSTED_PROXY_HOPS, ROOK_GUEST_SECRET, ROOK_WEB_ORIGINS, ROOK_DEMO_REPOS; verify the Vercel rewrite streams SSE |
| ROOK-030 | Auth (Supabase + CLI login) | P1 | DONE | reviewer PASS r1. JWT HS256 + JWKS (project is ES256); web Google PKCE via @supabase/auth-js; rook login (localhost + --device), logout. No CLI token refresh (re-login after ~1h) |
| ROOK-031 | GitHub App integration | P1 | DONE | reviewer PASS r1 (aa2a4c5). Hosted server never runs GitHub repos (web shows the CLI command). Live PR test pending user redeploy (steps in HANDOFF). Follow-ups: in-memory install states; re-check valid_repo in token_for; pin mypy dev dep |
| ROOK-032 | GitHub Action | P1 | DONE | reviewer PASS round 1; action.yml + rook-pr-comment (dry run, marker upsert, SHA pins verified). Open: Bob tgz hosting for live mode; README `@<full-commit-sha>` placeholder; never run on a real runner |
| ROOK-033 | Web scaffold + event client | P0 | DONE | reviewer PASS round 1 (59 vitest, tsc, build, audit 0). Notes: /dev/stream chunk ships in prod (clean fixture); cap SSE line length; open contract gaps for 029 (Bearer+CORS on SSE, guest cookie SameSite cross-site, §11 response shapes, pct 0–100) |
| ROOK-034 | Web sprite + rows | P0 | DONE | reviewer PASS round 1 (91 vitest; /dev/* 404 in prod verified). Follow-ups: 035 must clean() DevStream card text; bidi/zero-width pass through; one shared ticker for many rows |
| ROOK-035 | Web cards + answers + chat | P0 | DONE | reviewer PASS round 1 (132 vitest). Not built (no backend yet): Edit-rule, Replay, Download-test buttons. Follow-ups: DOM tests for double-submit/countdown; gate /dev/* before 038 |
| ROOK-036 | Web pages, picker, guest | P0 | DONE | reviewer PASS round 2; `npm run test:e2e` (web/e2e/smoke.mjs, replay, 0 coins, 17 checks). Replayed run ends `failed` at DIAGNOSE (Detective recording key includes sandbox logs; recorded in-process vs real uvicorn) → follow-up |
| ROOK-037 | Server image + AWS EC2 deploy | P0 | DONE | reviewer PASS r1. Re-targeted from HF (Docker Spaces now paid) to AWS EC2 t3.small + Caddy on `<ip-dashes>.sslip.io`, profile `rook`, us-west-2 ($100 credits). Local: image builds, /health via Caddy, guest replay run to SAVE (fails at DIAGNOSE, known). NOT deployed yet: user runs deploy/aws/create.sh + deploy.sh + set-secret.sh BOB_API_KEY |
| ROOK-038 | Vercel deploy | P0 | DONE | reviewer PASS r1. SSE `: flush` after bursts (Vercel held burst tails ~15 s); ROOK_PROXY_SECRET header via web/middleware.ts → trusted client IP; per-IP guest quota 10/day (cookie 3); nonce CSP; favicon; e2e/console.mjs. User must set ROOK_PROXY_SECRET on Vercel THEN server (deploy.sh + set-secret.sh) and check /health proxied:true |
| ROOK-039 | Demo apps integration + recordings | P0 | IN PROGRESS | 039a DONE (DIAGNOSE deterministic). 039c DONE (reviewer PASS r1, b7adb5f: hosted replay runs the patched workspace; live skips VERIFY honestly). 039b DONE (reviewer PASS r1, 9c92834: volatile masking, id collisions, approve-all recordings 0.14 coins). Next: re-record Surgeon/fix path for hosted replay; then the 3 demo repos (U5). Waiting for the 3 demo repos (U5) |
| ROOK-040 | Release polish + PyPI | P1 | IN PROGRESS | README rewritten (uncommitted, not reviewed). PyPI name rook-cli TAKEN (free: rook-invariants, rook-bob): waiting user decision/token |

Statuses: `TODO` · `IN PROGRESS` · `IN REVIEW` · `DONE` · `BLOCKED (reason)`

## User tasks

| ID | Task | Status |
|---|---|---|
| U1 | Supabase + Google OAuth | DONE (Supabase nfegrmjlbwfgvcyhwddh; Google app in Testing mode → owner as test user; judges use guest) |
| U2 | GitHub App "Rook" | DONE (App ID 5093123, slug rook-invariants; 3 secrets on AWS) |
| U3 | AWS account + IAM user rook-deploy (profile `rook`) | DONE (was HF Space; $100 credits) |
| U4 | Vercel project | DONE (rook-weld-six.vercel.app) |
| U5 | 3 demo apps via Antigravity | IN PROGRESS (user building; prompts in docs/demo-apps/) |
| U6 | Bob IDE clips | TODO |
| U7 | Video | TODO |
| U8 | Deck | TODO |
| U9 | Submit | TODO |

## Blockers
None.

## Key decisions (log)
- 26 Sep: name **Rook** (warned about the rook.io / Rookout name clash; the user kept it). The CLI is the hero; the full web app is required at the URL.
- 26 Sep: 13 Bob agents as custom modes (Coordinator + 12 specialists) plus 6 deterministic engine workers; only the engine judges.
- 26 Sep: agents appear inline as blob characters while working (no roster panel).
- 26 Sep: web = Claude Code web layout; Vercel (web) + Hugging Face Docker Space (API + demo apps via ProcessSandbox).
- 26 Sep 18:40: admin rule = **B** (flag a rule broken on the 1st request as 'possibly already broken', human approval, never --auto). Done in 023.
- 26 Sep 19:55: the web calls the API through a same-origin Vercel rewrite proxy, so the guest cookie stays first-party SameSite=Lax (03 unchanged in spirit; note to add in 029).
- 26 Sep: Google sign-in (Supabase) + a separate GitHub App connect; guest demo mode on the web.
