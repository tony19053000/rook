# HANDOFF: session-to-session continuity

> Two Claude Code accounts take turns on this repo. **Update this file after every ticket**, because a session can end at any moment. The next session reads it first (CLAUDE.md, section 0).

---

## ▶ Next session starts here

**State:** Docs, rules and sub-agents are done and committed. No product code exists yet.
**Do next:** start the ticket loop at **ROOK-001 (Project scaffold)**, then 002 → 003 → 004 → 005 … in order (see `STATUS.md`).
**How:** the orchestrator sends each ticket to the `coder` sub-agent, then the `reviewer` sub-agent (CLAUDE.md, section 2).
**Watch out:**
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
| 26 Sep 13:50 | 1 | Design finalised with the user; wrote CLAUDE.md, the coder/reviewer sub-agents, docs 01–05, STATUS, HANDOFF and README; created the GitHub repo | (see git log) |
| 26 Sep 12:20 | 1 | Verified Bob Shell 2.0.5: `bob run --format json/stream-json`, custom modes via `.bob/custom_modes.yaml`, about 0.023 coins per call; the Lawmaker test found the refund invariant from code | (none) |

## Useful facts
- Mockups (the same files as in `docs/mockups/`, also published privately for the user): walkthrough, terminal session, agent characters, web app.
- The hackathon requires a URL, an MP4 of 5 minutes or less, a PDF deck, and a public repo. Bob IDE use is mandatory; Bob Shell is optional (we use both).
- The user is in IST. `gh` is logged in as `tony19053000`.
