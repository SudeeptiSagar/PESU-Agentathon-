# PRD: Fully Autonomous Voice-Controlled Browser for Blind and Visually Impaired Users

| | |
|---|---|
| Event | Agentathon 2026, 24-hour hackathon |
| Start | Sat 31 Oct 2026, 16:00 IST |
| Assumed end | Sun 1 Nov 2026, 16:00 IST (confirm the real submission and demo time) |
| Version | 3.2 (see "What changed in 3.2"); base 3.1, 3.0 (final for build), 31 Oct 18:15 IST. Pivot from "government scheme applications" to "fully autonomous browser control" |
| Repo | `github.com/SudeeptiSagar/PESU-Agentathon-` |
| Lead | Prashanth (M1) |
| Team | Prashanth (M1), Vishal (M2), Sudeepti (M3), Abishek (M4), see Section 13 |
| Priority keys | P0 = must ship, P1 = should ship, P2 = nice to have |

Read Sections 1 to 5 for the product, 10 for the safety rules, 12 for the code contract, 13 and 14 for your role, and 21 for the tickets (GitHub issues titled `[TICKET-ID] ...`).

### What changed in 3.2

- **Conversation, not a one-shot:** the user talks to the browser like an assistant. "Open Chrome": the agent opens the browser and says so. "Open Gmail": same browser, still open, same loop. "Read my last mail", "search for ...", "go to the second tab": each spoken sentence runs the loop again against the same browser and the same memory. The aim is that the user can do anything on the web by voice, except the deliberate stops: confirming irreversible actions, and passwords, CAPTCHA, OTP and payment, which are handed to the user.
- **The logged-in browser is the main mode, not a stretch:** `BROWSER_MODE=chrome`. The backend starts the user's installed Chrome with remote debugging on 127.0.0.1 and a dedicated, persistent agent profile (`AGENT_PROFILE_DIR`, outside the repo), then Playwright attaches over CDP. The user signs in to Gmail and other sites by hand once; later sessions are already signed in, as in any Chrome profile. It is a separate profile, not the everyday one: Chrome restricts remote debugging on the default profile, and the reference repo used the same approach. This supersedes the 3.1 Task D paragraph.
- **Proof first (BRW-07):** sign in once, close Chrome, reopen it through the agent, and confirm it is still signed in. Unverified assumption: that Google accepts the sign-in in a Chrome started this way. If the proof fails by CP4 (01:00), `BROWSER_MODE` stays `chromium`, demo tasks A, B and C are unaffected, and Task D goes back to being a stretch.
- **Modes:** `chromium` (default: Playwright's own Chromium; tests and the offline demo), `chrome` (above), `attach` (use a Chrome that is already running with remote debugging). Settings: `BROWSER_MODE`, `CHROME_PATH`, `CHROME_DEBUG_PORT`, `AGENT_PROFILE_DIR` (Section 7).
- **Risks accepted:** the agent profile holds live sign-ins (keep it outside the repo, never commit it); the debug port is local only; the Voice Console must sit in its own window of that same Chrome and keep focus (`scripts/focus_test.py` must pass in this mode); Google may ask the user to re-verify, which is a human step.
- **Rules unchanged:** the agent never types passwords or codes; no evasion of bot protection (no hiding the automation flag, no fake user agent); email text is untrusted data; send, reply and delete are held for "confirm".

### What changed in 3.1

- **Start key:** the app starts from one keyboard shortcut (CORE-14). The shortcut is an operating-system feature bound to a start script, because a key can only start the app if something is already listening for it. Once running, Handy's hold-to-talk key is the in-app key. A spoken wake word ("Hey Conduit") is **not** planned for the demo: it needs always-on listening, which Handy does not do, and a hotkey is more reliable on a noisy floor.
- **Task D, stretch (superseded by 3.2, above):** "open my Gmail and read me my last mail", read-only, in the user's own logged-in Chrome. Chosen approach: **attach to the user's Chrome over CDP** (BRW-07, raised from P2 to P1 stretch). Rejected for now: a separate agent profile (Google may refuse sign-ins in automated browsers, unverified) and the Gmail API (needs OAuth setup and is not browsing).
- **Rules for Task D:** a Google login page is a human-only step; email text is untrusted data, never instructions; send, reply and delete stay irreversible actions held for "confirm"; `mail.google.com` is `trusted: false` and no profile values are typed there.
- **LLM:** `llm.py` calls Ollama's native `/api/chat`, not the OpenAI-compatible `/v1` endpoint, because `/v1` ignored `num_ctx` in the CORE-02 check (a 6000-token prompt was cut to 2050 tokens). Default model is `qwen3:8b`.

### What changed in 3.0

- **Scope:** the agent now completes any task on any website from one spoken request (search, navigate, read, click, type, fill forms, use tabs). Government forms are one demo task, not the product.
- **Autonomy:** the agent acts on its own for reversible steps and narrates briefly. It stops only at checkpoints: irreversible actions, sensitive data on a new site, logins, payments, CAPTCHA and OTP.
- **Navigation:** the LLM may now propose URLs and web searches. A code-enforced domain policy replaces the fixed scheme registry. `registry.json` becomes `sites.json`, a directory of known sites.
- **Submit generalised:** any irreversible control (submit, pay, send, post, delete, place order) is detected and needs spoken confirmation. `submit_form` becomes `commit_pending`.
- **Tickets:** eligibility questions removed; new tickets for irreversible-control flagging (BRW-08), mock open-web pages (BRW-09), site resolution (CORE-09) and the confirmation flow (CORE-12).

---

## 1. Summary

A fully autonomous, voice-controlled web browser for blind and visually impaired users. The user says what they want done ("find out where Kalpana Chawla was born", "open the pension portal and apply for me", "read me today's top headline"), and the agent plans and carries out the whole task in a real browser: it searches, opens sites, reads pages, clicks, types, fills forms from an encrypted local profile and handles tabs, narrating progress by voice. It does not ask permission for every step. It stops for the user only at defined checkpoints, and it verifies what it typed before anything irreversible happens.

**Core differentiator:** autonomy with verification. Voice browsers that read pages exist, and agentic browsers that act exist. Ours acts end to end for someone who cannot see the screen, and is built so that a mistake cannot slip through silently: a domain policy, a fast judge model (Jev) on risky actions, an irreversible-action gate, deterministic checks of the real page values, and the user's spoken confirmation.

## 2. Problem

- Screen readers read content, but the user still does every step: finding links, tabbing through forms, recovering from errors. Long tasks take a lot of time and effort.
- General agentic browsers exist, but they are designed for sighted users who can watch and correct them. A blind user cannot see a wrong click or a wrong value.
- Mistakes on the web have real costs: a wrong form entry, an accidental purchase, a message sent by mistake, personal data typed into the wrong site.
- Research on agentic browsers as assistive tools points to limited user control and trust as the main gaps.

## 3. Goals and non-goals

### Goals

| ID | Goal |
|---|---|
| G1 | Complete multi-step tasks autonomously from one spoken request, on real websites and on our mock sites |
| G2 | Demo task A (open web): a search-and-read task on a real site, answered by voice |
| G3 | Demo task B (forms): fill a mock application form from the encrypted profile; verify; read back; confirm; submit |
| G4 | Demo task C (stop point, P1): a mock shop task that stops at payment and hands over |
| G5 | Safety layers: domain policy, Jev gate, irreversible-action gate, DOM verifier, spoken confirmation |
| G6 | Human hand-off for CAPTCHA, OTP, passwords and payment, never bypassed |
| G7 | Local-first stack: Handy (speech recognition), Piper (speech output), Ollama (LLM) |
| G8 | A planted mistake caught live in the demo |
| G9 | Logged-in browsing: sign in to Gmail once in the agent's Chrome profile, later sessions open already signed in; read the newest email (Task D), read-only |

### Non-goals for this hackathon

- Mobile or hosted version (roadmap item in the pitch)
- Multilingual voice (roadmap)
- Completing payments, or typing passwords or card numbers (the user always does these)
- Bypassing CAPTCHA, OTP or any bot protection (never)
- Submitting real applications or orders on live sites during the demo
- User accounts or a cloud backend

## 4. User and scenarios

**Primary user:** a blind or low-vision adult who wants to get things done on the web without sighted help.

**Scenario A (open web):** Ramesh says "Find out where Kalpana Chawla was born." The agent says "Searching the web", opens a search, picks a reliable result, reads the relevant part and answers: "She was born in Karnal, Haryana. Want me to read more?"

**Scenario B (form):** Ramesh says "Apply for the disability pension on the demo portal." The agent opens the portal, fills both tabs from his profile, notices that the PIN code on the page is wrong, fixes it or asks him, pauses for the "I'm not a robot" check, reads the form back and submits only after he says "confirm".

**Scenario D (stretch, own Chrome):** Ramesh presses the start key and says "Open my Gmail and read me my last mail." The agent attaches to his already logged-in Chrome, opens the inbox, opens the newest message and reads it aloud. It never types his Google password and never sends, replies or deletes without "confirm".

**Scenario C (stop point):** "Order a pack of AA batteries from the demo shop." The agent searches the shop, adds the item, reads the total and stops: "The next step is payment. I'll hand over to you."

## 5. User flow

1. Start the app with one keyboard shortcut (an OS shortcut bound to the start script, CORE-14). The agent says it is ready.
2. First time: onboarding builds the encrypted profile (questions spoken, sensitive values typed). Later sessions: unlock with the PIN.
3. The user states a task in their own words. Handy transcribes it.
4. The agent resolves where to go: a known site from `sites.json`, a URL, or a web search. It announces the site ("Opening wikipedia.org").
5. The agent works autonomously: navigate, read, click, type, fill, switch tabs. It narrates in short phrases ("Opened the article. Reading the early life section.").
6. Checkpoints that stop and ask: an irreversible control (submit, pay, send, post, delete, place order); the first sensitive profile value on a site the user hasn't approved; login, password, CAPTCHA, OTP or payment pages (handed to the user); the agent is unsure or failed twice.
7. Before an irreversible form action: the DOM verifier checks every field, problems are reported, and the agent reads the form back from the real page values with sensitive numbers masked.
8. The user says "confirm" (the action runs) or "change <field>" / "no" (it doesn't).
9. The agent reports the result (an answer, an acknowledgment number, where it stopped).
10. Always available, mid-task: "stop", "pause", "continue", "repeat", "go back", "where am I", "what can I say".

## 6. Functional requirements

| ID | Requirement | Priority | Owner |
|---|---|---|---|
| FR-1 | Spoken input through Handy reaches the backend as text | P0 | M2 |
| FR-2 | All output is spoken with Piper and can be interrupted by new input | P0 | M2 |
| FR-3 | Command matcher (stop, pause, continue, repeat, yes, no, confirm, back, done, where am I, help) in plain code, not the LLM; "stop" halts the agent mid-task | P0 | M2 |
| FR-4 | Site resolution: known-site aliases from `sites.json`, explicit URLs, or a web search; the destination domain is announced | P0 | M1 (logic), M3 (directory) |
| FR-5 | Domain policy enforced in code: blocklist; announce new domains; sensitive profile values only on user-approved domains | P0 | M1 |
| FR-6 | Page perception: compact fields, links, tabs, buttons, errors, summary and readable main text | P0 | M3 |
| FR-7 | Autonomous agent loop with a step cap, brief narration, retry or alternative on failure, ask the user after 2 failures | P0 | M1 |
| FR-8 | Tool executor with placeholder substitution and expected-value recording | P0 | M1 |
| FR-9 | Irreversible controls flagged in perception, held by the executor and committed only by the state machine after confirmation | P0 | M3 (flag), M1 (hold and commit) |
| FR-10 | DOM verifier comparing expected and actual values with type-aware normalisation | P0 | M4 |
| FR-11 | Read-back built from actual page values, with masking | P0 | M4 |
| FR-12 | Jev gate returning proceed, ask_user or block (deterministic rules first) | P0 | M4 |
| FR-13 | Human hand-off for CAPTCHA, OTP, password and payment pages | P0 | M3 (detect), M1 (pause and resume) |
| FR-14 | Encrypted local profile with a PIN-derived key | P0 | M1 |
| FR-15 | Onboarding and PIN unlock in the Voice Console | P0 | M2 |
| FR-16 | Accessible Voice Console: keyboard-only, focus management, large text, high contrast, ARIA live regions, live step log | P0 | M2 |
| FR-17 | Multi-tab: follow and announce new tabs; switch and close tabs by voice | P1 | M3 |
| FR-18 | Mock open-web pages (search results, article, shop with checkout) for an offline-safe demo | P1 | M3 |
| FR-19 | Audit log (JSONL, no sensitive values) | P1 | M4 |
| FR-20 | Real Chrome with a persistent agent profile (`BROWSER_MODE=chrome`) or attach to a running Chrome (`attach`), over CDP | P0, proof by CP4 | M3 |
| FR-21 | Start script and keyboard shortcut that bring the whole system up | P1 | M1 |

## 7. Architecture

```
 User ──voice──▶ Handy (separate desktop app, local Whisper or Parakeet + Silero VAD)
                    │  pastes the transcript into the focused text field
                    ▼
        Voice Console (browser page, always-focused text box)  ◀── speak / state / steps / alerts
                    │  WebSocket: {"type":"utterance","text":...}
                    ▼
 ┌──────────────────────── Backend (Python, FastAPI) ─────────────────────────────┐
 │ Command matcher ─▶ Autonomous agent loop (Ollama LLM, step-capped) ◀▶ State machine │
 │                         │ proposed action                                          │
 │                         ▼                                                          │
 │      Domain policy ─▶ Jev gate (proceed / ask / block)                             │
 │                         ▼                                                          │
 │  Profile (encrypted) ─▶ Tool executor ─▶ Playwright (agent browser window, tabs)    │
 │                         │   └─ irreversible? ─▶ pending action ─▶ confirm ─▶ commit │
 │                  expected values             Page perception (+ irreversible flags) │
 │                         ▼                           ▼                              │
 │                     DOM verifier ◀──────────────────┤                              │
 │                         ▼                           ▼                              │
 │                     Read-back             Human check (CAPTCHA/OTP/login/payment)  │
 │  Piper TTS ◀── speak ───┘          Audit log · Site directory (sites.json)         │
 └────────────────────────────────────────────────────────────────────────────────────┘
```

### One task, end to end

1. Handy pastes text into the Console; the Console sends `utterance`.
2. `main.py` passes it to the command matcher. Commands (stop, confirm, repeat...) are handled directly. Anything else starts or continues a task.
3. The agent resolves the destination (directory, URL or search), the domain policy checks it, and the agent announces it.
4. Each step: perception snapshot, then one LLM tool call, validated, then the gate for risky actions, then the executor through Playwright, then a human-check scan.
5. Reversible actions run immediately with short narration. An irreversible control is not clicked: the executor stores it as `pending_action`.
6. For a pending form action, the verifier checks the fields, read-back is spoken, the user confirms, and the state machine calls `commit_pending`.
7. The agent ends with `finish(summary)`, which is spoken. "stop" at any time halts the loop.

### Folder layout

```
pesu-agentathon/
  app/
    main.py config.py session.py agent.py llm.py tools.py profile.py      # M1
    voice.py onboarding.py                                                 # M2
    browser.py perception.py humancheck.py sites.json                      # M3
    gate.py verifier.py readback.py audit.py                               # M4
  client/            console.html console.css console.js                   # M2
  mock_site/         portal/ (index, apply, help, ack)  web/ (search, article, shop, cart, checkout)   # M3
  tests/             test_<module>.py (each owner), e2e/ (M4)
  docs/              PRD.md TEAM_PROMPTS.md REFERENCE_NOTES.md JEV_NOTES.md REAL_SITE_NOTES.md DEMO.md
  scripts/           tickets.json create_issues.py focus_test.py
  CLAUDE.md AGENTS.md HANDOFF.md README.md SETUP.md requirements.txt .env.example .gitignore
```

### Ports and environment

| Item | Value |
|---|---|
| Backend (FastAPI) | `http://localhost:8080`, Console at `/console`, WebSocket at `/ws/console`, health at `/health` |
| Mock sites | `http://localhost:8000` (`python -m http.server 8000` inside `mock_site/`): `/portal/` and `/web/` |
| Ollama | `OLLAMA_URL` (default `http://localhost:11434/v1`), `LLM_MODEL` (default `qwen3:8b`), `NUM_CTX=8192` |
| Search | `SEARCH_URL` (default `https://html.duckduckgo.com/html/?q={q}`); `SEARCH_URL=http://localhost:8000/web/search.html?q={q}` for the offline demo |
| Autonomy | `MAX_STEPS=30`, `MAX_FAILURES=2`, `BLOCKED_DOMAINS` (comma list) |
| Browser | `BROWSER_MODE=chromium` (default) or `chrome` or `attach`; `CHROME_PATH` (empty = auto-detect), `CHROME_DEBUG_PORT=9222`, `AGENT_PROFILE_DIR=~/.voiceagent/chrome-profile` (outside the repo) |
| Voice | `STT_BACKEND=handy` or `whisper`; `TTS_BACKEND=piper` or `browser`; `PIPER_VOICE=<path to .onnx>` |
| Jev | `GATE_BACKEND=jev` or `llm` or `rules`, plus any key Jev needs (from M4's notes) |

## 8. Voice layer: Handy integration

### 8.1 What Handy is

Handy is a free, offline, cross-platform dictation app built with Tauri. The user holds or taps a configurable shortcut, speaks, and the transcript is pasted into whichever text field has focus. It uses Whisper or Parakeet models with Silero voice-activity detection, and has command-line flags such as `--toggle-transcription` and `--cancel` for a running instance. On macOS it needs microphone and accessibility permissions. It is MIT-licensed, but its name and logo are not, so we credit it and do not rebrand it.

**What Handy does not do:** it has no speech output and no API that hands transcripts to another program. Its only output is pasting into the focused field. The Voice Console exists to catch that paste.

### 8.2 The Voice Console

1. The backend serves `/console`, a page with one large text box that always has focus.
2. The user holds the Handy shortcut and speaks; Handy pastes the transcript into the box.
3. The Console waits about 900 ms after the last change (or Enter), sends `{"type":"utterance","text":...}` and clears the box.
4. Any new utterance interrupts Piper if it is speaking.
5. The Console shows status, a live step log of what the agent is doing, the transcript, a masked field table and alerts, for judges and sighted helpers. It must be accessible itself (FR-16).
6. Sensitive values (Aadhaar, bank details) are typed into the same box, which avoids speech errors on digits.

### 8.3 Keeping focus (main integration risk)

Handy pastes into whichever window has OS focus. When the agent works in its browser window, focus can move away from the Console.

- The Console and the agent's browser run in **two separate Playwright windows**.
- After every agent action and every finished Piper utterance, the backend calls `browser.refocus_console()`.
- Test on macOS and Windows whether this really moves OS focus. If not, add an OS-level refocus helper (AppleScript on macOS, an equivalent on Windows).

### 8.4 Known Handy issues to set up for

- Handy's troubleshooting notes say the old clipboard can sometimes be pasted instead of the transcript. Use its Paste Delay or experimental Reliable Paste settings (debug menu) and test on every machine.
- Bluetooth microphones can degrade audio on macOS. Use a wired headset or the built-in microphone, with headphones for output so the microphone doesn't hear Piper.
- Download models on every machine now, not on demo day.

### 8.5 Decision gate at 20:30 IST and fallback

M2 runs 10 utterances (including digits, a name and each command) through Handy into the Console, and M3's `scripts/focus_test.py` confirms focus holds across 5 simulated agent actions. **Pass:** at least 9 of 10 arrive intact and focus holds.

**If it fails,** switch the speech-recognition adapter to faster-whisper with silero-vad inside the backend (microphone through sounddevice), behind the same `STT` interface. Nothing else changes.

### 8.6 Speech output

Piper, played through sounddevice. Digits spoken separated ("9 8 7 6"). `interrupt()` stops playback immediately. Narration is short: one phrase per step, full sentences only for answers, read-back and questions. If Piper isn't working within 90 minutes, use `TTS_BACKEND=browser`: the backend sends `speak` events and the Console uses the browser's `speechSynthesis`.

## 9. Backend reference

**Reference repo:** `github.com/pascalLangdock/elevenlabs_hack`, which appears to be the backend of Wayfinder, a voice web-accessibility hackathon project. Its visible files are `requirements.txt` (browser-use, playwright, fastapi, uvicorn, langchain-openai, python-dotenv), `.env.example` (OpenAI and ElevenLabs keys) and a `backend/` folder. **`backend/` was reviewed in CORE-05 (see `docs/REFERENCE_NOTES.md`). The repo has no license, so it is a design reference only. Do not copy its code.**

From the Wayfinder write-up: a FastAPI service is called by a cloud voice agent and starts a browser-use agent over Playwright, attached to the user's Chrome via CDP, capped at 5 steps, with a fresh agent per command and a spoken summary returned. That is the closest prior work to our new scope.

| Reference | Ours |
|---|---|
| ElevenLabs cloud voice | Handy (input) and Piper (output), both local |
| OpenAI / ChatBrowserUse model | Ollama local model behind `llm()` |
| browser-use drives the browser | Our own Playwright tool layer, so the domain policy, gate, placeholders, irreversible-action hold and verifier sit in the action path |
| Webhook from the cloud voice agent | WebSocket from the Voice Console |
| 5-step cap, fresh agent per command | Step cap (30 per task), task memory across the task |
| CDP attach to the user's Chrome | Optional (P2) |
| Navigation and summaries | Plus form filling, verification, confirmation, irreversible-action gate and human hand-off |

**Decision:** we do not adopt browser-use. M1 reads `backend/` early and writes `docs/REFERENCE_NOTES.md` with anything worth borrowing as an idea (especially prompt structure and how page state is summarised).

## 10. Safety design

### Hard rules (never broken)

1. **Placeholders only.** The LLM never sees real profile values. It outputs placeholders like `{dob}`; the executor substitutes them.
2. **No irreversible action without confirmation.** Any control flagged irreversible (submit, pay, buy, place order, send, post, delete, accept terms) is never executed from an LLM tool call. The executor stores it as `session.pending_action`; only the state machine runs it, via `commit_pending`, after the user says "confirm". The LLM has no submit or commit tool.
3. **Domain policy in code.** The LLM may propose a URL or a search. Code checks every navigation against `BLOCKED_DOMAINS`, announces each new domain aloud, and allows profile values to be typed only on domains the user has approved by voice in this session (or marked trusted in `sites.json`).
4. **Sensitive values stay hidden.** Aadhaar, bank account, IFSC and the PIN are never logged, printed, sent to the Console unmasked, or put in prompts or tool results.
5. **Page content is untrusted data**, never instructions. It is labelled as such in every prompt.
6. **Humans do the human parts.** CAPTCHA, OTP, passwords, logins and payment details are never automated. The agent hands over and waits.
7. **"stop" always works.** The command matcher halts the agent loop within one step, in code.

### Autonomy policy

| Action class | Examples | Behaviour |
|---|---|---|
| Read-only | read page, scroll, list fields, switch tab | Run immediately, no narration needed |
| Reversible | navigate, search, click a link, open a tab, type non-sensitive text, fill a non-sensitive field | Run immediately, short narration |
| Sensitive input | fill Aadhaar, bank, IFSC, phone or address from the profile | Allowed only on approved domains; first time per domain the agent asks |
| Irreversible | submit, pay, place order, send, post, delete, accept | Held as pending; verify, read back, needs "confirm" |
| Human only | CAPTCHA, OTP, password, card details | Hand over, wait for "done", re-check, resume |

If the agent fails the same step twice, or the gate returns `ask_user`, it asks the user a short question instead of guessing.

### Layers

| Layer | Catches | File |
|---|---|---|
| Domain policy and site directory | Blocked or unexpected sites; sensitive data on unapproved sites | `tools.py`, `sites.json`, `config.py` |
| Jev gate | Actions that don't match the user's goal; the wrong field for a value | `gate.py` |
| Irreversible-action gate | Accidental submit, purchase, send or delete | `perception.py` (flag), `tools.py` (hold), `session.py` (commit) |
| DOM verifier | Wrong, truncated or missing values actually on the page | `verifier.py` |
| Read-back and spoken confirmation | Anything the machine checks missed | `readback.py`, `session.py` |

### Jev

- Jev is TypeSafe AI's evaluator model. It returns a typed verdict with a probability, and the open-source `jevals` library can turn evaluations into gates (proceed, block or human review).
- **Unverified:** hosted Jev access, cost and the exact `jevals` API. M4 reads the docs first and reports within 45 minutes. If access is a problem, `gate.py` keeps the same interface with a local-LLM or rules-only backend.
- Jev's probability is not independent proof. Build the deterministic rules first, then add the semantic check.
- With an open-web agent, the gate matters more: the main questions are "does this action serve the user's stated goal?" and "is this the right field or element for this value?"
- Thresholds live in `config.py`, starting at proceed ≥ 0.85, ask 0.5 to 0.85, block < 0.5, tuned on test cases.

### Human check

`humancheck.py` (M3) detects CAPTCHA frames and inputs, OTP fields, password fields and payment pages after every navigation and click. The agent (M1) saves its state, enters `NEEDS_HUMAN_CHECK`, says what is needed, waits for "done", asks M3's detector whether the challenge is gone, and resumes. The LLM never sees or acts on the challenge.

### Privacy

- Profile at `~/.voiceagent/profile.json`, encrypted with Fernet using a key derived from the PIN (PBKDF2, random salt). Never committed.
- Sensitive values masked to the last four digits in the Console, the read-back and logs.
- Speech recognition, speech output and the LLM run locally. Web pages visited are, of course, on the internet.

## 11. Data

### Profile fields

`full_name, dob, gender, address, city, state, pin_code, phone, email, annual_income, category, disability_percent` stored as plain values; `aadhaar, bank_account, ifsc` encrypted.

### Site directory (`sites.json`, M3)

```json
[
  {"id": "demo_portal", "aliases": ["pension portal", "demo portal", "government portal"],
   "url": "http://localhost:8000/portal/index.html", "domain": "localhost", "trusted": true,
   "notes": "Mock disability pension application with a planted PIN-code trap"},
  {"id": "demo_shop", "aliases": ["demo shop", "shop"],
   "url": "http://localhost:8000/web/shop.html", "domain": "localhost", "trusted": true},
  {"id": "wikipedia", "aliases": ["wikipedia", "wiki"],
   "url": "https://en.wikipedia.org", "domain": "en.wikipedia.org", "trusted": false}
]
```

`trusted: true` means profile values may be typed without asking first. Everything else needs the user's approval per domain.

### Expected-value record (written by the executor)

```json
{"f3": {"label": "Date of birth", "selector": "#dob", "value": "1980-03-04", "type": "date", "source": "profile:dob"}}
```

### Pending action (held by the executor)

```json
{"element_id": "b4", "label": "Submit application", "kind": "submit", "url": "http://localhost:8000/portal/apply.html", "domain": "localhost"}
```

## 12. Interface contract

This is the shared contract. M1 commits it as stub code in CORE-01 so everyone can code against it immediately. **Changes go through M1 only**, who updates this section and announces it.

```python
# config.py (M1)
OLLAMA_URL, LLM_MODEL, NUM_CTX, MAX_STEPS = 30, MAX_FAILURES = 2, SEARCH_URL, BLOCKED_DOMAINS,
GATE_BACKEND, GATE_THRESHOLDS, STT_BACKEND, TTS_BACKEND, PIPER_VOICE, SENSITIVE_KEYS

# llm.py (M1)
async def llm(messages: list[dict], tools: list[dict] | None = None) -> dict
# returns {"text": str | None, "tool_call": {"name": str, "args": dict} | None}

# session.py (M1)
@dataclass
class Session:
    state: str; goal: str | None; plan: list[str]; progress: list[str]
    profile: dict; approved_domains: set[str]; locators: dict; expected: dict
    elements: dict   # id -> {kind,label,irreversible,...} of the last snapshot (tools.record_snapshot)
    pending_action: dict | None; confirmed: bool; failures: int
    history: list; saved_state: str | None
# states: IDLE, PLANNING, ACTING, VERIFYING, READBACK, AWAITING_CONFIRM, COMMITTING,
#         DONE, PAUSED, NEEDS_USER, NEEDS_HUMAN_CHECK
def transition(session: Session, new_state: str) -> None    # raises IllegalTransition on an illegal transition
# also: TRANSITIONS (allowed-moves table), can_transition(session, new_state) -> bool,
#       confirm(session)  # backend command matcher only: AWAITING_CONFIRM -> COMMITTING
#       resume(session) -> str  # leave PAUSED / NEEDS_HUMAN_CHECK, back to saved_state
# Nobody else assigns session.state or sets confirmed=True (a test scans app/ for it). "stop" (IDLE) works from any state.

# profile.py (M1)
def profile_exists() -> bool
def save_profile(data: dict, pin: str) -> None
def load_profile(pin: str) -> dict                           # raises WrongPinError

# tools.py (M1)
TOOL_SCHEMAS: list[dict]
#  navigate(target)             target = sites.json alias or URL; domain policy applies
#  web_search(query)            opens SEARCH_URL with the query
#  go_back()  scroll(direction)  read_page(mode)  mode = "summary" | "main_text" | "fields"
#  click(element_id)            irreversible elements are held, not clicked
#  type_text(field_id, text)    non-sensitive text from the user or the task
#  fill_field(field_id, value_ref)   value_ref = "{profile_key}" placeholder
#  select_option(field_id, option)  press_key(key)
#  switch_tab(index)  close_tab(index)
#  ask_user(question)  speak(text)  finish(summary)
#  -- NO submit or commit tool
class ToolExecutor:
    def __init__(self, announce=None)   # announce(domain) is called once per new domain
    async def run(self, action: dict, session: Session, browser) -> str   # short result, no raw sensitive values
#  The first word of a result is its status: ok | error | blocked | needs_approval | needs_human | held |
#  ask_user | speak | finish   (tools.parse_result). held = an irreversible control was stored as
#  session.pending_action and NOT pressed. needs_approval = ask the user, then tools.approve_domain(), retry.
#  The agent loop must call tools.take_snapshot (snapshot + record_snapshot) every step: the executor
#  refuses ids that are not in the last snapshot, and clears them after any click or navigation.
#  press_key accepts only Enter, Tab, Shift+Tab, Escape, arrows, PageUp/Down, Home, End, Space; Enter and
#  Space are refused when they would submit a form or press an irreversible control.
def resolve_target(target: str) -> dict                     # {"url","domain","site_id"|None,"trusted","kind"}
#  kind: site (sites.json id/alias, filler words like "open the ... please" ignored) | url | domain
#  | search (url is None: not a destination, the agent should use web_search). Non-web schemes,
#  URLs with a username and bad ports are never resolved.
def domain_allowed(domain: str) -> bool
async def commit_pending(session: Session, browser) -> str  # state machine only: needs state COMMITTING, confirmed, pending_action; presses the stored selector once

# agent.py (M1)
async def handle_utterance(text: str, ctx) -> None          # entry point from main.py
async def run_task(ctx) -> None                             # loop, max MAX_STEPS
async def stop(ctx) -> None                                 # halts within one step

# voice.py (M2)
class STT:  async def listen(self) -> str
class HandyConsoleSTT(STT): ...                              # fed by /ws/console utterances
class WhisperSTT(STT): ...                                   # fallback
class TTS:  async def speak(self, text: str) -> None; def interrupt(self) -> None
class PiperTTS(TTS): ...;  class BrowserTTS(TTS): ...        # BrowserTTS sends `speak` events
def match_command(text: str) -> str | None
#  stop|pause|continue|repeat|yes|no|confirm|back|done|where|help|None
def spoken_digits(s: str) -> str                             # "9876" -> "9 8 7 6"
def words_to_digits(s: str) -> str                           # "nine eight seven" -> "987"

# onboarding.py (M2)
async def run_onboarding(ctx) -> None                        # asks questions, confirms, calls save_profile
async def run_unlock(ctx) -> None                            # asks PIN, calls load_profile

# browser.py (M3)
class BrowserController:
    async def start(self) -> None                            # agent window + console window; honours config.BROWSER_MODE (chromium | chrome | attach)
    async def goto(self, url: str) -> None
    active                                                   # current agent page (tab)
    console_page                                             # Voice Console page
    async def list_tabs(self) -> list[dict]
    async def switch_tab(self, index: int) -> None
    async def close_tab(self, index: int) -> None
    async def go_back(self) -> None
    async def refocus_console(self) -> None
    async def close(self) -> None
# emits an on_new_tab(title, url) callback when a new tab opens

# perception.py (M3)
async def snapshot(page, session: Session) -> dict
# {"page_title","url","domain","summary","headings":[],
#  "fields":[{"id","label","type","required","value","error","sensitive_hint"}],
#  "links":[{"id","text"}],"tabs":[{"id","text","selected"}],
#  "buttons":[{"id","text","irreversible","kind"}],   # kind: submit|pay|send|post|delete|accept|other
#  "errors":[]}
# fills session.locators[id]; caps: 60 elements, labels under 60 characters
async def main_text(page, max_chars: int = 4000) -> str     # readable article text for read_page

# humancheck.py (M3)
async def challenge_present(page) -> dict | None
# {"kind": "captcha"|"otp"|"password"|"payment", "hint": str}

# gate.py (M4)
async def check(action: dict, context: dict) -> dict
# context: {"goal","domain","approved_domains","element": snapshot entry, "history_tail"}
# returns {"decision": "proceed"|"ask_user"|"block", "reason": str, "p": float}

# verifier.py (M4)
async def verify(page, session: Session) -> list[dict]       # [{"field_id","label","expected","actual","kind": "mismatch"|"missing"|"error"}]

# readback.py (M4)
def build_readback(session: Session, actual_values: dict) -> list[str]
def describe_pending(session: Session) -> str                # "I'm about to press Place order on demo shop. Total 249 rupees."

# audit.py (M4)
def log_event(kind: str, **fields) -> None                   # drops sensitive keys automatically
```

### WebSocket events (`/ws/console`)

| Direction | Event | Payload |
|---|---|---|
| Console → backend | `utterance` | `{text}` |
| Console → backend | `key` | `{name}` (Escape = stop, Space = pause/continue when the box is empty) |
| Backend → Console | `speak` | `{text}` (shown always; voiced only when `TTS_BACKEND=browser`) |
| Backend → Console | `state` | `{name}` |
| Backend → Console | `step` | `{n, action, target, result}` for the live step log |
| Backend → Console | `field_table` | `{fields: [{label, value_masked, status}]}` |
| Backend → Console | `pending` | `{description}` when an irreversible action waits for "confirm" |
| Backend → Console | `alert` | `{level, message}` |
| Backend → Console | `input_mode` | `{mode: "voice"|"typed_secret"}` (the Console hides typed secrets) |

Only the backend's command matcher turns an utterance into a confirmation. The Console never sets `confirmed` itself.

## 13. Team roles

| Member | Name | Role | Owns |
|---|---|---|---|
| M1 | Prashanth (`pruthviprashanth`), lead | **Core backend and integration** | `main.py`, `config.py`, `session.py`, `agent.py`, `llm.py`, `tools.py`, `profile.py`, `requirements.txt`, `.env.example`, `CLAUDE.md`, `AGENTS.md`, `HANDOFF.md`; reference repo study; merges to main |
| M2 | Vishal (`VishalAprameya4`) | **UI, frontend and voice experience** | `client/` (Voice Console), Handy setup, `voice.py`, `onboarding.py`, `SETUP.md`, accessibility of the Console |
| M3 | Sudeepti (`SudeeptiSagar`) | **Browser perception and sites** | `browser.py`, `perception.py`, `humancheck.py`, `sites.json`, `mock_site/`, `scripts/focus_test.py`, real-site testing |
| M4 | Abishek (`abishekraom`) | **Jev, verification and demo** | `gate.py`, `verifier.py`, `readback.py`, `audit.py`, `tests/e2e/`, `docs/DEMO.md`, deck, backup video |

### Working rules

- Edit only the files you own. Need a change elsewhere? Ask the owner, or open an issue for them.
- Each owner writes unit tests for their own module in `tests/test_<module>.py`. M4 owns end-to-end tests.
- Contract changes (Section 12) go through M1.
- Status at every checkpoint (Section 15) to M1.

### Dependencies between roles

- **Everyone depends on CORE-01** (M1's skeleton with stubs and a running `main.py`). Until it lands, everyone works on tasks with no code dependency: Handy setup, mock sites, Jev research, Console HTML.
- M1's agent loop needs M3's `snapshot`, `main_text` and `BrowserController` (stubs first, real versions by CP3).
- M1's irreversible-action hold needs M3's `irreversible` flags (BRW-08).
- M4's verifier needs M3's locators and M1's `session.expected`.
- M2's Console needs M1's WebSocket endpoint (stub in CORE-01).

## 14. Role responsibilities

### M1, Prashanth: core backend and integration

The backbone everyone builds on. In order:
1. Ship the skeleton (CORE-01) fast, so the others are unblocked.
2. LLM wrapper and reliability test; state machine; executor with domain policy and irreversible hold.
3. Autonomous agent loop with narration, recovery and stop; confirmation flow.
4. Wire every module into `main.py`, merge branches, keep main runnable, cut scope when needed.

### M2, Vishal: UI, frontend and voice experience

Everything the user hears, says and sees:
1. Handy on every demo machine, with the Console catching its pastes.
2. The accessible Voice Console with a live step log.
3. Piper output, command matcher (including stop and pause), number handling.
4. Onboarding and PIN unlock.
5. Run the 20:30 Handy decision gate and own the fallback if it fails.

### M3, Sudeepti: browser perception and sites

Everything the agent sees and touches on the web:
1. Mock portal (with the planted trap and fake human check) and mock open-web pages.
2. Two-window Playwright controller with tabs, back and console refocus.
3. Page perception with label fallbacks, readable main text and summaries.
4. Irreversible-control flagging and human-check detection.
5. Site directory and tests on real sites.

### M4, Abishek: Jev, verification and demo

Everything that proves the agent is safe, and the story we tell:
1. Jev research and the gate.
2. DOM verifier, read-back, pending-action description, audit log.
3. End-to-end tests for all three demo tasks.
4. Demo script, deck, rehearsals and backup video.

## 15. Timeline and checkpoints (IST)

| Time | Hour | Milestone |
|---|---|---|
| 18:30 | H+2.5 | PRD v3.0 shared; issues assigned; everyone pulls the repo |
| 19:30 | H+3.5 | **CP1, foundation:** CORE-01 skeleton on main; every machine runs `main.py`, reaches Ollama and serves the mock sites; Handy installed; Jev access known |
| 20:30 | H+4.5 | **CP2, decision gate:** Handy pass or fail; LLM reliability score; gate backend chosen |
| 23:00 | H+7 | **CP3, modules:** every P0 module passes its acceptance check and is merged |
| 01:00 | H+9 | **CP4, first end to end:** typed requests complete demo tasks A and B |
| 04:00 | H+12 | **CP5, full loop:** voice end to end; gate, irreversible hold and human check wired in; planted trap caught |
| 04:00 to 07:00 | | Sleep shift A: M2 and M4 (M1 and M3 keep working) |
| 07:00 to 10:00 | | Sleep shift B: M1 and M3 (M2 and M4 keep working) |
| 11:00 | H+19 | **Feature freeze.** Bug fixes and rehearsal only |
| 11:00 to 14:00 | | Hardening; five clean voice runs; deck; backup video |
| 14:00 to 16:00 | H+22 to 24 | Final rehearsal on the demo machine; buffer; submission (adjust to the real deadline) |

If a checkpoint slips by more than 90 minutes, cut P2 items first, then P1.

## 16. Git workflow and tickets

- Repo: `SudeeptiSagar/PESU-Agentathon-` (owned by Sudeepti); all four are collaborators. M1 manages merges to main.
- Branches: `core/*` (M1), `ui/*` (M2), `browser/*` (M3), `jev/*` (M4). One branch per ticket, for example `browser/BRW-03-perception`.
- Pull requests into main, reviewed by M1 (M1's own PRs reviewed by anyone). Squash-merge. Reference the issue: `Closes #12`.
- Before pushing: `git pull --rebase origin main`. After any merge, everyone rebases.
- Commit small and often. Never commit `.env`, profile files, logs or model files.
- Tag the working demo before the last hours: `git tag demo-v1 && git push origin demo-v1`.

### Labels

`role:core`, `role:ui`, `role:browser`, `role:jev-demo`, `P0`, `P1`, `P2`, `blocked`, `bug`, `decision`.

### Milestones

`CP1 Foundation`, `CP2 Decision gate`, `CP3 Modules`, `CP4 First end to end`, `CP5 Full loop`, `Freeze and demo`.

### Ticket format

Each issue has: title prefixed with the ticket ID (for example `[CORE-01]`), assignee, labels, milestone, depends on and acceptance criteria as a checklist. The full backlog is in Section 21. Issues are created by `scripts/create_issues.py` from `scripts/tickets.json`, which mirrors Section 21.

## 17. Demo plan (3 minutes)

1. **Hook (20 s):** a screen reader reads; it doesn't do. Mistakes on the web cost real things.
2. **Task A, open web (40 s):** "Find out where Kalpana Chawla was born." The agent announces the search, opens a result, reads, and answers. The Console's step log shows each action.
3. **Task B, form (70 s):** "Apply for the disability pension on the demo portal." The agent fills both tabs from the profile; the verifier catches the truncated PIN code and the agent says so; it pauses for the "I'm not a robot" check and resumes after "done"; read-back; "confirm"; acknowledgment number spoken.
4. **Task C, stop point (20 s, if ready):** "Order AA batteries from the demo shop." The agent adds to cart, reads the total, holds "Place order" and hands over at payment.
5. **Close (30 s):** autonomy with verification; local and private stack; "stop" works at any moment; roadmap (hosted phone version, multilingual, user's own Chrome).

**Backups:** recorded video of a clean run; `SEARCH_URL` pointed at the mock search page if the venue network or search engine blocks us; browser-speech fallback; typed input in the Console if the microphone fails.

## 18. Risks and mitigations

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Handy has no transcript API and pastes into the focused window | Input lost or misplaced | Voice Console; refocus after each action; 20:30 gate; faster-whisper fallback behind `STT` | M2, M3 |
| Handy pastes old clipboard content | Wrong text reaches the agent | Paste Delay or Reliable Paste; read back numbers; type sensitive values | M2 |
| Skeleton is late | Everyone blocked | CORE-01 first; others start on dependency-free tasks | M1 |
| Small local LLM is weak at open-ended autonomy | Wrong clicks, loops | Few clear tools, trimmed snapshots, temperature 0, failure counter, step cap, ask after 2 failures, reliability test at CP2, API fallback behind `llm()` | M1 |
| Real sites change, block bots or are slow | Task A fails live | Mock open-web pages; `SEARCH_URL` switch; rehearse on the venue network | M3 |
| Irreversible controls missed by keyword flags | Accidental submit | Flags from button text, form submit type and URL hints; gate double-checks; tests on every mock page | M3, M4 |
| Prompt injection from web pages | Agent follows page text | Page text labelled untrusted; gate checks the action serves the user's goal; domain policy | M1, M4 |
| Logged-in Chrome (Task D): Google blocks the sign-in or asks to re-verify; the profile holds live sign-ins; the debug port gives full browser control; Console focus inside Chrome; Gmail page too heavy for perception | Logged-in browsing fails or leaks | Prove login persistence first (BRW-07); fall back to `chromium`; profile outside the repo; debug port bound to 127.0.0.1; the human does all verification; focus test in chrome mode; mock inbox for offline tests | M3, M1 |
| Ollama's small default context | Model ignores rules | `num_ctx` 8192; capped snapshots; trimmed history; log `prompt_eval_count` | M1 |
| Jev access or API unknown | No semantic gate | Report in 45 minutes; rules first; LLM backend fallback | M4 |
| Reference repo unread, no visible license | Wrong assumptions, licensing | Study only, no copying; own tool layer | M1 |
| Piper or audio setup fails | No speech output | 90-minute time box; browser `speechSynthesis` fallback | M2 |
| Microphone hears the speaker | False input | Wired headset; ignore input while speaking if needed | M2 |
| Fatigue | Late bugs | Sleep shifts; freeze at 11:00 | M1 |
| Merge conflicts | Lost time | File ownership; small PRs | All |

## 19. Positioning for the pitch

- Voice browsing agents (Wayfinder, Diamond Access AI, Screen Agent), voice form fillers (fill.ai, ConWeb) and general agentic browsers all exist. Do not claim to be the first autonomous voice browser.
- Our claim: **autonomy that a blind user can trust**. The agent does the whole task, and the design guarantees that irreversible steps, sensitive data and human-only checks always come back to the user, with the real page values read back.
- Research on agentic browsers as assistive tools points to limited user control and trust. "stop" at any moment, the step log, the irreversible-action gate and read-back address that directly.
- "We never bypass security checks or type passwords. The agent does everything up to those steps, hands them to the user, and continues."
- Safety is layered: Jev is a fast semantic check; the domain policy, irreversible hold, DOM verifier and the user's confirmation are the guarantees.
- Credit Handy, Piper, Ollama, Playwright and the other open-source tools.

## 20. Open questions

| Question | Who answers | By |
|---|---|---|
| Real submission and demo time | Prashanth | 18:30 |
| Hackathon rules on open-source and reference code | Prashanth | 18:30 |
| Jev access (hosted key, credits from organizers?) | M4 | 19:00 |
| Which machine hosts Ollama, and can all others reach it | M1 | 19:30 |
| Is the venue network fine for real sites and the search engine | M3 | 20:30 |
| Does Handy paste reliably into the Console on each demo machine | M2 | 20:30 |
| Does `bring_to_front()` really restore OS focus | M3 with M2 | 20:30 |

## 21. Ticket backlog (GitHub issues)

Ticket IDs are stable; use them in branch names and PR titles. Owners: CORE = Prashanth, UI = Vishal, BRW = Sudeepti, JEV = Abishek. "Depends on" lists tickets that must be merged first; CORE-01 stubs are enough for most work to start.

### Core backend (M1, label `role:core`)

| ID | Title | P | Milestone | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| CORE-01 | Repo skeleton with contract stubs | P0 | CP1 Foundation | none | Folder layout from PRD Section 7; every module in Section 12 exists with the exact signatures and stub bodies returning fixed, realistic values; `main.py` serves `/health`, `/console` (placeholder page) and `/ws/console` (echoes utterances as `speak`); `requirements.txt`, `.env.example` (every variable in Section 7), `tests/test_smoke.py` committed; a teammate can clone, install and run it |
| CORE-02 | `llm.py` against Ollama | P0 | CP1 Foundation | CORE-01 | Returns text or a validated tool call; temperature 0; `num_ctx` from config; malformed tool output retried once; works from every team machine |
| CORE-03 | LLM reliability test for autonomy | P0 | CP2 Decision gate | CORE-02 | 10 runs each of a `fill_field` call on a sample form and a `click` choice on a sample search-results snapshot; pass counts reported at CP2 (target 9/10 each); model choice recorded |
| CORE-04 | `config.py` | P0 | CP1 Foundation | CORE-01 | All env vars from Section 7 with defaults; gate thresholds; blocked domains; sensitive keys |
| CORE-05 | Reference repo study | P1 | CP2 Decision gate | none | `docs/REFERENCE_NOTES.md`, about 10 lines: structure, how the agent starts, browser connection, prompt and page-state ideas to borrow |
| CORE-06 | `session.py` state machine | P0 | CP3 Modules | CORE-01 | Allowed-transitions table; illegal transition raises; unit test proves COMMITTING is unreachable without `confirmed=True` and a `pending_action`; PAUSED and NEEDS_HUMAN_CHECK save and restore state |
| CORE-07 | `profile.py` encrypted profile | P0 | CP3 Modules | CORE-01 | Fernet with a PBKDF2 key from the PIN and a random salt; sensitive fields encrypted; wrong PIN raises `WrongPinError`; file outside the repo; unit tests |
| CORE-08 | `tools.py` schemas, executor and domain policy | P0 | CP3 Modules | CORE-06, CORE-07 | All tools from Section 12; placeholder substitution; `domain_allowed` blocks `BLOCKED_DOMAINS`; profile values typed only on approved or trusted domains; expected values recorded with type; irreversible elements stored as `pending_action`, never clicked; result strings contain no raw sensitive values; no submit or commit tool; unit tests with a stub page |
| CORE-09 | Site and intent resolution | P0 | CP3 Modules | BRW-05 | `resolve_target` maps aliases from `sites.json`, plain URLs and domains; otherwise the agent uses `web_search`; the destination domain is announced; tests for 5 phrasings |
| CORE-10 | Autonomous agent loop | P0 | CP4 First end to end | CORE-08, BRW-03 | Step cap from config; snapshot and history trimmed to fit the context; page content labelled untrusted; one-phrase narration per step and a `step` event; failure counter with retry or alternative and `ask_user` after 2 failures; gate called before risky actions; human-check pause and resume; `stop` halts within one step; typed requests complete demo tasks A and B |
| CORE-11 | `main.py` integration | P0 | CP4 First end to end | CORE-10, UI-02 | WebSocket routing; command matcher before the agent; every event in Section 12 sent to the Console; refocus after actions; one command starts the full system |
| CORE-12 | Irreversible-action confirmation flow | P0 | CP4 First end to end | CORE-08, JEV-02, JEV-03 | A held action triggers verify (for forms), read-back or `describe_pending`, a `pending` event and AWAITING_CONFIRM; "confirm" runs `commit_pending`; "no" or "change <field>" returns to ACTING; unit test proves nothing irreversible runs without "confirm" |
| CORE-13 | Final integration and freeze | P0 | Freeze and demo | all P0 | Demo tasks A and B pass twice in a row by voice on the demo machine; `demo-v1` tagged |
| CORE-14 | Start script and keyboard shortcut | P1 | CP5 Full loop | CORE-11, BRW-02 | `scripts/start.ps1` and `scripts/start.sh` start the backend if it is not running (wait for `/health`), open the Console and agent browser, and do not start a second backend if run twice; `docs/START_KEY.md` explains binding the script to a keyboard shortcut with the OS (checked against current Windows and macOS documentation); pressing the key from another app brings the system up and the agent says it is ready |

### UI, frontend and voice (M2, label `role:ui`)

| ID | Title | P | Milestone | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| UI-01 | Handy setup on every demo machine | P0 | CP1 Foundation | none | Installed, models downloaded, hold-to-talk shortcut, permissions, paste settings tested; wired headset works; steps written in `SETUP.md` |
| UI-02 | Voice Console page | P0 | CP2 Decision gate | CORE-01 | Always-focused text box; 900 ms debounce or Enter sends `utterance`; shows status, live step log, transcript, masked field table, pending action and alerts from the Section 12 events; reconnects if the socket drops |
| UI-03 | Console accessibility | P0 | CP3 Modules | UI-02 | Keyboard-only operation; Escape = stop; ARIA live region for agent messages; large text; high contrast; focus never leaves the text box; checked with VoiceOver or NVDA |
| UI-04 | Handy decision gate | P0 | CP2 Decision gate | UI-01, UI-02, BRW-02 | 10-utterance test plus focus test across 5 actions; result (pass or fail) posted at 20:30; notes whether the Console can stay a small always-on-top window and whether an OS-level refocus helper is needed; if Handy fails, notes whether a wake word is practical |
| UI-05 | Fallback STT (only if UI-04 fails) | P0 | CP3 Modules | UI-04 | `WhisperSTT` with faster-whisper and silero-vad behind `STT`; switched with `STT_BACKEND=whisper`; 9/10 test passes |
| UI-06 | `voice.py` output and commands | P0 | CP3 Modules | CORE-01 | `PiperTTS` with `interrupt()`; `BrowserTTS` fallback; `match_command` covers every command in Section 12; `spoken_digits`; `words_to_digits`; unit tests for the text functions |
| UI-07 | Onboarding and PIN unlock | P0 | CP4 First end to end | CORE-07, UI-06 | Questions spoken one at a time; each answer read back and confirmed; sensitive values typed and hidden on screen; PIN set and confirmed; unlock works after restart; wrong PIN handled clearly |
| UI-08 | Voice polish | P1 | Freeze and demo | CORE-11 | Barge-in works; "stop" and "pause" work mid-task; "where am I" and "what can I say" answered; narration stays short; friendly error messages; five consecutive clean voice runs |

### Browser perception and sites (M3, label `role:browser`)

| ID | Title | P | Milestone | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| BRW-01 | Mock portal | P0 | CP1 Foundation | none | `mock_site/portal/`: landing page with Apply link; form with tabs "Personal Details" and "Bank Details"; fields from Section 11; labels and `aria-invalid` errors; validation messages; help link opening a new tab; fake "I'm not a robot" step; **PIN code field silently drops its last digit**; Submit shows an acknowledgment number; a human can complete it |
| BRW-02 | `browser.py` controller and focus test | P0 | CP2 Decision gate | none (start standalone, fit to the CORE-01 stub once merged) | Headed Playwright with agent and Console windows; follows and announces new tabs; `switch_tab`, `close_tab`, `go_back`, `refocus_console`; `scripts/focus_test.py` reports Console focus across 5 clicks for UI-04 |
| BRW-03 | `perception.py` snapshot and main text | P0 | CP3 Modules | BRW-02 | Ids and locators per contract; label fallbacks (aria-label, placeholder, nearby text, name/id); errors; one-paragraph summary; `main_text` returns readable article text without menus; iframe handling; size caps; correct JSON for every mock page and for one real Wikipedia article |
| BRW-04 | `humancheck.py` | P0 | CP3 Modules | BRW-01 | Detects the fake check, OTP fields, password fields and the mock checkout payment page; silent on normal pages; reports when the challenge is gone |
| BRW-05 | `sites.json` directory | P0 | CP3 Modules | BRW-01 | Entries for the mock portal, mock shop, mock search and 4 real sites (Wikipedia, a news site, a gov.in page, DuckDuckGo) with aliases, domain and trusted flag |
| BRW-06 | Real-site tests | P1 | CP5 Full loop | BRW-03 | Snapshot and `main_text` on 3 real sites and the real search page; whether Playwright is blocked; findings and fallbacks in `docs/REAL_SITE_NOTES.md` |
| BRW-07 | Logged-in Chrome: real Chrome with a persistent agent profile, or attach over CDP | P0 (fallback: stays `chromium`) | CP4 First end to end | BRW-02 | `BROWSER_MODE=chrome`: the backend starts the installed Chrome with remote debugging on 127.0.0.1 and `AGENT_PROFILE_DIR`, waits until it answers, and attaches over CDP with the same `BrowserController` interface; `attach` connects to a running Chrome; `chromium` stays the default fallback. **Proof first:** sign in to Gmail by hand once, close Chrome, reopen via the agent, still signed in (recorded in `docs/REAL_SITE_NOTES.md`). Agent tabs use the signed-in default context; the Voice Console is its own window of the same Chrome and `scripts/focus_test.py` passes in this mode. Task D on real Gmail: open inbox, open newest message, `main_text` reads it; `gmail` and `my mail` aliases in `sites.json`, `trusted: false`. No automation-hiding flags and no fake user agent |
| BRW-08 | Irreversible-control flagging | P0 | CP3 Modules | BRW-03 | Every button and submit input gets `irreversible` and `kind` from text, form submit type and target hints (submit, pay, buy, place order, send, post, delete, accept); unit tests across all mock pages with no missed irreversible control |
| BRW-09 | Mock open-web pages | P1 | CP4 First end to end | BRW-01 | `mock_site/web/`: search results page reading `?q=`, an article page, a shop with product list, cart and checkout (payment form for the hand-off); work with `SEARCH_URL` pointed at the mock search; also a mock inbox and message page for offline Task D tests |

### Jev, verification and demo (M4, label `role:jev-demo`)

| ID | Title | P | Milestone | Depends on | Acceptance criteria |
|---|---|---|---|---|---|
| JEV-01 | Jev and jevals research | P0 | CP1 Foundation | none | `docs/JEV_NOTES.md`: access method, cost, real API, example call; backend decision (jev, llm or rules) posted by 19:00 |
| JEV-02 | `verifier.py` | P0 | CP3 Modules | CORE-01 | Reads real values (inputs, dropdown text, checkboxes); type-aware normalisation (dates, phone with +91, Aadhaar grouping, case, spaces); unit tests catch the truncated PIN code and a missing required field |
| JEV-03 | `readback.py` and pending description | P0 | CP3 Modules | CORE-01 | Read-back chunks from actual values; digits separated; sensitive values masked to the last four; ends with the confirm or change instruction; `describe_pending` names the action, the site and any total shown; unit tests |
| JEV-04 | `gate.py` rules layer | P0 | CP3 Modules | CORE-04 | Risk classes from the Section 10 autonomy policy; block navigation to blocked domains; block profile fills on unapproved domains; first sensitive fill per domain returns `ask_user`; irreversible elements never return `proceed`; unit tests |
| JEV-05 | `gate.py` Jev layer | P0 | CP5 Full loop | JEV-01, JEV-04 | Semantic checks (action serves the user's goal; right element or field for the value); thresholds from config; `ask_user` for a mid-confidence test case; an injected instruction on a page is not followed; switchable backend |
| JEV-06 | `audit.py` | P1 | CP4 First end to end | CORE-01 | JSONL log; sensitive keys dropped automatically; test proves no raw values are written |
| JEV-07 | End-to-end tests | P0 | CP5 Full loop | CORE-11 | Scripted typed runs of demo tasks A (mock search), B and C; planted trap caught; human check paused and resumed; nothing irreversible runs without "confirm"; pass or fail printed |
| JEV-08 | Demo script and deck | P0 | Freeze and demo | none | `docs/DEMO.md` with the 3-minute script from Section 17; deck with problem, architecture, autonomy policy, safety layers, competition and roadmap |
| JEV-09 | Rehearsals and backup video | P0 | Freeze and demo | CORE-13 | Two full rehearsals on the demo machine and venue network; backup video of a clean run saved |

## 22. Instructions for coding agents (also in `CLAUDE.md` and `AGENTS.md`)

- Read `docs/PRD.md` first, especially Sections 10, 12 and 13.
- Obey the hard rules in Section 10. Never add a submit or commit tool for the LLM. Never put real profile values in prompts, logs, tool results or Console events. Never automate CAPTCHA, OTP, passwords or payment.
- Edit only the files owned by your role (Section 13). If you need a change elsewhere, stop and say so.
- Code against the signatures in Section 12. Use the CORE-01 stubs for modules that are not merged yet.
- Do not guess library APIs (Playwright, jevals, Piper, faster-whisper, FastAPI WebSockets). Check the installed version's documentation.
- Do not copy code from the reference repo. It is a design reference only.
- Work on one issue at a time, on a branch named after it. Finish with the issue's acceptance criteria and report the real output, not a summary of success.
