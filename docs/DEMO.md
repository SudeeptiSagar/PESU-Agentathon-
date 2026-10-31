# Demo script and slide outline (JEV-08)

| | |
|---|---|
| Ticket | JEV-08 |
| Owner | Abishek (M4) |
| Version | 1.0, Sat 31 Oct 2026 |
| Script source | [PRD.md](PRD.md), Section 17 (v3.1) |
| Deck | **Outline only** (Section 8). The PowerPoint was descoped by the owner. Do not build a `.pptx` from this without asking. |
| Rehearsal status | **Not rehearsed.** JEV-09 is blocked on CORE-13. No live timing, latency number or backup video exists yet. See Section 10 and [REHEARSAL.md](REHEARSAL.md). |

Read this with [PRD.md](PRD.md) Sections 10, 17 and 19, and [AGENTS.md](../AGENTS.md) hard rules. The demo must never break a hard rule to look good.

## 0. How to read the script

- **Presenter lines in quotes are exact.** Say them as written. They are short on purpose.
- **Agent lines marked "expected" are content, not a teleprompter.** The agent generates its own wording at runtime. The line states what the agent must convey; the exact words may differ.
- **Timings are budgets, not measurements.** They have not been validated on the demo machine. Rehearsal R1 replaces them with measured times (see [REHEARSAL.md](REHEARSAL.md)).
- Bracketed text is a stage direction, never spoken.
- The presenter speaks the user's task in first person ("Find out where..."). The same human can present and play the user, or a second teammate can play the user. Pick one before R1 and keep it fixed.

## 1. Non-negotiables on stage

1. Never speak the profile PIN or any Aadhaar, bank account or IFSC value. Unlock before the demo, or type the PIN into the Console in typed-secret mode.
2. Never say "confirm" for Task C. The agent must hold "Place order" and hand over.
3. Never complete the robot check by automation. A human clicks it; the agent waits.
4. Never debug on stage. The operator calls a fallback at the first trigger, not after three attempts.
5. Do not claim a rehearsal, a latency number, a pass rate or the Gmail stretch unless it has happened and is recorded. See Section 9.

## 2. Timing at a glance

| Beat | Window | Budget | Hard mark |
|---|---|---|---|
| Hook | 0:00 to 0:20 | 20 s | Task A starts by 0:20 |
| Task A, open web | 0:20 to 1:00 | 40 s | Task B starts by 1:00 |
| Task B, form | 1:00 to 2:10 | 70 s (up to 90 s if Task C is cut) | Task C or Close starts by 2:10 |
| Task C, stop point (P1) | 2:10 to 2:30 | 20 s | Close starts by 2:30 |
| Close | 2:30 to 3:00 | 30 s | Stop talking at 3:00 |

Cut rule: if Task B is still running at 2:05, the operator cuts Task C and goes to the Close at 2:30. Task C is P1; the Close is not optional. If Task B is still running at 2:30, the presenter starts the Close over the agent, then says "stop" once, and the agent stops.

## 3. The script

### Beat 1: Hook (0:00 to 0:20)

Presenter, exact:

> "Screen readers read the web. They do not use it. A blind user still finds every link, fills every field, and catches every error. One wrong entry on a form, or one wrong click in a shop, costs real money. So we built a browser that does the whole task, and stops only where a human must decide."

- Expected agent lines: none. The app is idle and quiet.
- Console: `state = IDLE`, empty step log, empty field table, no pending action.
- Fallback: if the app is not up at 0:00, the operator starts it with the start script while the presenter finishes the hook. Task A starts when the Console shows connected, even if that is after 0:20. Do not restart the app during the hook for any other reason.

### Beat 2: Task A, open web (0:20 to 1:00)

Presenter, exact:

> "Ramesh has one question. He speaks it, and then he does nothing else."

[Presenter holds the Handy key and speaks the task, then releases.]

> "Find out where Kalpana Chawla was born."

Expected agent lines, in order:

1. "Searching the web." (around 0:30)
2. "Opening Wikipedia." (around 0:35; the site name must match the actual result)
3. "Reading the article." (around 0:40)
4. "Kalpana Chawla was born in Karnal, Haryana. Want me to read more?" (around 0:48)

Presenter, exact, after the answer:

> "Search, open, read, answer. He never touched the page."

- Console should show: `state = ACTING`, then `DONE`; a `step` line for `web_search`, `navigate`, `read_page`, `finish`; the spoken answer also appears as a `speak` event. No pending action, no field table.
- Timing: utterance by 0:26, search by 0:32, article open by 0:40, answer by 0:52, presenter line by 0:58.
- Fallback A (network or search blocked): switch `SEARCH_URL` to `http://localhost:8000/web/search.html?q={q}`, restart the backend, run the same utterance. Say first: "The venue network is blocking real search, so we are on our offline mirror of the same pages." The mock article must contain the Karnal, Haryana answer.
- Fallback B (real site loads but is slow or blocked): cut to the mock article through the same mock search. Do not wait more than 10 seconds for a page.
- Fallback C (voice input fails): operator types the utterance into the Console text box and presses Enter. Say: "I am typing the request so the demo keeps moving; the path after this is identical."
- If the answer comes back wrong or vague: do not read more. Say "The agent is unsure, which is a checkpoint, not a guess", ask it to stop, and go to Task B. Do not improvise a second live attempt.

### Beat 3: Task B, form (1:00 to 2:10)

Presenter, exact:

> "Now a government form. This portal has a trap we planted: it drops the last digit of the PIN code. Watch the verifier."

> "Apply for the disability pension on the demo portal."

Expected agent lines, in order:

1. "Opening the demo pension portal." (about 1:12)
2. "Filling personal details from your profile." (about 1:20)
3. "Filling bank details." (about 1:30)
4. Verifier catch, about 1:36: "The PIN code on the page reads 5 6 0 0 0. Your profile says 5 6 0 0 0 1. Correcting it." Then, after a re-check, if the retry succeeds: "The PIN code is now correct."
5. Robot check, about 1:44: "There is an I'm not a robot check. Please complete it in the browser, then say done."
6. Read-back, about 1:52: the agent reads the actual page values. The current build reads every filled field, so the first four risk fields are: "Name: Ramesh Kumar. PIN code: 5 6 0 0 0 1. Aadhaar ending 1 2 3 4. Bank account ending 4 3 2 1." Then the remaining fields, then "Say confirm to go ahead, or say change followed by the field name." If CORE-12 adds a compact read-back that says "everything else matches your profile", use that; do not claim it before it exists.
7. After "confirm": "Submitted. Your acknowledgment number is [number from the mock acknowledgment page]."

Presenter, exact, at the robot check:

> "Done."

[The presenter, as the human, clicks the "I'm not a robot" checkbox in the agent browser, then says "Done". The agent must not click it.]

Presenter, exact, at the read-back:

> "Confirm."

Presenter, exact, after the acknowledgment:

> "The page was wrong. The verifier read the real page, and Ramesh confirmed by voice."

- Console should show: `state = ACTING`, then `VERIFYING`, a warn-level `alert` naming the PIN code mismatch (expected `560001`, actual `56000`), then `NEEDS_HUMAN_CHECK` while the robot check is open, then `READBACK`, `AWAITING_CONFIRM` with a `pending` description, `COMMITTING`, `DONE`.
- Console field table: one row per field with a masked value. Aadhaar and bank account and IFSC show only the last four digits. The PIN code is a postal code, not a secret, so it shows in full.
- Console must never show: a full Aadhaar, bank account, IFSC or the app PIN. If it does, that is a hard-rule failure; stop the demo.
- Values in line 6 come from the prepared demo profile. The worked example assumes `full_name` Ramesh Kumar and `pin_code` 560001. Set the profile to match before R1, or adjust the example. Do not let the agent read a value that is not in the profile.
- Timing: utterance by 1:04, both tabs filled by 1:34, trap caught by 1:42, robot check done by 1:50, read-back by 2:02, acknowledgment by 2:08, presenter line by 2:10. This is tight. Rehearse it before promising it.
- Dependency, now verified against the real mock portal (`mock_site/portal/apply.js`, 31 Oct): the PIN-code trap fires once, drops the sixth digit (`560001` -> `56000`), and later fills are kept. The correction in line 4 therefore works. The Console alert must show `expected 560001` and `actual 56000`. Re-confirm on the demo machine in R1.
- Fallback A (read-back runs long, more than 15 seconds): do not interrupt it. Cut Task C and let Task B use the 20 seconds. The Close still starts at 2:30.
- Fallback B (robot check not detected): the presenter clicks the checkbox anyway and says "Done"; if the agent does not resume, the operator presses the Console key for pause/continue. Do not let the agent click the checkbox.
- Fallback C (verifier does not catch the truncation): stop. Say "The verifier missed the planted error, so we are not submitting." Do not say "confirm". This is a no-go for the live demo and the recorded video must be used. Report it as a bug.
- Fallback D (voice input fails): operator types "Apply for the disability pension on the demo portal" and later "confirm". The confirmation must still come from the user role, by voice if the microphone works, by typed Console text if it does not. Never let the operator type "confirm" silently while the presenter is talking; say what is happening.

### Beat 4: Task C, stop point (2:10 to 2:30, P1, cut if not ready)

Presenter, exact:

> "Last one. A shop, where money is involved."

> "Order the Braille story book from the demo shop."

Expected agent lines, in order:

1. "Opening the demo shop." (about 2:16)
2. "Added the Braille story book to the cart. Total 249 rupees." (about 2:22; use the total the shop actually shows)
3. "The next step is Place order, which takes you to payment. I have held it. I will hand over to you." (about 2:28)

Presenter, exact, over the end of line 3:

> "It stopped before the money. That is the design."

- Console should show: `state = AWAITING_CONFIRM`, a `pending` event with the description "I'm about to press Place order on demo shop. Total 249 rupees.", and `step` lines for navigate, click (add to cart), read page. It must not show `COMMITTING`.
- The agent must not click "Place order", must not open the payment page, and must not ask for card details. If it does, that is a hard-rule failure; say "stop" immediately.
- Fallback: if the mock shop is not ready, skip Task C entirely. Do not substitute a real shop. Say: "The shop stop point is the next task; today the form is the money-adjacent proof." Then go to the Close at 2:30.
- If the total differs from 249 rupees, say the real total. Never read a number off the slide instead of the page.
- Product mismatch: PRD Section 17 says "AA batteries", but `mock_site/web/cart.js` stocks a folding cane (649), a talking watch (899), a talking calculator (499) and a Braille story book (249). Use the Braille story book, or ask M3 to add batteries. Do not say "batteries" unless the shop really shows them.

### Beat 5: Close (2:30 to 3:00)

Presenter, exact:

> "Three things to take away. One: autonomy with verification. The agent acts, the verifier reads the real page, and Ramesh confirms anything irreversible. Two: local and private. Speech in, speech out and the model run on our own hardware, and the profile is encrypted and never sent to the model. Three: stop works at any moment, in code. Next: a hosted phone version, more languages, and your own Chrome. A browser a blind user can trust with the whole task."

- Expected agent lines: none. The agent is idle after Task B or holding the Task C pending action.
- Console: `DONE` after Task B, or `AWAITING_CONFIRM` after Task C. Leaving the pending action visible during the Close is good: it shows the agent waiting, not acting.
- Fallback: if the demo overran, drop the first sentence and start at "One: autonomy with verification." Never drop the "stop works" line or the roadmap.

### Presenter cue card

Say only these, in order:

1. "Screen readers read the web. They do not use it. ... stops only where a human must decide."
2. "Ramesh has one question. He speaks it, and then he does nothing else."
3. "Find out where Kalpana Chawla was born."
4. "Search, open, read, answer. He never touched the page."
5. "Now a government form. This portal has a trap we planted: it drops the last digit of the PIN code. Watch the verifier."
6. "Apply for the disability pension on the demo portal."
7. "Done." [after clicking the robot check]
8. "Confirm."
9. "The page was wrong. The verifier read the real page, and Ramesh confirmed by voice."
10. "Last one. A shop, where money is involved."
11. "Order the Braille story book from the demo shop."
12. "It stopped before the money. That is the design."
13. "Three things to take away. ... A browser a blind user can trust with the whole task."

## 4. Console cheat sheet for judges

| State or event | What it proves |
|---|---|
| `step` log with action, target, result | The agent's actions are visible, not hidden in a black box |
| `state` changes ACTING to VERIFYING | Verification is a real step, not a spoken claim |
| warn `alert` with expected versus actual | The planted PIN-code error was caught from the page |
| `NEEDS_HUMAN_CHECK` | A human-only step paused the agent and it resumed |
| `field_table` with masked values | Sensitive values are masked on screen |
| `READBACK`, then `AWAITING_CONFIRM` | Nothing irreversible runs without the user's word |
| `pending` still showing at 3:00 | The agent waits; it does not act on its own at payment |
| No `COMMITTING` in Task C | "Place order" was held, not clicked |

## 5. Pre-demo checklist

Run this on the demo machine, in this order. Times are relative to going on stage. Owner: operator unless stated.

### T-60: machine and network

| # | Check | How | Pass condition |
|---|---|---|---|
| 1 | Ollama is up | `Invoke-RestMethod http://localhost:11434/api/tags` | Returns a model list, no connection error |
| 2 | The model is pulled | `ollama list` | The name equals `LLM_MODEL` (default `qwen3:8b`) |
| 3 | Network profile is known | Open one real site and the search engine | Both load, or the operator has already switched to the mock search |
| 4 | Mock sites are up | `cd mock_site; python -m http.server 8000` | `http://localhost:8000/portal/` and `http://localhost:8000/web/search.html?q=test` both return 200 |
| 5 | Backend is up | `python -m app.main` | `http://localhost:8080/health` returns healthy |
| 6 | Console is up and focused | `http://localhost:8080/console` | Text box has focus; status shows connected; press Escape and see it is handled |
| 7 | Playwright browser is installed | `playwright install chromium` (already done) | Agent browser opens headed, Console window opens |
| 8 | No second backend | Check for a stray process on port 8080 | Only one backend; the start script does not start a second (CORE-14) |
| 9 | Notifications and updates off | OS settings | No toast can cover the Console or steal focus; updates paused; screen lock off; power plugged in |
| 10 | No private tabs or files on screen | Close everything else | No personal browser tabs, no `.env`, no profile file, no chat windows |

### T-30: configuration

| # | Variable | Expected | Why |
|---|---|---|---|
| 11 | `OLLAMA_URL` | Reachable host, default `http://localhost:11434/v1` | `llm.py` strips `/v1`; do not "fix" it in a panic |
| 12 | `LLM_MODEL` | The model pulled in check 2 | Mismatch is the most common silent failure |
| 13 | `NUM_CTX` | `8192` | Smaller context makes the agent ignore rules |
| 14 | `SEARCH_URL` | Default search, or the mock search URL | Contains `{q}` or the app refuses to start |
| 15 | `STT_BACKEND` | `handy` (or `whisper` if that is what was tested) | Must match what the machine actually runs |
| 16 | `TTS_BACKEND` | `piper` with a valid `PIPER_VOICE` path, else `browser` | A missing `.onnx` file fails at the worst moment |
| 17 | `GATE_BACKEND` | `rules`, `llm` or `jev`, whichever was tested | Say the live backend in Q&A; do not imply Jev runs if it does not |
| 18 | `GATE_PROCEED`, `GATE_ASK` | `0.85`, `0.5` unless tuned and recorded | Do not tune thresholds on stage |
| 19 | `MAX_STEPS`, `MAX_FAILURES` | `30`, `2` | The loop must stop, not spin |
| 20 | `BLOCKED_DOMAINS` | The intended list for the demo | An empty list is a policy gap, not a feature |
| 21 | `PROFILE_PATH` | The prepared demo profile, default `~/.voiceagent/profile.json` | Fresh profile or a known-good one, never created live |

### T-15: voice, profile and safety

| # | Check | Pass condition |
|---|---|---|
| 22 | Handy is running with its model loaded | Hold-to-talk shortcut works in a scratch text box |
| 23 | Wired headset is connected and selected | The presenter's narration is not re-heard as a command; microphone level is healthy |
| 24 | Handy paste test into the Console | 9 of 10 short utterances arrive as exact text; no stale clipboard content |
| 25 | Piper speaks | The agent's voice is audible over the room audio; digits are separated; interrupt works |
| 26 | Browser speech fallback works | Set `TTS_BACKEND=browser`, restart, and confirm the Console voices a `speak` event |
| 27 | Profile unlock | The prepared profile unlocks with the demo PIN, typed, not spoken; wrong PIN is not tried |
| 28 | Profile values are fake demo values | No real Aadhaar, bank account, phone or address of a team member anywhere |
| 29 | Sensitive values are masked | Console field table and logs show only the last four digits for Aadhaar, bank account and IFSC |
| 30 | Robot check is clickable by a human | The checkbox responds to a mouse or keyboard; the agent does not touch it |
| 31 | Stop is tested | Spoken "stop" and Escape each halt the agent within one step, five times in a row, on this machine |
| 32 | Pause and continue are tested | The state returns to the same step after continue |
| 33 | Start key is tested | The OS shortcut (or the start script) brings the stack up and the agent says it is ready |
| 34 | Backup video plays | Full screen, with audio, on the demo machine, from outside the repo, and it is the current build |

### T-5: stage

| # | Check | Pass condition |
|---|---|---|
| 35 | Timer is visible to the presenter only | Phone or laptop timer, silent, started at 0:00 |
| 36 | Projector shows the Console and the agent browser side by side | Text is readable from the back of the room; no sensitive value visible |
| 37 | Presenter has the cue card | Printed or on a second screen the audience cannot see |
| 38 | Operator has the fallback commands ready | `SEARCH_URL` switch, `TTS_BACKEND=browser`, typed Console input, video path |
| 39 | The team knows who calls the fallback | Operator, at the trigger, once. The presenter never debugs |
| 40 | The demo profile and `.env` are not in the repo | `git status` clean of secrets; nothing staged |

## 6. Backup plan A, B and C

| Plan | Trigger | What changes | Who decides | Time to switch |
|---|---|---|---|---|
| A: live, real web | Default | Nothing. Voice input, real search, live mock portal and shop | Operator | 0 s |
| B1: live, mock web | Venue network blocks search, or a real page takes more than 10 s | Set `SEARCH_URL=http://localhost:8000/web/search.html?q={q}`, restart backend, say why | Operator | About 30 s |
| B2: live, typed input | Handy or the microphone fails twice | Type each utterance into the Console and press Enter; the confirmation stays a deliberate user action | Operator, announced by presenter | About 5 s per utterance |
| B3: live, browser speech | Piper fails or the audio route dies | Set `TTS_BACKEND=browser`, restart, Console speaks through `speechSynthesis` | Operator | About 30 s |
| C: recorded video | Backend or browser crashes twice, or the live path is unsafe (verifier missed the trap, irreversible action ran) | Stop the live demo. Play the backup video full screen with audio. Presenter narrates the same beats and points at the Console | Operator calls it; presenter announces "We are switching to our recorded run" | About 20 s |
| C-last: walkthrough | The video will not play | Use the slide outline and the stored step-log screenshots; be explicit that it is a recording, not live | Presenter | Immediate |

Rules:

- One restart only. If the stack is not healthy after one restart, go to Plan C.
- If a real site fails and the mock mirror is not ready or also fails, go to Plan C. Do not keep trying live pages.
- Never re-run a beat live "to see if it works now" in front of judges.
- Never show a fallback that hides a safety failure. If the verifier missed the trap or an irreversible action ran, the demo is over and the video is the honest path.
- The backup video must be recorded from the same build that is on stage. Re-record after any demo-path code change (see [REHEARSAL.md](REHEARSAL.md)).

## 7. Q&A: eight likely judge questions

Keep answers under 30 seconds. Do not invent numbers.

**1. How do you stop it doing something wrong?**
Five layers: a domain policy in code, a semantic gate, an irreversible-action hold, a DOM verifier that reads the real page, and the user's spoken confirmation. The LLM has no submit or commit tool. "Stop" halts the loop in code within one step, and Escape does the same from the Console.

**2. Where does my data go?**
Speech recognition, speech output and the model run on hardware we control, not in a cloud. The profile is encrypted at rest with a key derived from the PIN, and the model never sees real values: it sees placeholders like `{dob}`, and the executor substitutes them. Visited web pages are, of course, on the internet. There is no cloud backend and no user account.

**3. Do you solve CAPTCHA, OTP or passwords?**
No, and we never will. Those are human-only steps. The agent detects them, saves its state, says what is needed, waits for "done", re-checks, and resumes. Payment details are the same: the agent stops and hands over. That is a product rule, not a limitation we are working around.

**4. What is Jev, and is it the safety guarantee?**
Jev is a fast semantic check: does this action serve the user's stated goal, and is this the right field for this value? Its probability is not independent proof, so it is not the guarantee. The guarantees are the deterministic layers: the domain policy, the irreversible hold, the verifier and the user's confirmation. The gate backend is switchable, and we will tell you which one is running today.

**5. Why not use browser-use or an existing agentic browser?**
Because the safety checks have to sit in the action path. We wrote our own Playwright tool layer so a click can be held, a value can be checked against the real DOM, and a tool the model can call to submit simply does not exist. Existing agents are built for sighted users who can watch and correct them; our user cannot see a wrong click. We are not claiming better general browsing, only a safer path for this user.

**6. What is the latency?**
Each step is one model call on our own hardware, so seconds per step, not minutes, and narration covers the wait. [If measured in rehearsal: state the measured median and the machine.] We will not quote a number we have not measured on this machine.

**7. Is the app itself accessible?**
The Console is keyboard-only, Escape stops, agent messages go into an ARIA live region, and it uses large text and high contrast. It is designed to be checked with NVDA or VoiceOver. [Say whether that check has actually happened. Until UI-03 is verified, say "designed for, not yet audited".]

**8. How is this different from Wayfinder, Diamond Access or a voice form filler?**
Those products exist and we do not claim to be first. Voice browsers read, agentic browsers act, and voice form fillers fill. Our claim is narrower and harder: autonomy that a blind user can trust, because irreversible steps, sensitive data and human-only checks always come back to the user with the real page values read back. We also credit the open-source stack: Handy, Piper, Ollama, Playwright, FastAPI.

## 8. Slide outline (12 slides, no PowerPoint)

Use these only if there is a separate pitch, a judges' table review, or a Q&A screen. The 3-minute demo itself has no slides. Each slide is one bullet block: a title, four to six short bullets, and one evidence line. Do not put paragraphs on a slide.

Slides describe the design as specified in the PRD. Before presenting, check each claim against the merged code. Do not present an unmerged layer as working; the "Honest limits" slide exists for exactly that reason.

### Slide 1: Title

- A browser that does the whole task
- Voice-controlled, autonomous, verified
- Built for blind and visually impaired users
- Agentathon 2026, 24 hours
- Team: Prashanth, Vishal, Sudeepti, Abishek

Evidence line: "Live demo: two core tasks, one stop point, three minutes."

### Slide 2: The problem

- Screen readers read content; the user still does every step
- Find the link, tab through the form, recover from the error
- Agentic browsers assume a sighted user watching the screen
- A blind user cannot see a wrong click or a wrong value
- Mistakes cost money: a wrong form entry, an accidental purchase, data typed into the wrong site
- The research gap is control and trust, not raw capability

Evidence line: "One wrong PIN digit is a rejected application; one wrong click is an order."

### Slide 3: What we built

- One spoken request, one end-to-end task
- Search, open, read, click, type, fill, switch tabs
- Narrates briefly; does not ask permission for every step
- Stops only at defined checkpoints: irreversible, sensitive, human-only, unsure
- Verifies what it typed against the real page before anything irreversible
- Runs on our hardware, no cloud account

Evidence line: "Task A: a spoken question, a spoken answer, no page reading by the user."

### Slide 4: Architecture

- Handy transcribes speech locally and pastes into the always-focused Console
- Console sends `utterance` over a WebSocket to a FastAPI backend
- Agent loop: perception snapshot, one LLM tool call, validation, action
- Domain policy and gate run before risky actions
- Playwright executes in a headed browser; the Console shows every step
- Encrypted profile feeds values through placeholders; the model never sees them

Evidence line: "The step log on screen is the same event stream the backend acts on."

### Slide 5: Autonomy policy

- Read-only: run immediately
- Reversible: run immediately, one short phrase of narration
- Sensitive input: only on approved or trusted domains; first time per domain, ask
- Irreversible: held as pending; verify, read back, require "confirm"
- Human only: CAPTCHA, OTP, password, card details; hand over and wait
- Two failures on the same step: ask a short question instead of guessing

Evidence line: "The LLM has no submit tool. The state machine commits, and only after confirmation."

### Slide 6: Safety layers

- Domain policy and site directory: blocked and unexpected sites
- Jev gate: does the action serve the goal; is this the right field
- Irreversible-action gate: flags on buttons, form submit type, URL hints; hold, never click
- DOM verifier: expected versus actual, with type-aware normalisation
- Read-back and spoken confirmation: the human check the machine cannot replace
- "Stop" in code within one step; audit log with sensitive keys dropped

Evidence line: "Layer five exists because layers one to four can still miss something."

### Slide 7: The planted trap, live

- The mock portal silently drops the last digit of the PIN code
- The agent types the profile value; the page shows a truncated one
- The verifier reads the real DOM, not the intended keystrokes
- The mismatch is spoken and resolved before submit is offered
- Without verification, the application could be rejected silently
- This is a planted failure, shown on purpose

Evidence line: "Expected 560001, actual 56000. The Console shows both."

### Slide 8: Privacy and local-first

- Handy, Piper and Ollama run on our own hardware, not in a cloud
- Profile encrypted with Fernet; key derived from the PIN with PBKDF2 and a random salt
- Aadhaar, bank account, IFSC masked to the last four on screen and in logs
- Placeholders in prompts; the model never receives real values
- No user accounts, no cloud backend
- Pages visited are on the internet; we do not claim offline browsing

Evidence line: "The Console the judges see is the same masked view the user's helper sees."

### Slide 9: Competition and positioning

- Voice browsers exist: Wayfinder, Diamond Access AI, Screen Agent
- Voice form fillers exist: fill.ai, ConWeb
- General agentic browsers exist and are improving fast
- We do not claim to be first
- Our claim: autonomy a blind user can trust
- The difference is the safety path: domain policy, hold, verifier, read-back, confirmation

Evidence line: "Read, act, trust: the third one is the product."

### Slide 10: Honest limits today

- Tasks B and C run on our mock portal and mock shop
- Task A runs on the real web when the venue network allows; otherwise a mock mirror
- Jev is a semantic layer, not the guarantee; the backend may be rules today
- No payments, no passwords, no CAPTCHA bypass, no real government submission
- Timings and pass rates will come from rehearsal; none are claimed today
- Task D, reading Gmail in the user's own Chrome, is a stretch and is not claimed unless it runs

Evidence line: "Everything on this slide is a boundary we chose, not a bug we hid."

### Slide 11: Roadmap

- Hosted phone version, so no laptop is needed
- Multilingual voice, starting with Hindi and Kannada
- The user's own Chrome over CDP, read-only first
- More sites and services through the site directory
- User testing with blind and low-vision participants
- Stronger semantic gate as hosted evaluator access improves

Evidence line: "The safety path is the part that scales; the model is swappable."

### Slide 12: Close

- Autonomy with verification
- Local and private by default
- Stop works at any moment
- A browser a blind user can trust with the whole task
- Thank you; questions

Evidence line: "Ask us to run the stop command live after the demo."

## 9. What not to claim

Source: [PRD.md](PRD.md), Section 19.

| Do not say | Say instead |
|---|---|
| "The first autonomous voice browser." | "Voice browsers and agentic browsers exist. Our claim is autonomy a blind user can trust." |
| "It bypasses CAPTCHA / OTP / bot checks." | "It detects them, hands over to the human, waits, and resumes. We never bypass security." |
| "Jev proves the action is safe." | "Jev is a fast semantic check. The guarantees are the domain policy, the irreversible hold, the verifier and the user's confirmation." |
| "It submits real government applications." | "It submits to our mock portal in the demo. Real submissions are out of scope." |
| "It runs fully offline." | "Speech, speech output and the model run on our own hardware. Visited pages are on the internet." |
| "It is production ready." | "It is a 24-hour prototype with a deliberately narrow, tested demo path." |
| "We rehearsed and the timings are measured." | "Rehearsals are blocked on CORE-13. The timings in this script are budgets." |
| "The app is fully accessibility audited." | "The Console is designed for keyboard and screen-reader use. The audit is UI-03 and only counts when it is done." |
| "It reads your Gmail." | Say nothing about Task D unless BRW-07 has actually run on the demo machine. It is a stretch. |
| "Our agent never makes a mistake." | "The agent can make mistakes; the design catches them before anything irreversible, and the user confirms." |
| "100% pass rate" or any unmeasured number | "Here is the measured result from rehearsal" or "we have not measured that yet." |

Also:

- Do not show a full Aadhaar, bank account, IFSC or the app PIN, even a fake one, if it teaches the audience the wrong norm. Use last-four masking everywhere.
- Do not claim the reference repo's code is ours. It is a design reference only.
- Credit Handy, Piper, Ollama, Playwright, FastAPI and the jevals library where used.

## 10. Rehearsal status (honest)

| Item | Status |
|---|---|
| JEV-08 script and outline | Written, this document |
| JEV-09 rehearsal 1 | **BLOCKED** on CORE-13 |
| JEV-09 rehearsal 2 | **BLOCKED** on CORE-13 |
| Backup video | **Does not exist** |
| Measured timings | **None.** All timings here are budgets taken from PRD Section 17 |
| Measured latency | **None.** Do not quote a number in Q&A |
| Voice pass rate | **None.** UI-04's gate result is not in this document |
| Task D / Gmail | **Not claimed.** Stretch, BRW-07 |

CORE-13 is "Final integration and freeze": demo tasks A and B pass twice in a row by voice on the demo machine, and `demo-v1` is tagged. Until that lands, this script cannot be rehearsed end to end and the backup video cannot be recorded from a known-good build.

The runbook, go/no-go criteria, failure drills and blank sign-off table are in [REHEARSAL.md](REHEARSAL.md). When R1 and R2 happen, update this section with the date, result and measured timings. Do not mark them done before they are.

## 11. Coverage check against PRD Section 17

| PRD Section 17 requirement | Where |
|---|---|
| Hook, 20 s: screen reader reads, does not do; mistakes cost real things | Beat 1 |
| Task A, 40 s: the Kalpana Chawla question; announces search, opens a result, reads, answers; step log shows actions | Beat 2 |
| Task B, 70 s: disability pension on the demo portal; fills both tabs from the profile | Beat 3, lines 1 to 3 |
| Task B: verifier catches the truncated PIN code and the agent says so | Beat 3, line 4 |
| Task B: pauses for the "I'm not a robot" check and resumes after "done" | Beat 3, line 5 |
| Task B: read-back | Beat 3, line 6 |
| Task B: "confirm" | Beat 3 |
| Task B: acknowledgment number spoken | Beat 3, line 7 |
| Task C, 20 s: Braille story book (249 rupees; the PRD says AA batteries but the mock shop does not stock them); adds to cart; reads the total; holds "Place order"; hands over at payment | Beat 4 |
| Close, 30 s: autonomy with verification; local and private; "stop" works; roadmap | Beat 5 |
| Backups: recorded video, mock search via `SEARCH_URL`, browser speech, typed Console input | Section 6 |
| Deck: problem, architecture, autonomy policy, safety layers, competition, roadmap | Section 8, slides 2, 4, 5, 6, 9, 11 |
