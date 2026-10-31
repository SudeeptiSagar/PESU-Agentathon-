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
| GitHub issues | **Not created yet.** The planning session's GitHub token got `403 Resource not accessible by integration` on labels, milestones and issues for this repo. Run the script yourself (Section 3) |
| Git | Planning files committed as the first commit on `main`. The push from the planning session was refused (the Claude GitHub App isn't installed on Sudeepti's account), so it is pushed from Prashanth's machine (Section 3) |
| Code | None yet. CORE-01 (skeleton) is the first thing to build |

## 2. Team and tickets

| Member | GitHub | Role | Tickets |
|---|---|---|---|
| M1 Prashanth | `pruthviprashanth` | Core backend and integration (lead) | CORE-01 to CORE-13 |
| M2 Vishal | `VishalAprameya4` | UI, frontend and voice | UI-01 to UI-08 |
| M3 Sudeepti | `SudeeptiSagar` | Browser perception and sites | BRW-01 to BRW-09 |
| M4 Abishek | `abishekraom` | Jev, verification and demo | JEV-01 to JEV-09 |

All four usernames were checked as assignable on the repo.

## 3. Do these first (about 10 minutes)

From the repo root on your own machine:

```bash
# 1. If main is still empty on GitHub, push the first commit from the bundle
git clone pesu-agentathon.bundle PESU-Agentathon- && cd PESU-Agentathon-
git remote set-url origin https://github.com/SudeeptiSagar/PESU-Agentathon-.git
git push -u origin main
#    If main already has the commit: git clone https://github.com/SudeeptiSagar/PESU-Agentathon-.git

# 2. Create labels, milestones and the 39 assigned issues with your own GitHub login
gh auth status                 # must be logged in as pruthviprashanth with repo access
python3 scripts/create_issues.py --dry-run
python3 scripts/create_issues.py
```

If the script fails on labels or milestones, check that you have push access to the repo (Sudeepti can grant "Write" or "Maintain"). It skips anything that already exists, so it is safe to re-run.

Then tell the team: pull main, read `docs/PRD.md` "What changed in 3.0", and paste their block from `docs/TEAM_PROMPTS.md`.

## 4. Your next build steps (M1)

1. **CORE-01 skeleton** on branch `core/CORE-01-skeleton`. Target: merged by **19:30 (CP1)**. Everyone else is blocked on it for code. Prompt is in `docs/TEAM_PROMPTS.md`.
2. CORE-04 `config.py`, CORE-02 `llm.py`, then CORE-03 reliability test (result due at **20:30, CP2**).
3. CORE-05 reference notes (read `pascalLangdock/elevenlabs_hack` `backend/`, ideas only, no copying).
4. CORE-06 state machine, CORE-07 profile, CORE-08 executor and domain policy, CORE-09 site resolution (CP3, 23:00).
5. CORE-10 agent loop, CORE-11 integration, CORE-12 confirmation flow (CP4, 01:00).

Checkpoints: CP1 19:30, CP2 20:30, CP3 23:00, CP4 01:00, CP5 04:00, freeze 11:00 Sunday.

## 5. Decisions made (do not reopen without a reason)

- Speech recognition: **Handy**, via the Voice Console page that catches its paste. Fallback after the 20:30 gate fails: faster-whisper + silero-vad behind the same `STT` interface.
- Speech output: **Piper**; fallback is browser `speechSynthesis` through the Console.
- LLM: **Ollama** (`qwen3:8b` default), behind one `llm()` function so an API can be swapped in.
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

## 7. Prompt for the fresh session

Paste this into a new Claude Code session opened in the repo:

```
Read HANDOFF.md, CLAUDE.md and docs/PRD.md (v3.0) first. I am Prashanth, M1 (core backend and
integration lead) on a 24-hour hackathon. Confirm the current state from HANDOFF.md in 3 lines, then
start CORE-01 using my prompt in docs/TEAM_PROMPTS.md, on branch core/CORE-01-skeleton. Stubs only for
other owners' modules. Finish with the real output of `python -m app.main` (health and WebSocket echo)
and `pytest -q`, then give me a PR title and description with "Closes #<CORE-01 issue number>".
```
