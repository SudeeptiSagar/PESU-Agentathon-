# Starter prompts for each team member (PRD v3.0)

The product is now a **fully autonomous, voice-controlled browser**: one spoken request, the agent does the whole task on any website, and stops only at checkpoints (irreversible actions, sensitive data on a new site, CAPTCHA/OTP/login/payment). Read `docs/PRD.md` "What changed in 3.0" first.

Paste your block into Claude Code or Antigravity from the repo root, after `git pull`. Each prompt covers your first tickets. For later tickets, use the "any ticket" prompt at the bottom. Run `git checkout -b <branch>` with the branch name in your prompt before you start.

---

## M1, Prashanth: core backend (first: CORE-01, then CORE-04, CORE-02, CORE-03, CORE-05)

```
Read CLAUDE.md, HANDOFF.md and docs/PRD.md (Sections 7, 10, 12, 13, 21) first.
You are M1 (core backend). Work on branch core/CORE-01-skeleton.

CORE-01: create the repo skeleton so the other three members can start against stubs.
- Folder layout exactly as in PRD Section 7 (app/, client/, mock_site/portal and mock_site/web
  placeholders, tests/, docs/, scripts/).
- Every module in PRD Section 12 exists with the exact signatures, type hints and docstrings,
  and stub bodies that return fixed, realistic values (no NotImplementedError), so imports and
  integration work immediately. Mark every stub with `# STUB: <TICKET-ID>` naming the owner's ticket.
- app/sites.json with the three example entries from PRD Section 11 (M3 will extend it).
- app/main.py: FastAPI on port 8080 with GET /health, GET /console (serves client/console.html if
  present, else a placeholder page), and WebSocket /ws/console that echoes utterances back as a
  `speak` event in the Section 12 event format.
- requirements.txt (fastapi, uvicorn[standard], playwright, openai, cryptography, python-dotenv,
  pytest, pytest-asyncio; add others only when a ticket needs them), .env.example with every
  variable from PRD Section 7, and tests/test_smoke.py that imports every module and hits /health.
- Do not implement real logic for other owners' modules; stubs only.
Acceptance: fresh clone -> venv -> pip install -> `python -m app.main` serves /health and the
WebSocket echo; `pytest -q` passes. Show me the real output of both.

Then CORE-04 (config.py with every variable and default in Section 7, gate thresholds, blocked
domains, sensitive keys), CORE-02 (llm.py against Ollama's native /api/chat, because /v1 ignored num_ctx, temperature 0,
num_ctx from config, validated tool calls, one retry on malformed output), and CORE-03: a script that
runs 10 fill_field calls on a sample form and 10 click choices on a sample search-results snapshot
and prints both pass counts.

Later: CORE-14, a start script plus an OS keyboard shortcut that brings the whole system up (PRD 3.1).
```

## M2, Vishal: UI, frontend and voice (first: UI-01, UI-02, UI-06)

```
Read CLAUDE.md and docs/PRD.md (Sections 5, 8, 10, 12, 13, 21) first.
You are M2 (UI, frontend and voice). You own client/, app/voice.py, app/onboarding.py, SETUP.md only.

UI-01 (no code dependency, do it now): write SETUP.md steps for installing Handy (offline dictation
app, github.com/cjpais/Handy), downloading a model, setting a hold-to-talk shortcut, granting
microphone and accessibility permissions, and Handy's paste-delay / reliable-paste debug settings.
Use Handy's README for the real steps; do not invent menu names.

UI-02 on branch ui/UI-02-console: client/console.html, console.css, console.js.
- One large text box that keeps focus at all times (re-focus on blur).
- When text appears (Handy pastes it), wait ~900 ms after the last change or Enter, send
  {"type":"utterance","text":...} over WebSocket to ws://localhost:8080/ws/console, clear the box.
- Render every backend event in PRD Section 12: speak, state, a live step log (`step`), a masked
  field table, the pending irreversible action (`pending`), alerts. Handle `input_mode`
  typed_secret by masking typed characters.
- Reconnect automatically if the socket drops.
- Accessible: ARIA live region for agent messages, large text, high contrast, keyboard only;
  Escape sends {"type":"key","name":"Escape"} (stop).
Until CORE-01 is merged, test against a tiny local WebSocket echo server.

UI-06 on branch ui/UI-06-voice: app/voice.py per Section 12 (PiperTTS with interrupt(), BrowserTTS
that sends `speak` events, match_command covering stop, pause, continue, repeat, yes, no, confirm,
back, done, where, help; spoken_digits; words_to_digits), with unit tests for the text functions.
Check Piper's current docs for the Python API; do not guess it. Report real test output.

At 20:30 you run UI-04 (Handy decision gate) with Sudeepti's scripts/focus_test.py.
If Handy passes, its hold-to-talk key is the in-app key (the app itself starts from an OS keyboard shortcut, CORE-14);
a spoken wake word is not planned for the demo. See issue #22.
```

## M3, Sudeepti: browser and sites (first: BRW-01, BRW-02, then BRW-09, BRW-03, BRW-08)

```
Read CLAUDE.md and docs/PRD.md (Sections 7, 8.3, 10, 11, 12, 13, 21) first.
You are M3 (browser perception and sites). You own app/browser.py, app/perception.py,
app/humancheck.py, app/sites.json, mock_site/ and scripts/focus_test.py only.

BRW-01 on branch browser/BRW-01-mock-portal (no code dependency, do it now): a static mock
"Disability Pension" portal in mock_site/portal/, plain HTML/CSS/JS, served from mock_site/ with
`python -m http.server 8000`.
- index.html: landing page with an "Apply" link and a help link that opens help.html in a new tab.
- apply.html: in-page tabs "Personal Details" and "Bank Details"; fields full name, date of birth,
  mobile (10 digits), address, PIN code (6 digits), Aadhaar (12 digits, display grouped), annual
  income, category (dropdown), disability percentage, bank account, IFSC. Proper <label for>,
  required attributes, aria-invalid and visible error messages on validation.
- A fake "I'm not a robot" checkbox step before submit (clearly fake, local only).
- PLANTED TRAP: the PIN code field silently drops its last digit (JS truncation), so a correct
  6-digit value ends up wrong.
- ack.html: shows an acknowledgment number after submit. A human must be able to complete it.

BRW-02 on branch browser/BRW-02-browser: app/browser.py per Section 12 using async Playwright, headed:
one window for the agent's browsing and a separate window for the Voice Console
(http://localhost:8080/console); follow and announce new tabs via an on_new_tab callback; list_tabs,
switch_tab, close_tab, go_back, refocus_console. Also scripts/focus_test.py: opens both windows,
performs 5 clicks in the agent window, calls refocus_console after each, and reports whether the
Console has focus (needed for UI-04 at 20:30). Check the installed Playwright docs. Report real output.

Next: BRW-09 (mock_site/web/: search results page reading ?q=, an article page, a shop with cart and a
checkout payment page), then BRW-03 (perception snapshot + main_text) and BRW-08 (flag every
irreversible button with `irreversible` and `kind`).

BRW-07 (PRD 3.2, issue #33) is your main ticket after BRW-08: BROWSER_MODE=chrome starts the installed Chrome with a saved
agent profile and attaches over CDP, so the user signs in to Gmail once and stays signed in. Prove login persistence first;
BROWSER_MODE=chromium stays the fallback. Prashanth will send you the full prompt for it.
```

## M4, Abishek: Jev, verification and demo (first: JEV-01, then JEV-02, JEV-03, JEV-04)

```
Read CLAUDE.md and docs/PRD.md (Sections 10, 11, 12, 13, 17, 21) first.
You are M4 (Jev, verification and demo). You own app/gate.py, app/verifier.py, app/readback.py,
app/audit.py, tests/e2e/ and docs/DEMO.md only.

JEV-01 (do now, report by 19:00): research Jev (TypeSafe AI's evaluator model) and the open-source
jevals library. Read the real README and docs; do not guess. Write docs/JEV_NOTES.md: how to get
access, cost or free tier, the actual Python API to evaluate an agent action and get a decision and
probability, a minimal example, local backend options, and a recommendation: GATE_BACKEND=jev, llm
or rules.

JEV-02 on branch jev/JEV-02-verifier: app/verifier.py per Section 12. Read actual values from the live
page (input_value for inputs, selected option text for selects, checked state), compare against
session.expected with type-aware normalisation (dates, phone with +91/spaces, Aadhaar grouping, case,
whitespace), and report mismatches, missing required fields and visible page errors. Unit tests must
catch a truncated PIN code and a missing required field (small local HTML fixture with Playwright).

JEV-03 on branch jev/JEV-03-readback: app/readback.py per Section 12. build_readback: spoken chunks from
ACTUAL page values ("Label: value"), digits separated by spaces, aadhaar/bank_account/ifsc masked to the
last four, ending with "Say confirm to go ahead, or say change followed by the field name."
describe_pending: one sentence naming the action, the site and any total shown. Unit tests.

JEV-04 on branch jev/JEV-04-gate-rules: the deterministic rules from the PRD Section 10 autonomy policy.
Irreversible elements must never return "proceed". Report real test output.

Later (JEV-07): add Task D (read the newest message in the mock inbox) to the end-to-end tests once BRW-07 and BRW-09 land.
```

---

## Any ticket (use for every later ticket)

```
Read CLAUDE.md and docs/PRD.md first. I am <M1/M2/M3/M4>. Work on GitHub issue <#number> (<TICKET-ID>),
on branch <prefix>/<TICKET-ID>-<short-name>. Follow the hard rules and edit only files I own.
Code against PRD Section 12. Meet every acceptance criterion in the issue, show the real test or run
output, then give me a PR title and description that includes "Closes #<number>".
```
