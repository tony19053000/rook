# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**Updated:** 26 Sep 15:30 IST. Account 2 stopped (user switching accounts). All background agents were stopped; Docker has no leftover `rook.sandbox` containers.

**Committed and DONE (reviewer PASS):** ROOK-001–010, 012, 013, 014, 015, 016, 017, 022 (17 / 40). M1, M3 complete; M2 7/8; M4 4/8. Pushed to GitHub. Bob coins used ≈ 0.30 of 40.

**UNCOMMITTED work in the working tree:**
1. ~~ROOK-011~~ **DONE + committed by account 1 (round 2 PASS).** Old notes: — coded, **review round 1 = FAIL**, the fix-round coder was stopped before (or while) making changes, so treat the files as round-1 code:
   `src/rook/export/counterexample.py`, `src/rook/export/tests.py`, `src/rook/engine/verifier.py`, `src/rook/engine/testrunner.py`, `tests/unit/test_export.py`, `test_testrunner.py`, `test_verifier.py`, `tests/integration/test_verify_minishop.py`.
   Everything else passed review (all ACs, AST-checked generated test, pytest isolation, env isolation). Send this to `coder` (round 2), then `reviewer`, commit as `ROOK-011`:
   - F1 (security): `counterexample.py` ~248-256 `safe_dir` calls `mkdir(parents=True)` BEFORE the inside-root check, so a planted symlink `<root>/rook -> /outside` creates `/outside/counterexamples` (or `/outside/tests`) before PermissionError. Fix: walk components with dir fds (`os.open(name, O_DIRECTORY|O_NOFOLLOW, dir_fd=parent)`, `os.mkdir(name, dir_fd=parent)`), write the leaf via that fd. Extend `test_writes_refuse_symlinks_out_of_the_root` to assert NOTHING (not even a dir) is created outside, for both dirs and a deeper symlink (`rook/tests -> outside`).
   - Cheap extras: check 4 (fresh_search) must fail if no step got a <400 response ("could not exercise the app"); depth/size cap on `observed` before JSON/AST.
2. ~~ROOK-018~~ **DONE + committed by account 1.** OPEN DECISION for user: a response rule that fails on the 1st request on the buggy app (admin_export as customer) is rejected, so the admin bug is never searched. Proposed option B: flag it as 'possibly already broken' for the human instead of rejecting (do in 023, doc change). Old notes: — coder was stopped at the very start; **no files were written**. Start it fresh (brief below).

**Then continue in order:** 011 (fix) → 018 → 020 (deps 011) → 019 → 021 → 023 (Session) → M6 CLI (024–028) → 029 server → M8/M9 web → M10 deploy.
Parallel pairs that worked: 011-fix ‖ 018; later 019 ‖ 020.

**ROOK-018 brief (for the coder):** follow the ROOK-017 pattern (`src/rook/agents/understand.py`, `tests/unit/test_pipeline_understand.py`: recorded replay in the default suite + one `@pytest.mark.bob` live test + a secret scan of recordings). Reuse the recorded understand run (`tests/fixtures/recordings/understand_minishop/`) so only Lawmaker/Critic calls cost coins; budget ≤1.5 coins. The ENGINE sanity-checks each rule (parses with the safe evaluator + holds on a fresh app); the critic judges meaning only. AC: produces refund, stock, ship, admin rules; a rule that fails on a fresh app is auto-rejected with a reason. **Known issue:** ROOK-017's dry-run treats status ≥400 as failure — a response rule like `admin_export_forbidden` (expected 401/403 on a fixed app) must not be rejected for that.

**Open decisions for the user:**
- ROOK-007 throughput: 268 seq/s measured (target 500). Ceiling is minishop itself (sync `current_user` + O(n) user scans); engine alone ≈750/s. Recorded in STATUS as not met.
- ROOK-014: sandboxed apps have NO internet at run time. Apps that need it would need a new `SandboxPlan.egress` field (contract change in 02 §8) — not added; ask the user if a demo app needs it.

**Follow-ups noted (non-blocking, from reviews):** Mechanic fileRegex `^\.rook-sandbox/` (registry.py:26) never matches (Bob matches ABSOLUTE paths): fix like surgeon_edit_regex or drop the unused edit group; per-actor cookie jars on the real-HTTP executor path; reject `inf` generator weights; wrap Guide snapshot as `<untrusted>`; `CostUpdate` ge=0 + monotonic cost in RunState; NFKC-normalise Surgeon paths; recordings contain local `/tmp/pytest-of-aayush` paths; document cx JSON shape in 02 §7.8.

**Lessons from this session:**
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

**Current goal:** Fix + commit ROOK-011 (review F1), build ROOK-018, then 020 → 019 → 021 → 023 → M6 CLI (see "Next session starts here").

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
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
