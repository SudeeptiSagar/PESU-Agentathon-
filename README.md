# Autonomous Voice Browser (Agentathon 2026)

A fully autonomous, voice-controlled web browser for blind and visually impaired users. Say what you want done; the agent searches, navigates, reads, clicks, types and fills forms from an encrypted local profile, narrating as it goes. It stops for you only at checkpoints: irreversible actions (submit, pay, send, delete), sensitive data on a new site, and CAPTCHA, OTP, login or payment steps. Before anything irreversible it checks the real values on the page and reads them back for your spoken "confirm".

- Product and plan: [`docs/PRD.md`](docs/PRD.md) (v3.0)
- Current state and next steps: [`HANDOFF.md`](HANDOFF.md)
- Rules for coding agents: [`CLAUDE.md`](CLAUDE.md) (same as `AGENTS.md`)
- Starter prompts per team member: [`docs/TEAM_PROMPTS.md`](docs/TEAM_PROMPTS.md)
- Tickets: GitHub issues, created from [`scripts/tickets.json`](scripts/tickets.json) by [`scripts/create_issues.py`](scripts/create_issues.py)

## Team

| Role | Person |
|---|---|
| M1 core backend and integration (lead) | Prashanth |
| M2 UI, frontend and voice | Vishal |
| M3 browser perception and sites | Sudeepti |
| M4 Jev, verification and demo | Abishek |

## Stack

Python, FastAPI, Playwright, Ollama (local LLM), Handy (speech recognition), Piper (speech output), Jev via jevals (safety gate).

Credits: [Handy](https://github.com/cjpais/Handy) (MIT) for offline speech recognition. Wayfinder (`pascalLangdock/elevenlabs_hack`) was used as a design reference only.
