# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**State:** ROOK-001, 002, 004 and 005 are DONE and committed. ROOK-003 is coded and failed review round 1 (O(n²) template regex, a DoS); the coder is fixing it and it needs re-review before commit.
**Do next:** finish ROOK-003 (re-review, then commit), then the engine: ROOK-006 (HTTP executor) → 007 → 008 → 009 → 010 → 011 → 012. Tickets with no dependency on each other can run as parallel coders on separate files (as was done for 002–005).
**How:** the orchestrator sends each ticket to the `coder` sub-agent, then the `reviewer` sub-agent (CLAUDE.md, section 2).
**Watch out:**
- Sub-agents: `coder` = Opus 5.5 at medium effort, `reviewer` = Sonnet 5 at medium effort (set in `.claude/agents/*.md`). They only load in a session started *after* the files existed. In the session that created them, run them as `general-purpose` agents told to read their `.md`, with the model override (opus / sonnet).
- Bob calls need `source ~/.bob-key.env` and Node 24 on `PATH` (`~/.nvm/versions/node/v24.21.0/bin`). **Always use stdin=DEVNULL.**
- Keep Bob spend low during development: use recorded NDJSON fixtures for tests and the `-m bob` marker only for manual live checks.
- The mockups in `docs/mockups/` use the old name "Counterexample" / `cx`; treat that as Rook / `rook`.

**Open questions for the user:** none right now. When needed, ask for: the demo-apps prompt (U5), the Supabase keys (U1), the GitHub App (U2), the Hugging Face Space (U3) and the Vercel project (U4).

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

**Current goal:** Implement M1 + M2 (ROOK-001 → ROOK-012): the foundation and the deterministic engine on the minishop fixture.

---

## Session log (newest first)

| When (IST) | Account | Did | Commit |
|---|---|---|---|
| 26 Sep 13:48 | 1 | ROOK-002, 004 (after a work-budget fix) and 005 PASS + committed; 003 in fix round | ROOK-002/004/005 |
| 26 Sep 13:36 | 1 | ROOK-001 scaffold (coder → reviewer PASS) | ROOK-001 |
| 26 Sep 13:25 | 1 | Design finalised with the user; wrote CLAUDE.md, the coder/reviewer sub-agents, docs 01–05, STATUS, HANDOFF and README; created the GitHub repo | (see git log) |
| 26 Sep 12:20 | 1 | Verified Bob Shell 2.0.5: `bob run --format json/stream-json`, custom modes via `.bob/custom_modes.yaml`, about 0.023 coins per call; the Lawmaker test found the refund invariant from code | (none) |

## Useful facts
- Mockups (the same files as in `docs/mockups/`, also published privately for the user): walkthrough, terminal session, agent characters, web app.
- The hackathon requires a URL, an MP4 of 5 minutes or less, a PDF deck, and a public repo. Bob IDE use is mandatory; Bob Shell is optional (we use both).
- The user is in IST. `gh` is logged in as `tony19053000`.
