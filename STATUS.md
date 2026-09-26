# STATUS: live tracker and context dashboard

> Update this file after **every** ticket (CLAUDE.md, section 2). The ticket scope and acceptance criteria are in `docs/05_FEATURE_TICKETS.md`.

**Last updated:** 2026-09-26 15:05 IST · **By:** Account 2
**Deadline:** 27 Sep 20:30 IST · **Freeze:** 27 Sep 15:30 IST
**Current block:** B1 (M2 engine + M4 agents in parallel; ahead of the roadmap)

## Progress

```
OVERALL   [███████████░░░░░░░░░░░░░░░░░░░]  37%  15 / 40 tickets
TIME      [████░░░░░░░░░░░░░░░░░░░░░░░░░░]  13%   ~27h left (to 27 Sep 20:30 IST)

M0  Docs & setup      [██████████]  100%   done
M1  Foundation        [██████████] 100%   4 / 4    ROOK-001…004
M2  Engine            [████████░░]  87%   7 / 8    ROOK-005…012
M3  Sandbox           [█████░░░░░]  50%   1 / 2    ROOK-013…014
M4  Bob agents        [███░░░░░░░]  37%   3 / 8    ROOK-015…022
M5  Session           [░░░░░░░░░░]   0%   0 / 1    ROOK-023
M6  CLI (hero)        [░░░░░░░░░░]   0%   0 / 5    ROOK-024…028
M7  Server            [░░░░░░░░░░]   0%   0 / 1    ROOK-029
M8  Auth & GitHub     [░░░░░░░░░░]   0%   0 / 3    ROOK-030…032
M9  Web               [░░░░░░░░░░]   0%   0 / 4    ROOK-033…036
M10 Deploy & demo     [░░░░░░░░░░]   0%   0 / 4    ROOK-037…040
USER tasks            [░░░░░░░░░░]   0%   0 / 9    U1…U9
```
Bars are 10 cells for milestones and 30 for overall and time; round down. Update them with every ticket status change.

## Snapshot

| | |
|---|---|
| Product | Rook (`rook`), IBM Bob-powered invariant breaker |
| Repo | https://github.com/tony19053000/rook (public) |
| Hosted web | not deployed yet (Vercel) |
| Hosted API | not deployed yet (Hugging Face Space) |
| Bob | Shell 2.0.5 works; key in `~/.bob-key.env`; about 0.023 coins per call. Coins used so far: about 0.15 |
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
| ROOK-011 | Export + Verifier + Test Runner | P0 | IN PROGRESS | coder (account 2) |
| ROOK-012 | Parallel steps (race) | P1 | DONE | reviewer PASS; stock race found seeds 1-10 (≤82 seqs); replay 10/10; flaky flag validated in 010 |
| ROOK-013 | Sandbox + ProcessSandbox | P0 | DONE | reviewer PASS on round 2 (settable_env whitelist + env denylist, fullmatch SHA) |
| ROOK-014 | DockerSandbox | P0 | IN PROGRESS | round 1 FAIL (run network not internal → egress open); fixing with proxy sidecar |
| ROOK-015 | BobClient + recorder | P0 | DONE | reviewer PASS on round 2 (env allowlist) |
| ROOK-016 | Agent registry, prompts, modes | P0 | DONE | reviewer PASS on round 2 (case-insensitive .git, control chars, entity tags); note: NFKC-normalise paths as hardening |
| ROOK-017 | Scout → Mechanic → Mapper | P0 | TODO | |
| ROOK-018 | Lawmaker + Rule Critic | P0 | TODO | |
| ROOK-019 | Test Designer + Strategist | P1 | TODO | |
| ROOK-020 | Detective + Diagnosis Reviewer | P0 | TODO | |
| ROOK-021 | Surgeon + path guard + Fix Reviewer | P0 | TODO | |
| ROOK-022 | Coordinator + rails + Guide | P0 | DONE | reviewer PASS; rails in core/rails.py. Follow-ups: wrap Guide snapshot as untrusted; CostUpdate ge=0 + monotonic cost in RunState |
| ROOK-023 | Session + Conductor end to end | P0 | TODO | |
| ROOK-024 | Typer commands + CI mode | P0 | TODO | |
| ROOK-025 | TUI shell | P0 | TODO | |
| ROOK-026 | Sprite + row widgets | P0 | TODO | |
| ROOK-027 | Question prompts + cards | P0 | TODO | |
| ROOK-028 | Background run + chat | P0 | TODO | |
| ROOK-029 | FastAPI server | P0 | TODO | |
| ROOK-030 | Auth (Supabase + CLI login) | P1 | TODO | needs U1 |
| ROOK-031 | GitHub App integration | P1 | TODO | needs U2 |
| ROOK-032 | GitHub Action | P1 | TODO | |
| ROOK-033 | Web scaffold + event client | P0 | TODO | |
| ROOK-034 | Web sprite + rows | P0 | TODO | |
| ROOK-035 | Web cards + answers + chat | P0 | TODO | |
| ROOK-036 | Web pages, picker, guest | P0 | TODO | |
| ROOK-037 | Hugging Face Space image | P0 | TODO | needs U3 |
| ROOK-038 | Vercel deploy | P0 | TODO | needs U4 |
| ROOK-039 | Demo apps integration + recordings | P0 | TODO | needs U5 |
| ROOK-040 | Release polish + PyPI | P1 | TODO | |

Statuses: `TODO` · `IN PROGRESS` · `IN REVIEW` · `DONE` · `BLOCKED (reason)`

## User tasks

| ID | Task | Status |
|---|---|---|
| U1 | Supabase + Google OAuth | TODO |
| U2 | GitHub App "Rook" | TODO |
| U3 | Hugging Face Docker Space | TODO |
| U4 | Vercel project | TODO |
| U5 | 3 demo apps via Antigravity | TODO (ask Claude for the prompt) |
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
- 26 Sep: Google sign-in (Supabase) + a separate GitHub App connect; guest demo mode on the web.
