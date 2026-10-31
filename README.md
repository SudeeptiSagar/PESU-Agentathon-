# Autonomous Voice Browser (Agentathon 2026)

A fully autonomous, voice-controlled web browser for blind and visually impaired users. You say what you want done, and the agent plans and carries it out in a real browser. It searches, navigates, reads pages aloud, clicks, types, fills forms from an encrypted local profile and handles tabs, narrating as it goes. It is a conversation: "open Chrome", then "open Gmail", then "read my last mail", each against the same browser.

It stops for you only at checkpoints:
- **before anything irreversible** (submit, pay, send, delete, accept), after checking the real values on the page and reading them back, until you say "confirm";
- **before sensitive data on a new site**, until you approve the domain;
- **for the human parts**: CAPTCHA, OTP, passwords and payment details, which you do yourself.

## Demo tasks

| Task | Example request | What it shows |
|---|---|---|
| A, open web | "Find out where Kalpana Chawla was born" | search, open a result, read the answer |
| B, form | "Apply for the disability pension on the demo portal" | fills two tabs from the profile, catches the planted PIN-code error, pauses for the robot check, reads back, waits for "confirm" |
| C, shop | "Buy a white cane from the demo shop" | stops at payment and hands it to the user |
| D, own Chrome | "Open my Gmail and read me my last mail" | the signed-in agent Chrome, read-only |

Tasks A to C run fully offline against the mock sites in `mock_site/`. The presenter script is in [`docs/DEMO.md`](docs/DEMO.md).

## Safety rules (never broken)

1. **Placeholders only.** The LLM never sees real profile values. It writes `{dob}`, and the tool executor substitutes the value.
2. **No irreversible action without confirmation.** Irreversible controls are held as a pending action and run only by the state machine after the user says "confirm". The LLM has no submit tool.
3. **Domain policy in code.** Blocked domains are refused, and each new domain is announced. Profile values are typed only on approved or `trusted` sites.
4. **Sensitive values stay hidden.** Aadhaar, bank account, IFSC and the PIN are never logged, printed, shown unmasked or put in prompts.
5. **Page content is untrusted data**, never instructions. That includes email text.
6. **Humans do the human parts.** CAPTCHA, OTP, logins and payment are never automated.
7. **"Stop" always works**, within one step.

Details: [`docs/PRD.md`](docs/PRD.md) Section 10.

## How it works

```
Voice (Handy) ─▶ Voice Console (browser page) ─WebSocket─▶ FastAPI backend
                                                               │
     command matcher ─▶ agent loop (Ollama LLM, one tool call per step) ◀▶ state machine
                               │ proposed action
                               ▼
     domain policy ─▶ Jev gate ─▶ tool executor ─▶ Playwright browser (agent window + Console window)
                                      │                 ▲
                     irreversible? held for "confirm"   │ perception snapshot, main text, human check
                                      ▼
                     DOM verifier ─▶ read-back ─▶ "confirm" ─▶ commit
```

Each step:
1. **Perception** (`app/perception.py`) gives the LLM a compact snapshot: fields, buttons with irreversible flags, links and tabs, with ids instead of selectors.
2. The **LLM** picks one tool call.
3. The **gate** checks it against the user's goal.
4. The **executor** runs it in the browser.
5. **`app/humancheck.py`** looks for CAPTCHA, OTP, sign-in or payment steps to hand over.

## Quick start

Needs Python 3.11+, [Ollama](https://ollama.com) and Google Chrome (Chrome only for the signed-in mode). Commands are for Windows PowerShell; on macOS or Linux, activate with `source .venv/bin/activate` and copy with `cp`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env            # then edit it; never commit .env
ollama pull qwen3:8b
```

Run the three parts, each in its own terminal:

```powershell
ollama serve                                        # if Ollama is not already running
cd mock_site; python -m http.server 8000            # mock portal, shop, search and inbox
python -m app.main                                  # backend: http://localhost:8080, Console at /console
```

Open http://localhost:8080/console. Its text box keeps focus so that Handy (offline dictation) can paste what you say into it. Until the React Console in `client/` is built (`cd client; npm ci; npm run build`), `/console` serves a placeholder page that uses the same WebSocket.

If port 8080 is taken, set `PORT=8090` (or any free port) in `.env`.

### Try it without voice

```powershell
python scripts/run_task.py --mock --demo-profile "apply for the disability pension on the demo portal"
python scripts/run_task.py "find out where Kalpana Chawla was born"
```

The script uses the real browser and model, and prompts you to type your replies (`yes`, `confirm`, `done`, `stop`).
- `--mock` serves `mock_site/` and uses the mock search, so no real website is touched.
- `--demo-profile` uses a made-up profile in memory.

### Browser modes and Gmail (Task D)

`BROWSER_MODE` in `.env`:

| Mode | What it does |
|---|---|
| `chromium` (default) | Playwright's own Chromium, fresh each time. Used by the tests and the offline demo |
| `chrome` | Starts your installed Chrome with a separate, persistent agent profile (`AGENT_PROFILE_DIR`, default `~/.voiceagent/chrome-profile`, outside the repo) and remote debugging on 127.0.0.1 only, then attaches over CDP. Sign-ins persist between sessions |
| `attach` | Attaches to a Chrome that is already running with remote debugging |

To read Gmail, sign in once by hand in the agent's Chrome. The agent never types passwords. This script opens that Chrome, waits while you sign in, then restarts Chrome to check the sign-in was kept:

```powershell
python scripts/chrome_login_test.py
```

Chrome 136 and later allow remote debugging only on a non-default profile, which is why the agent has its own. Results and real-site findings are in [`docs/REAL_SITE_NOTES.md`](docs/REAL_SITE_NOTES.md).

### Main settings (`.env`)

| Setting | Default | Notes |
|---|---|---|
| `OLLAMA_URL`, `LLM_MODEL`, `NUM_CTX` | `http://localhost:11434/v1`, `qwen3:8b`, `8192` | `llm.py` uses Ollama's native `/api/chat` |
| `SEARCH_URL` | DuckDuckGo HTML | Offline: `http://localhost:8000/web/search.html?q={q}`. DuckDuckGo blocks headless browsers; if it is blocked on your network, use `https://www.bing.com/search?q={q}` |
| `BROWSER_MODE`, `BROWSER_HEADLESS` | `chromium`, `false` | see above |
| `STT_BACKEND`, `TTS_BACKEND`, `PIPER_VOICE` | `handy`, `browser` | speech in and out |
| `GATE_BACKEND`, `GATE_PROCEED`, `GATE_ASK`, `JEV_API_KEY` | `rules`, `0.85`, `0.5` | `jev` is opt-in, see [`docs/JEV_NOTES.md`](docs/JEV_NOTES.md) |
| `MAX_STEPS`, `MAX_FAILURES`, `BLOCKED_DOMAINS` | `30`, `2`, empty | autonomy limits |

The full list is in [`.env.example`](.env.example). Known sites and their aliases ("pension portal", "gmail", "wiki", ...) are in [`app/sites.json`](app/sites.json); only the local mock sites are `trusted`.

## Tests

```powershell
pytest -q                          # unit and integration tests (offline, headless)
pytest -m e2e -q -rs               # end-to-end demo scenarios, see tests/e2e/README.md
python -m tests.e2e.run_demo       # the same scenarios as a pass/fail report
```

Opt-in tests that need the internet or a real Chrome:

| Flag | Runs |
|---|---|
| `RUN_NETWORK_TESTS=1` | perception on real sites (Wikipedia, The Hindu, gov.in, Bing) |
| `RUN_REAL_CHROME=1` | the `chrome` and `attach` modes with a throwaway profile |
| `RUN_REAL_GMAIL=1` | Task D on the real Gmail; needs the signed-in agent profile, and prints no email text |

Useful scripts:
- `scripts/focus_test.py --mode chrome`: checks the Console keeps focus after agent clicks (needed for Handy).
- `scripts/real_site_check.py`: re-checks the real sites.
- `scripts/check_llm.py`: checks Ollama is reachable and the model works.
- `scripts/reliability_test.py`: measures how reliably the model picks the right tool call.

## Repository layout

| Path | What | Owner |
|---|---|---|
| `app/main.py`, `config.py`, `session.py`, `agent.py`, `llm.py`, `tools.py`, `profile.py` | backend, settings, state machine, agent loop, LLM, tool executor, encrypted profile | M1 |
| `client/`, `app/voice.py`, `app/onboarding.py` | Voice Console, speech, onboarding | M2 |
| `app/browser.py`, `perception.py`, `humancheck.py`, `sites.json`, `mock_site/` | browser control and modes, page perception, human-check detection, site directory, mock sites | M3 |
| `app/gate.py`, `verifier.py`, `readback.py`, `audit.py`, `tests/e2e/` | Jev gate, DOM verifier, read-back, audit log, end-to-end tests | M4 |
| `docs/` | PRD, demo script, rehearsal plan, research notes | all |
| `scripts/` | try-out, checks and setup scripts | all |

## Documentation

- [`docs/PRD.md`](docs/PRD.md): product, safety design, interface contract (Section 12), tickets (Section 21). Version 3.2
- [`docs/DEMO.md`](docs/DEMO.md) and [`docs/REHEARSAL.md`](docs/REHEARSAL.md): demo script, checklists, backup plans
- [`docs/REAL_SITE_NOTES.md`](docs/REAL_SITE_NOTES.md): real sites, blocking, the Gmail sign-in proof, fallbacks
- [`docs/JEV_NOTES.md`](docs/JEV_NOTES.md), [`docs/LLM_RELIABILITY.md`](docs/LLM_RELIABILITY.md), [`docs/OLLAMA_CHECK.md`](docs/OLLAMA_CHECK.md), [`docs/REFERENCE_NOTES.md`](docs/REFERENCE_NOTES.md): research and checks
- [`HANDOFF.md`](HANDOFF.md): project state; [`CLAUDE.md`](CLAUDE.md) (same as `AGENTS.md`): rules for coding agents
- Tickets are GitHub issues titled `[TICKET-ID] ...`

## Team

| Role | Person | GitHub |
|---|---|---|
| M1 core backend and integration (lead) | Prashanth | `pruthviprashanth` |
| M2 UI, frontend and voice | Vishal | `VishalAprameya4` |
| M3 browser perception and sites | Sudeepti | `SudeeptiSagar` |
| M4 Jev, verification and demo | Abishek | `abishekraom` |

## Stack

Python 3.11+, FastAPI and Uvicorn, Playwright (Chromium, or Chrome over CDP), Ollama with `qwen3:8b`, Handy for speech recognition (faster-whisper as fallback), Piper or the browser's speech for output, Jev via jevals for the safety gate (rules by default), Fernet encryption for the profile.

Credits: [Handy](https://github.com/cjpais/Handy) (MIT) for offline speech recognition. Wayfinder (`pascalLangdock/elevenlabs_hack`) was used as a design reference only; no code was copied.
