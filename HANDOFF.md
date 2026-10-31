# Handoff: start here in a fresh session

Written Sat 31 Oct 2026, about 18:30 IST, at the end of the planning session. Owner: Prashanth (M1, lead).

## 1. Where things stand

| Item | State |
|---|---|
| Product | Pivoted to a **fully autonomous voice-controlled browser** (PRD v3.0). Government forms are now one demo task, not the product |
| `docs/PRD.md` | v3.0, final for build. Sections 10 (safety), 12 (contract), 13 (ownership), 21 (backlog) are the ones that matter |
| `CLAUDE.md` / `AGENTS.md` | Updated for v3.0 (identical files) |
| `docs/TEAM_PROMPTS.md` | Starter prompts for M1 to M4, updated for v3.0 |
| `scripts/tickets.json` | 39 tickets generated from PRD Section 21, with assignees |
| `scripts/create_issues.py` | Creates labels, milestones and assigned issues; safe to re-run |
| GitHub issues | **Created.** Per-member umbrella issues #1 to #4 (M1 to M4) and 39 per-ticket issues #6 to #44 with labels, milestones and assignees. CORE-14 is added by the 3.1 docs PR |
| Git | `main` is on GitHub. Open PRs, to merge in this order: #5 (CORE-01 skeleton) then #45 (CORE-02 `llm.py`, stacked on #5) then the 3.1 docs PR (stacked on #45). Change each PR's base to `main` after the one below it merges |
| Code | CORE-01 skeleton (PR #5) and CORE-02 `llm.py` (PR #45) written and tested (38 tests). Everything else is a stub marked `# STUB: <ticket>` |

## 2. Team and tickets

| Member | GitHub | Role | Tickets |
|---|---|---|---|
| M1 Prashanth | `pruthviprashanth` | Core backend and integration (lead) | CORE-01 to CORE-13 |
| M2 Vishal | `VishalAprameya4` | UI, frontend and voice | UI-01 to UI-08 |
| M3 Sudeepti | `SudeeptiSagar` | Browser perception and sites | BRW-01 to BRW-09 |
| M4 Abishek | `abishekraom` | Jev, verification and demo | JEV-01 to JEV-09 |

All four usernames were checked as assignable on the repo.

## 3. Done in the first build session (31 Oct evening)

- `main` pushed; per-member issues #1 to #4 and per-ticket issues #6 to #44 created.
- PR #5 (CORE-01, `Closes #6`) and PR #45 (CORE-02, `Refs #7`) opened.
- Real-Ollama check of `llm.py` with `qwen3:8b` on a teammate's laptop (`docs/OLLAMA_CHECK.md`, `scripts/check_llm.py`): reachable, plain reply and a real `fill_field` tool call passed; the `num_ctx` check failed on `/v1`. `llm.py` was switched to the native `/api/chat`. **The re-check is still pending.**
- Scope 3.1 added: start key (CORE-14) and the Task D stretch (see the PRD "What changed in 3.1").

Tell the team: pull `main` after #5 merges, read the PRD "What changed in 3.0" and "3.1", and paste your block from `docs/TEAM_PROMPTS.md`.

## 4. Your next build steps (M1)

1. Merge PR #5, then #45 (after the `num_ctx` re-check passes), then the 3.1 docs PR.
2. CORE-04 review of `config.py`, CORE-03 reliability test (result due at **20:30, CP2**), CORE-05 reference notes.
3. CORE-06 state machine, CORE-07 profile, CORE-08 executor and domain policy, CORE-09 site resolution (CP3, 23:00).
4. CORE-10 agent loop, CORE-11 integration, CORE-12 confirmation flow (CP4, 01:00).
5. CORE-14 start script and keyboard shortcut (CP5), CORE-13 final integration and freeze.

Checkpoints: CP1 19:30, CP2 20:30, CP3 23:00, CP4 01:00, CP5 04:00, freeze 11:00 Sunday.

## 5. Decisions made (do not reopen without a reason)

- Speech recognition: **Handy**, via the Voice Console page that catches its paste. Fallback after the 20:30 gate fails: faster-whisper + silero-vad behind the same `STT` interface.
- Speech output: **Piper**; fallback is browser `speechSynthesis` through the Console.
- LLM: **Ollama** (`qwen3:8b` default) through its **native `/api/chat`**, behind one `llm()` function so an API can be swapped in. The OpenAI-compatible `/v1` endpoint ignored `num_ctx` (prompt cut to 2050 tokens), so it is not used.
- Start key: an OS keyboard shortcut runs `scripts/start.*` (CORE-14); Handy's hold-to-talk key is the in-app key. No wake word for the demo.
- Task D (stretch): read the newest Gmail message in the user's own Chrome, read-only, by attaching over CDP (BRW-07, P1 stretch). Rejected: separate agent profile, Gmail API.
- Browser: **our own Playwright tool layer**, not browser-use, so the safety checks sit in the action path.
- Safety: placeholders for profile values; irreversible controls held as `pending_action` and committed only after "confirm"; domain policy in code; CAPTCHA, OTP, passwords and payment always handed to the user; "stop" always works.
- Jev: deterministic rules first, Jev semantic check second; switchable backend.
- Demo: Task A open-web lookup, Task B mock portal form with the planted PIN-code trap, Task C mock shop that stops at payment (P1).
- The reference repo is a design reference only (no visible license, `backend/` not yet read).

## 6. Open questions

- Real submission and demo time (PRD assumes Sunday 16:00 IST).
- Hackathon rules on open-source and reference code.
- Jev access (M4 reports by 19:00).
- Which machine hosts Ollama, and can everyone reach it.
- Venue network: are real sites and the search engine reachable (M3, by 20:30).
- Does Chrome attach over CDP work on the demo machine, and do `snapshot` and `main_text` cope with the real Gmail page (M3, BRW-07)?
- Re-run `scripts/check_llm.py` after the native-API change and post the output in #7 (the `num_ctx` check must pass).

## 7. Prompt for the fresh session

Paste this into a new Claude Code session opened in the repo:

```
Read HANDOFF.md, CLAUDE.md and docs/PRD.md (v3.1) first. I am Prashanth, M1 (core backend and
integration lead). Confirm the current state from HANDOFF.md in 3 lines (open PRs, what is verified,
what is pending), check `gh pr list` for changes since, then continue with the next M1 step in
Section 4. One ticket at a time, on a branch named core/<TICKET-ID>-<short-name>. Report real test output.
```
