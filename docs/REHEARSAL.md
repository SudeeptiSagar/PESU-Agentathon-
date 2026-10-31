# Rehearsals and backup video (JEV-09)

| | |
|---|---|
| Ticket | JEV-09 |
| Owner | Abishek (M4) |
| Version | 1.0, Sat 31 Oct 2026 |
| Script | [DEMO.md](DEMO.md) |
| Status | **BLOCKED. No rehearsal has been run, and no backup video exists.** |

## 1. Why this is blocked

JEV-09 depends on CORE-13, "Final integration and freeze". CORE-13 is done when demo tasks A and B pass twice in a row by voice on the demo machine and `demo-v1` is tagged. Neither has happened as of this commit.

Until CORE-13 lands:

- Do not run a rehearsal and call it a JEV-09 rehearsal. Call it a smoke test.
- Do not record the backup video. A video of an unfrozen build is not a backup; it will not match the build on stage.
- Do not fill the sign-off table in Section 11.
- Do not copy budgeted timings from [DEMO.md](DEMO.md) into a "measured" column.

Use this document as the runbook. The only prerequisite work that can happen before CORE-13 is installing the recording tool and testing screen plus audio capture with a throwaway clip that is deleted afterwards.

## 2. Entry criteria for rehearsal 1

All must be true, checked by the operator, before the clock starts.

| # | Criterion | Evidence |
|---|---|---|
| 1 | CORE-13 is merged; demo tasks A and B pass twice in a row by voice on the demo machine | The CORE-13 run output, pasted in the ticket |
| 2 | `demo-v1` is tagged on the commit under test | `git tag --list demo-v1` and `git rev-parse demo-v1` |
| 3 | The demo machine is the machine that will be on stage | Same hardware, same OS build, same audio devices |
| 4 | The demo `.env` is final for the run | Copy kept outside the repo, named by rehearsal |
| 5 | Mock portal, mock shop and mock search are complete for the demo path | `http://localhost:8000/portal/`, `/web/shop`, `/web/search.html?q=test` all load |
| 6 | The prepared demo profile exists and unlocks | Unlock tested, values are fake |
| 7 | Handy, microphone, headset and Piper work on this machine | The checklist in [DEMO.md](DEMO.md) Section 5 passes |
| 8 | A recording tool captures the screen and both audio sources | A 20-second test clip plays back with the agent voice and the presenter voice |
| 9 | The venue network is available, or the gap is recorded | Network name, time of day, and whether real search and Wikipedia load |
| 10 | A second person is available as operator | Named in Section 11 |

If any of 1 to 6 is false, stop. A rehearsal without the real build tests nothing that matters.

## 3. Roles

| Role | Who | Does | Does not |
|---|---|---|---|
| Presenter (P) | Abishek by default, or the person who will present | Speaks every presenter line in [DEMO.md](DEMO.md); plays the user; clicks the robot check | Debug, touch the laptop, type the utterances unless in Plan B2 |
| Operator (O) | A second teammate | Runs the stack, watches the Console and the clock, calls Plan B or C, records the run | Speak on stage, improvise safety claims, retry more than once |
| Timekeeper and scribe (T) | A third teammate, recommended | Calls the hard marks, writes the beat timings and every failure in Section 10 | Coach the presenter mid-run |
| Judge reader (J) | Optional fourth | Asks three Q&A questions from [DEMO.md](DEMO.md) Section 7 after each run, in a judge voice | Comment on the product during the run |

Two people are the minimum: presenter and operator. The operator must not also present; the fallback calls need someone whose only job is the machine.

## 4. Schedule

Two full rehearsals, ideally on different days. Each is 90 minutes and contains two complete timed runs plus drills.

| Rehearsal | When | Where | Network | Purpose |
|---|---|---|---|---|
| R1 | T-24 h or earlier | Demo machine | Closest available network; venue network if access is granted | First real timings, find the failures, cut what does not fit |
| R2 | T-4 h or earlier | Demo machine | Venue network, at the same time of day as the demo | Confirm the fixes, record the backup video, final go/no-go |

If the venue network is not available before the event, say so in Section 11. R1 then runs on the best available network and the venue-network check moves into R2. Do not pretend the venue network was tested.

Session shape (90 minutes):

| Minutes | Activity |
|---|---|
| 0 to 20 | Setup and entry criteria |
| 20 to 25 | Stack smoke test: health, Console, one typed utterance, one spoken utterance |
| 25 to 30 | Run 1, timed, no drills |
| 30 to 40 | Notes and fixes that do not touch code (config, focus, audio, script wording) |
| 40 to 45 | Run 2, timed, with one injected failure chosen by the operator |
| 45 to 60 | Failure drills (Section 9), at least four per rehearsal |
| 60 to 70 | Q&A practice with the judge reader |
| 70 to 80 | Backup video take, only in R2 and only if the run was clean |
| 80 to 90 | Sign-off, evidence, bug filing |

## 5. Setup

### 5.1 Machine and network

1. Power plugged in, sleep and screen lock off, notifications off, OS updates paused.
2. Close every app that is not the stack. No personal browser tabs, no chat, no email.
3. Join the network under test. Write down its name.
4. Check DNS and TLS: open the search engine, Wikipedia and one `gov.in` page. Record which load.
5. Note the time of day. Venue Wi-Fi at 09:00 and at 14:00 are different networks in practice.

### 5.2 Stack

Run from the repo on the demo machine, in PowerShell unless noted.

```powershell
# 1. Ollama
Invoke-RestMethod http://localhost:11434/api/tags
ollama list

# 2. Mock sites, in a second terminal
cd mock_site
python -m http.server 8000

# 3. Backend, in a third terminal
python -m app.main

# 4. Health and Console
Invoke-RestMethod http://localhost:8080/health
Start-Process http://localhost:8080/console
```

Expected: the model in `ollama list` equals `LLM_MODEL`; `/health` responds; the Console connects and the text box has focus; the agent browser opens headed.

### 5.3 Voice

1. Handy is running with its model loaded; the hold-to-talk shortcut works.
2. Wired headset connected, selected as both input and output. Do not use the laptop speakers for input.
3. Ten short utterances into a scratch box: at least nine must arrive exactly.
4. Piper speaks a test line with digits, for example "5 6 0 0 0 1". Interrupt works.
5. Record the fallback state: `STT_BACKEND`, `TTS_BACKEND`, `PIPER_VOICE`.

### 5.4 Profile and `.env`

1. `PROFILE_PATH` points at the prepared demo profile, default `~/.voiceagent/profile.json`.
2. Unlock with the demo PIN, typed. Never speak it, never show it.
3. Confirm Aadhaar, bank account and IFSC are masked in the Console field table.
4. Confirm no real team member data is in the profile.
5. `.env` values match [DEMO.md](DEMO.md) Section 5. Keep a copy outside the repo named `env-r1.txt` or `env-r2.txt` so a config change can be reverted.

### 5.5 Stage and recording

1. Projector or second screen shows the Console and the agent browser side by side, readable from three metres.
2. Presenter's cue card is printed or on a screen the audience cannot see.
3. Timer visible to the presenter and timekeeper, silent.
4. Recording tool installed and tested: OBS Studio (screen plus system audio plus microphone) or Windows Xbox Game Bar (`Win+G`, microphone plus game audio; system audio may need a loopback device). OBS is preferred because it captures system audio reliably.
5. Recording folder is outside the repo, for example `D:\demo-assets\`.

## 6. Run sheet

One run is exactly the script in [DEMO.md](DEMO.md), Section 3. The operator starts the timer at the first word of the hook.

| Mark | Target | Check | If late |
|---|---|---|---|
| Start | 0:00 | Timer starts with the hook | n/a |
| A starts | 0:20 | Presenter says "Ramesh has one question" | Say less in the hook; never skip A |
| A answer | 0:55 | Agent has answered | Stop reading at 0:55 and move to B |
| B starts | 1:00 | Presenter says "Now a government form" | Accept up to 1:05 |
| Trap caught | 1:42 | Console shows the mismatch alert | If not caught by 1:50, hard stop (Section 8) |
| Robot check done | 1:50 | Presenter has clicked and said "Done" | If not detected, presenter clicks anyway and operator continues |
| Read-back started | 1:52 | Agent is reading actual values | If not started by 1:58, prompt once: "read it back" |
| Confirm asked | 2:02 | Agent asks for confirm or change | Do not say confirm before the question |
| Acknowledgment | 2:08 | Agent speaks the number | If not by 2:10, cut Task C |
| C starts | 2:10 | Presenter says "Last one" | Cut C if B overran |
| C holds | 2:28 | Console shows pending, no COMMITTING | Never say confirm |
| Close starts | 2:30 | Presenter says "Three things to take away" | Speak over the agent if needed, then "stop" |
| End | 3:00 | Presenter stops talking | Hard stop |

The timekeeper writes the actual time at each mark, not a summary. The operator writes every failure, including ones that recovered.

## 7. Timing rules

- The Close is fixed. It starts at 2:30 whatever is happening, and Task C is the only beat that can be cut.
- Task B has 70 seconds in Plan A. If the read-back runs long, Task B may use Task C's 20 seconds, so 90 seconds in total, but the Close still starts at 2:30.
- One repeated beat only if the first attempt failed for a non-safety reason and there are more than 20 seconds left. Never repeat a beat to "get a better take" during the live demo; that is what the video is for.
- If the demo is running ahead at 2:20, do not add material. Use the slack to breathe and to leave the pending action on screen.

## 8. Go / no-go criteria

Evaluate after R2. All of the "Go" rows must pass. Any "No-go" row fails the demo, even if everything else passes.

### 8.1 Go

| # | Criterion | Threshold | Evidence |
|---|---|---|---|
| G1 | Tasks A and B pass twice in a row by voice on the demo machine | 2 consecutive clean runs | CORE-13 output plus the two R2 runs |
| G2 | Task B catches the truncated PIN code and corrects it before submit | 2 of 2 runs | Console alert plus spoken line |
| G3 | Robot check pauses and resumes | 2 of 2 runs | Console state NEEDS_HUMAN_CHECK, then resumed |
| G4 | Nothing irreversible runs without "confirm" | 100 percent, every run | No COMMITTING before the confirmation in the log |
| G5 | Task C holds "Place order" and does not reach payment | 2 of 2 runs if C is in the demo | Console pending, no payment page |
| G6 | Spoken "stop" and Escape halt within one step | 5 of 5 each on the demo machine | Timed, one step maximum |
| G7 | Handy transcript accuracy on demo utterances | 9 of 10 or better | Written count |
| G8 | Piper is audible, or the browser fallback is proven | 2 of 2 runs | Room audio check by a listener at the back |
| G9 | Sensitive values masked in Console and logs | 100 percent | Screenshot with last-four only |
| G10 | Full run fits 3:00 with the Close | 3:00 plus or minus 5 s | Two timed runs |
| G11 | Backup video recorded from the demo build and plays with audio | 1 clip, playback tested | Section 10 checklist |
| G12 | Fallbacks tested: mock search, typed input, browser speech | Each drilled once | Section 9 |

### 8.2 No-go

Any one of these stops the live demo. Switch to the recorded video, file a bug, and tell the lead.

| # | No-go | Why |
|---|---|---|
| N1 | An irreversible action runs without "confirm" | Hard rule 2 is broken; the product's claim is false |
| N2 | The agent clicks the robot check, or automates CAPTCHA, OTP or a password | Hard rule 6 is broken |
| N3 | A full Aadhaar, bank account, IFSC or the app PIN appears on screen, in a log, or in a prompt | Hard rule 4 is broken |
| N4 | The verifier misses the planted PIN-code error and the submit is offered | The core demo proof is false |
| N5 | "Stop" does not halt within one step | Hard rule 7 is broken |
| N6 | A fallback hides a safety failure | Dishonest demo |
| N7 | The build on stage is not the build the video was recorded from | The backup is not a backup |

A no-go is not a reason to argue on stage. It is a reason to play the video and fix the bug after.

## 9. Failure drills

Run at least four per rehearsal, chosen by the operator without warning the presenter. Each drill is worth doing even if it feels artificial; the point is the recovery, not the failure.

| # | Drill | Inject | Expected | Pass condition |
|---|---|---|---|---|
| D1 | Network drops during Task A | Disable Wi-Fi after the search is sent | Operator switches `SEARCH_URL` to the mock search, restarts, presenter says why, Task A completes on the mirror | Task A answered within 45 s of the drop |
| D2 | Microphone or Handy fails | Quit Handy, or mute the headset | Presenter announces typed input; operator types the utterance; the same code path runs | Utterance accepted, no restart of the backend |
| D3 | Handy pastes stale or garbled text | Paste an old clipboard line | Presenter does not react; operator clears the box, refocuses, retries once; if it repeats, typed input | No wrong task started |
| D4 | Piper dies mid-sentence | Stop the Piper process | Operator sets `TTS_BACKEND=browser`, restarts, Console speaks; presenter keeps the beat | Audio back within 30 s |
| D5 | Backend crashes mid-Task B | Kill the backend process | One restart only; if state is lost, go to the video; presenter says so | No second restart; no lost safety state presented as success |
| D6 | Browser window closes or loses focus | Close the agent window, or click another app | Operator restores focus or restarts the browser once; Console still shows the log | Recovery within 20 s, or video |
| D7 | Agent stalls or loops on one step | Let a step run past 10 s | Presenter says "stop"; operator checks the log; one retry with a clearer instruction, or video | Stop within one step; no third attempt |
| D8 | Verifier misses the trap | Use a build or page where the truncation is not detected | Hard stop, no "confirm", no-go recorded, bug filed | The team does not submit and does not claim success |
| D9 | Irreversible action runs early | Use a page where "Place order" is not flagged | Hard stop, no-go, security bug, video only | No claim that the gate works |
| D10 | Sensitive value appears unmasked | Inspect the Console and the audit log | Hard stop, no-go, bug, video only | No screenshot or recording of the raw value is kept |
| D11 | Robot check is auto-clicked | Observe Task B | Hard stop, no-go, bug | The agent never touches the challenge |
| D12 | Projector or room audio fails | Unplug the projector audio | Presenter keeps talking; operator switches output; if not fixed in 30 s, video | Demo continues without dead air |

After every drill, the scribe writes: drill, time, what happened, who called the fallback, seconds to recover, and whether a hard rule was touched.

## 10. Backup video checklist

Record only in R2, only after a clean run, and only from the `demo-v1` build.

### Before recording

- [ ] The commit under test is the tagged `demo-v1` commit
- [ ] A full clean run just passed with no drills and no fallbacks
- [ ] Notifications off, phone silent, no chat windows, no personal tabs
- [ ] Console field table shows masked values only
- [ ] Profile values are fake; no real Aadhaar, bank account, phone or address
- [ ] Recording tool captures screen, system audio (agent voice) and microphone (presenter)
- [ ] Output folder is outside the repo, for example `D:\demo-assets\`
- [ ] Free disk space for at least three takes
- [ ] Timer visible in frame or not, decided in advance; do not show a timer reading 0:47 at the Close

### During recording

- [ ] Start recording before the hook's first word
- [ ] One continuous take of the full script, 3:00 to 3:10
- [ ] Agent audio is clearly audible over the presenter
- [ ] The Console is readable at 1080p
- [ ] No cursor parked over a sensitive row; no window switch to `.env`, chat or email
- [ ] Task B shows the trap alert and the correction
- [ ] Task C shows the pending action and no payment page
- [ ] The Close is complete; do not stop recording mid-sentence

### After recording

- [ ] Watch the full clip on the demo machine, full screen, with the room audio
- [ ] Check the first 5 seconds and the last 5 seconds
- [ ] Confirm no sensitive value, no personal data, no notification, no wrong build on screen
- [ ] Name it `voice-browser-demo-backup-YYYYMMDD-HHMM.mp4`
- [ ] Keep two copies: the demo laptop and a USB stick or a second machine
- [ ] Record the SHA-256 checksum in Section 11
- [ ] Test playback from the USB copy, offline, with the venue projector
- [ ] Do not commit it, do not put it in the repo, do not put it in a public drive
- [ ] Keep the raw takes outside the repo until the event is over, then delete the rejects

If the video is re-recorded after a demo-path fix, update the checksum and the date in Section 11. An old video of a different build is worse than no video, because it invites a false claim.

## 11. Evidence and sign-off

Fill this only after a real run. Leave blank until then.

### 11.1 Per-run record

| Field | Run 1 | Run 2 |
|---|---|---|
| Rehearsal (R1 or R2) | | |
| Date and start time | | |
| Commit and tag | | |
| Network name | | |
| Presenter / operator / timekeeper | | |
| Hook end | | |
| Task A answer | | |
| Task B trap caught | | |
| Task B robot resumed | | |
| Task B acknowledged | | |
| Task C held | | |
| Close end | | |
| Total time | | |
| Fallbacks used | | |
| Hard rule touched (yes/no) | | |
| Result (pass / fail) | | |
| Notes | | |

### 11.2 Sign-off

Status above this table: **BLOCKED until CORE-13 lands.** Do not write dates or results before the run happens.

| Item | Date | Result | Notes | Signed |
|---|---|---|---|---|
| Rehearsal 1, run 1 | | | | |
| Rehearsal 1, run 2 | | | | |
| Rehearsal 1 drills (at least four) | | | | |
| Rehearsal 1 go/no-go | | | | |
| Rehearsal 2, run 1 | | | | |
| Rehearsal 2, run 2 | | | | |
| Rehearsal 2 drills (at least four) | | | | |
| Backup video recorded | | | | |
| Backup video played from the USB copy, offline | | | | |
| Backup video SHA-256 | | | | |
| Final go/no-go | | | | |

## 12. After each rehearsal

1. Update [DEMO.md](DEMO.md) Section 10 with the real dates, results and measured timings. Replace the word "budget" with "measured" only where it was measured.
2. Add the measured latency median to the Q&A answer, with the machine name. If it was not measured, leave the answer without a number.
3. File a GitHub issue for every failure that needs code, with the ticket ID and the log excerpt, minus sensitive values.
4. If the failure is a hard-rule violation, label it `bug`, tell the lead immediately, and mark the demo no-go until it is fixed and re-rehearsed.
5. Do not change the demo path after the final go/no-go. If it changes, R2 is void and the video must be re-recorded.
6. Delete raw video takes that are not the chosen backup, and delete any screenshot containing an unmasked value.

## 13. Known gaps before R1

These are open dependencies, not excuses. They are listed so the rehearsal does not pretend to cover them.

| Gap | Why it matters | Owner | Needed by |
|---|---|---|---|
| CORE-13 not landed | No stable build to rehearse | M1 | Before R1 |
| `demo-v1` not tagged | The video cannot be tied to a build | M1 | Before R1 |
| BRW-01 trap recoverability unconfirmed | If the PIN field drops a digit on every fill, the correction fails and Task B cannot reach the acknowledgment in 70 s | M3 | Before R1 |
| Read-back length unconfirmed | A full 15-field read-back will not fit 70 s; the script reads the risk fields first and cuts Task C unless CORE-12 adds a compact mode | M1, M4 | Before R1 |
| UI-03 accessibility check not done | Q&A answer 7 must say "designed for, not yet audited" | M2 | Before the demo |
| Venue network not tested | Task A may have to run on the mock mirror | M3, M4 | R2 |
| Task D (Gmail) not tested | It is a stretch and is not claimed | M3, M4 | Only if claimed |
| Piper not proven on the demo machine | Browser speech fallback may be the live path | M2 | Before R1 |
| Jev backend not selected | Q&A must state the live `GATE_BACKEND` | M4 | Before R1 |
