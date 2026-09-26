# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**Updated:** 26 Sep 14:08 IST. Account 1 stopped at about 90% of its 5-hour limit.

**Committed and DONE (reviewer PASS):** ROOK-001, 002, 003, 004, 005, 006, 015, 016, 022, 013, 007, 008, 012, 009, 010, 014, 017 (account 2). M1 is complete.

**UNCOMMITTED work in the working tree (verify it before anything else):**
1. ~~ROOK-016~~ DONE and committed by account 2 (was: coded, and the review was in progress when the session ended.
   Files: `src/rook/agents/schemas.py`, `registry.py`, `modes.py`, `prompts/__init__.py`, `prompts/*.md`, `tests/unit/test_agents_registry.py`.
   **Review round 1 = FAIL** (374 tests pass; everything else verified). Send these fixes to the `coder` sub-agent, then re-review, then commit as `ROOK-016`:
   - F1 (security): `registry.py` around line 154, `_check_path` compares path parts with `FORBIDDEN_DIRS {".bob", ".git"}` case-sensitively, so `A/.GIT/config` is accepted, which is the real .git on case-insensitive filesystems. Compare `part.lower()`.
   - F2 (security): `_check_path` (around lines 144-153) accepts embedded control characters (`notes\n.git/config`), and `_escape` doesn't escape `\n`. Reject any character with `ord < 0x20` or `== 0x7f` in a path.
   - Also: add explicit prose to `prompts/mapper.md` that every `{{ref.x}}` var must be listed in `requires` and produced by some action's `capture`; and in `prompts/__init__.py` also neutralise the HTML-entity form `&lt;/untrusted` (or add a banner line saying entity-encoded tags are data). Add tests for all of these.
2. **ROOK-007 + ROOK-008 (Generator + Runner + Judge)**: that coder was **stopped mid-work at 14:11 IST** (the user asked to stop), so treat the files as PARTIAL and unreviewed:
   `src/rook/engine/generator.py`, `judge.py`, `runner.py` and `tests/unit/test_generator.py`, `test_judge.py`, `test_runner.py` (possibly also small additive changes in `executor.py`).
   Run `git status` and `uv run pytest -q`. If they're incomplete, send the ticket to the `coder` sub-agent to finish it (both tickets' ACs in `docs/05_FEATURE_TICKETS.md`, including ≥500 seq/s or an honest measured ceiling, zero violations on fixed minishop, and finding the refund bug for 5 seeds). Then review and commit.
3. Docs wording (13 agents = Coordinator + 12 specialists) is committed.

**Then continue in order:** 009 (Shrinker) → 010 (Replayer) → 011 (Export + Verifier) → 012 (parallel race) → 013/014 (sandbox) → 017–022 (agent pipelines) → 023 (Session) → M6 CLI.
Independent tickets may run as parallel coders on separate files (this worked well for 002–005). Commit each on PASS, update the STATUS progress bars, and update this file after every ticket.

**Lessons from this session:**
- The reviewer finds real bugs (O(n²) regexes, nested-loop DoS, gather task leaks, env leaks). Always review, and always give the reviewer attack ideas.
- Per-ticket scope: tell each coder which files to stay in, and tell it not to edit pyproject.toml or uv.lock when others run in parallel.
- Bob facts: `cwd` MUST be the workspace; stdin DEVNULL; child env allowlisted (done in bob.py). Coins used ≈ 0.15 of 40.
- Performance note: the executor alone does about 290 seq/s in-process on minishop; 007 must optimise (touched-entity state reads, concurrency, caching the admin setup).

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

**Current goal:** Verify and commit ROOK-016 and ROOK-007+008 (see "Next session starts here"), then finish M2 (ROOK-009 → 012), M3 (013, 014) and M4 (017 → 022).

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
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
