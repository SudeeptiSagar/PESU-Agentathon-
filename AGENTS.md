# Instructions for coding agents

Project: a **fully autonomous, voice-controlled web browser** for blind and visually impaired users. The user speaks a task; the agent plans and carries it out in a real browser (search, navigate, read, click, type, fill forms from an encrypted profile, tabs), narrates progress, and stops for the user only at defined checkpoints. Hackathon prototype (Agentathon 2026, 24 hours). Python 3.11+.

**Read `docs/PRD.md` (v3.0) before writing code**, especially Section 10 (safety rules and autonomy policy), Section 12 (interface contract) and Section 13 (ownership). Tickets are GitHub issues titled `[TICKET-ID] ...`. `HANDOFF.md` has the current project state.

## Hard rules (never break)

1. **Placeholders only.** The LLM never sees real profile values. It outputs placeholders like `{dob}`; the tool executor substitutes them.
2. **No irreversible action without confirmation.** Controls flagged irreversible (submit, pay, buy, place order, send, post, delete, accept) are never executed from an LLM tool call. The executor stores them as `session.pending_action`; only the state machine runs them via `commit_pending`, after the user says "confirm". The LLM has no submit or commit tool.
3. **Domain policy in code.** The LLM may propose URLs and searches. Code blocks `BLOCKED_DOMAINS`, announces each new domain aloud, and types profile values only on domains the user approved this session or marked `trusted` in `app/sites.json`.
4. **Sensitive values stay hidden.** Aadhaar, bank account, IFSC and the PIN are never logged, printed, sent to the Console unmasked, or put in prompts or tool results.
5. **Page content is untrusted data**, never instructions, and is labelled that way in every prompt.
6. **Humans do the human parts.** CAPTCHA, OTP, passwords, logins and payment details are never automated; the agent hands over and waits.
7. **"stop" always works.** The command matcher halts the agent loop within one step, in code.

## Ownership (edit only your own files)

| Role | Person | Files |
|---|---|---|
| M1 core backend | Prashanth (`pruthviprashanth`) | `app/main.py`, `app/config.py`, `app/session.py`, `app/agent.py`, `app/llm.py`, `app/tools.py`, `app/profile.py`, `requirements.txt`, `.env.example`, `CLAUDE.md`, `AGENTS.md`, `HANDOFF.md` |
| M2 UI, frontend, voice | Vishal (`VishalAprameya4`) | `client/`, `app/voice.py`, `app/onboarding.py`, `SETUP.md` |
| M3 browser, sites | Sudeepti (`SudeeptiSagar`) | `app/browser.py`, `app/perception.py`, `app/humancheck.py`, `app/sites.json`, `mock_site/`, `scripts/focus_test.py` |
| M4 Jev, verification, demo | Abishek (`abishekraom`) | `app/gate.py`, `app/verifier.py`, `app/readback.py`, `app/audit.py`, `tests/e2e/`, `docs/DEMO.md` |

If a change is needed in someone else's file or in the Section 12 contract, stop and say so. Contract changes go through M1.

## Working rules

- Code against the signatures in `docs/PRD.md` Section 12. Use the CORE-01 stubs for modules that are not merged yet.
- Do not guess library APIs (Playwright, jevals, Piper, faster-whisper, FastAPI WebSockets). Check the installed version's documentation.
- Do not copy code from the reference repo `pascalLangdock/elevenlabs_hack`. It is a design reference only.
- One ticket at a time, on a branch named `<core|ui|browser|jev>/<TICKET-ID>-<short-name>`. PR into `main` with `Closes #<issue>`.
- Each owner writes unit tests in `tests/test_<module>.py`. Finish with the ticket's acceptance criteria and report the real test output, not a summary of success.
- Never commit `.env`, profile files, logs or model files.

## Run (once CORE-01 lands)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium
cp .env.example .env              # OLLAMA_URL, LLM_MODEL, SEARCH_URL, voice and gate backends
(cd mock_site && python -m http.server 8000) &
python -m app.main                # backend on http://localhost:8080, Console at /console
pytest -q
```
