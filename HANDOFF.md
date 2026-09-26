# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**Updated:** 26 Sep 20:00 IST. Account 1 stopped ("update handoff"). All 4 background coders were STOPPED; no pytest/bob/minishop processes left (the node bob pids 70572/70580 are the user's interactive Bob from 12:18, so leave them). ONLY ONE orchestrator session at a time.

**Committed and DONE (reviewer PASS):** ROOK-001–022, 025, 026, 027, 033 (26 / 40). HEAD 4705c23 before this docs commit. Bob coins ≈ 2.4 of 40 (the 023 recordings total 0.34).

**UNCOMMITTED work in the tree (do NOT commit before a reviewer PASS):**
1. **ROOK-023 (Session + Conductor, incl. admin rule B)**: coded; review FAIL round 1 of 3; a fix round was stopped midway. Files: core/session.py, core/workspace.py, engine/sanity.py, agents/rules.py, diagnose.py, fix.py, guide.py, core/events.py, store/repo.py, docs/02_ARCHITECTURE.md; tests/unit/session_helpers.py, test_session.py, test_session_recorded.py, test_sanity.py, test_pipeline_rules.py, test_events.py, test_store.py; tests/fixtures/recordings/session_minishop/ (10 files, scrubbed). Findings to fix (send a coder):
   a. SECURITY: workspace.py `_copy` uses copytree(symlinks=True). A symlink in an untrusted repo pointing outside (/etc/passwd, ~/.ssh, ~/.bob-key.env) is readable in the workspace where Bob runs on the host. Skip links that escape the source root (absolute, ../, chains, dir links) with a warn; the same for GitHub clones (core.symlinks=false or a post-clone scan). Tests for each case.
   b. FLAKY: test_session.py::test_cancel_at_every_phase_leaves_no_process_behind[PREPARE] fails ~1/10 runs solo. Root-cause the race (cancel vs to_thread(prepare_workspace) / SandboxTracker) and prove 30x with 0 failures. (The coder was mid-debug: "a child process outlived the 10 s wait".)
   c. mypy (`uv run --with mypy mypy`): events.py:416, fix.py:91, fix.py:488.
   Then the reviewer (round 2), then commit `ROOK-023: Session + Conductor end to end`.
2. **ROOK-025 (TUI shell)**: review FAIL round 2 of 3 (the LAST round). Control-char fix verified. Remaining: `clean_data` flattened \n, so the fix.ready diff loses its lines. The round-3 coder was stopped PARTWAY: `safe_text.clean_multiline` exists and render.py references it. Finish: clean_multiline keeps \n (\r\n/\r→\n, \t\v\f→space, strips other C0/DEL/C1); clean_data uses it for values; single-line chrome still uses clean; tests (`clean_data({"diff":"-a\r\n+b\n c"})["diff"]=="-a\n+b\n c"`, one-line rows stay one line). Files: cli/logo.py, cli/tui/{app,__main__,auth,backend,commands,history,render}.py, widgets/shell.py, safe_text.py (modified, additive), tests/unit/test_tui_app.py, test_tui_commands.py, tui_samples.py. If round 3 fails → BLOCKED per the rules (tell the user).
3. **ROOK-027 (prompts + cards)** and **ROOK-029 (FastAPI server)**: were started, then stopped; NO files written. Restart from scratch (briefs below).

**Next steps in order (run in parallel on separate files):** fix 023 + finish 025 → review both → commit. Start 029 (server) and 027 (cards) in parallel now (neither edits 023/025 files). After 025 passes: 024 (Typer commands, CI mode, bare `rook` → `run_tui()`, update test_smoke). Then 028 → 030/031/032 (need U1/U2) → 034–036 web → 037–040 deploy.

**Brief notes for 029:** routes per 02 §11 except auth/GitHub (seam for 030/031); SSE `after` resume; owner checks (404); guest cookie + demo-only + quotas; CORS for the web origin with credentials + Authorization (never *); rate + size limits. Match web/lib/sse.ts + api.ts (fetch-streamed SSE with Bearer, envelope JSON with seq, fatal 400/401/403/404/410, pct 0–100). DECISION: the web calls the API through a same-origin Vercel rewrite proxy (/api/v1/* → HF Space), so the guest cookie stays first-party SameSite=Lax; note it in 03 and pin the open §11 response shapes in 02. Tests use a fake Session or the recorded run (0 coins, no Docker).
**Brief notes for 027:** menu/confirm/setup-value prompts (mask secrets), rules/counterexample/diagnosis/fix-diff/verify/PR cards, the shrink line (04 §2.2). An `already_broken` rule is shown "possibly already broken" and NOT pre-selected. Plug in only via 025 seams (`app.views[type]`, `transcript.mount_item`, `backend.answer`); new files widgets/prompts.py and cards.py; clean all payload text; fits 80 cols.

**Then continue in order:** 023 → M6 CLI (024–028) → 029 server → M8/M9 web → M10 deploy.

**Session API notes for 024/029:** DiagnosePipeline(client, ws).run(model, cx, executor, sandbox=, summary=); FixPipeline gated by rails fix approval; edit tapes store only guard-approved files.

**Open decisions for the user:**
- ~~ADMIN RULE~~ DECIDED 26 Sep 18:40: **B**. A response rule broken on the 1st request is flagged 'possibly already broken' and needs explicit human approval (never auto-approved by --auto). Implemented inside 023.
- Live Bob recording for 023 approved, cap 3 coins.
- Start TUI (025/026) early on fake events while 023 finishes? (recommended yes)
- ROOK-007 throughput: 268 seq/s measured (target 500). Ceiling is minishop itself (sync `current_user` + O(n) user scans); engine alone ≈750/s. Recorded in STATUS as not met.
- ROOK-014: sandboxed apps have NO internet at run time. Apps that need it would need a new `SandboxPlan.egress` field (contract change in 02 §8) — not added; ask the user if a demo app needs it.

**Follow-ups noted (non-blocking, from reviews):** Mechanic fileRegex `^\.rook-sandbox/` (registry.py:26) never matches (Bob matches ABSOLUTE paths): fix like surgeon_edit_regex or drop the unused edit group; per-actor cookie jars on the real-HTTP executor path; reject `inf` generator weights; wrap Guide snapshot as `<untrusted>`; `CostUpdate` ge=0 + monotonic cost in RunState; NFKC-normalise Surgeon paths; understand_minishop recordings still contain local `/tmp/pytest-of-aayush` paths (018–021 recordings are scrubbed); document cx JSON shape in 02 §7.8.

**Lessons from this session:**
- Bob matches mode `fileRegex` against ABSOLUTE paths (found live in 021).
- Recording edit tapes must be written only AFTER the path guard (021 review).
- redact_text heuristics can alter app source ("missing bearer token") — never redact file contents that must replay byte-exact.
- Always give the reviewer attack ideas — it found real bugs in 013 (LD_PRELOAD env), 014 (open egress, then compose hostname DNS hijack: 11/20 requests stolen), 011 (mkdir symlink escape).
- Parallel coders on separate files work well; tell each which files NOT to touch. A reviewer may see transient failures from another coder's in-progress file — re-run before blaming.
- `ROOK_SLOW=1` enables the slow 20k-sequence tests; Docker tests: `uv run pytest -q -m docker`.
- Live Bob recordings live in `tests/fixtures/recordings/<name>/` (only that path is un-ignored). Re-record if prompts/templates change.

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

**Current goal:** Finish + review + commit ROOK-023 (Session, uncommitted in tree), then M6 CLI 024–028 → 029 server → web → deploy. Ask the user the open A/B admin-rule decision.

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
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
