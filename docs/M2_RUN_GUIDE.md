# M2 Run Guide (Windows 11)

This guide covers the Handy setup, React Bits Voice Console, and voice helpers. The ticket work is currently split across `ui/UI-01-handy-setup`, `ui/UI-02-console`, and `ui/UI-06-voice`. After those PRs are merged, the commands below can run from `main`. Before then, use the matching ticket branch; `tests/test_voice.py` is on `ui/UI-06-voice`.

## A. Prerequisites

- Windows 11.
- Python 3.11 or newer. This machine was checked with Python 3.11.9.
- Node.js and npm. The Console build was checked with Node.js 24.18.0 and npm 11.16.0.
- Git, PowerShell, an internet connection for package/model downloads, and a microphone for Handy.
- Python packages for the backend and tests are listed in `requirements.txt`: FastAPI, `uvicorn[standard]`, Playwright, OpenAI, cryptography, python-dotenv, httpx, pytest, and pytest-asyncio. Install them with `python -m pip install -r requirements.txt`.
- The Console's locked npm packages are installed from `client/package-lock.json` with `npm ci`: React 19.3.1, React DOM 19.3.1, and OGL 1.0.11 at runtime; Vite 7.3.7 and `@vitejs/plugin-react` 5.2.0 for development and builds.
- Piper is optional and is not in `requirements.txt`. Install it in the active virtual environment with `python -m pip install piper-tts sounddevice`.
- Handy is a separate application. On Windows, `winget install cjpais.Handy` is documented by the Handy project; releases are also available at [Handy releases](https://github.com/cjpais/Handy/releases).

## B. Run the Voice Console

Open PowerShell at the repository root. Install and start the frontend:

```powershell
Set-Location .\client
npm ci
$env:VITE_TTS_BACKEND = "browser"
npm run dev
```

Open **http://127.0.0.1:5173/console.dev.html**. Leave the Vite terminal running; press `Ctrl+C` there to stop it.

The browser speech backend is the default. For Piper, set `$env:VITE_TTS_BACKEND = "piper"` before starting Vite or building, and also set `TTS_BACKEND=piper` in the repository root `.env`. This prevents browser speech from duplicating Piper playback.

Build the production frontend from `client`:

```powershell
npm run build
```

This writes a self-contained production page to `client/console.html` for FastAPI's `/console` route, plus Vite preview assets under `client/dist/`. The Vite preview at **http://127.0.0.1:4173/console.dev.html** does not proxy WebSockets; use the development server for a proxied preview. For production integration, start FastAPI after the build and open **http://127.0.0.1:8080/console**. Stop Vite preview with `Ctrl+C`.

## C. Run the Python voice module and tests

From the repository root, create and activate a virtual environment and install the project requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell window, then activate again.

Run the voice module tests and the full Python suite:

```powershell
python -m pytest -q tests/test_voice.py
python -m pytest -q
```

The current voice module has no `python -m app.voice` command-line entry point. To try its text helpers directly:

```powershell
python -c "from app.voice import match_command, spoken_digits, words_to_digits; print(match_command('go back')); print(spoken_digits('9876')); print(words_to_digits('nine eight seven'))"
```

Expected output:

```text
back
9 8 7 6
987
```

To exercise Piper directly, install the optional packages, download a voice into a known folder, and point `PIPER_VOICE` at the `.onnx` file:

```powershell
python -m pip install piper-tts sounddevice
$piperDir = Join-Path $env:USERPROFILE "piper-voices"
New-Item -ItemType Directory -Force -Path $piperDir
Set-Location $piperDir
python -m piper.download_voices en_US-lessac-medium
```

The downloader puts `en_US-lessac-medium.onnx` and its `.onnx.json` sidecar in that folder. Return to the repository root. Copy the example only when `.env` does not already exist, then open it:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set these values in `.env`:

```text
TTS_BACKEND=piper
PIPER_VOICE=C:/Users/<your-user>/piper-voices/en_US-lessac-medium.onnx
```

Then run a short local playback check from the repository root:

```powershell
python -c "import asyncio; from app.voice import PiperTTS; asyncio.run(PiperTTS().speak('Piper playback check.'))"
```

Keep the backend's `TTS_BACKEND` and the Vite `VITE_TTS_BACKEND` setting in sync. The `piper-tts` and `sounddevice` packages and physical playback have not been verified on this machine.

## D. Backend routes and integration status

The FastAPI app has `GET /health`, `GET /console`, and `WS /ws/console`. Start it from a separate PowerShell window at the repository root, with the virtual environment active:

```powershell
python -m app.main
```

The backend listens on `http://127.0.0.1:8080` by default. Check **http://127.0.0.1:8080/health**. The route smoke test is `python -m pytest -q tests/test_smoke.py`. The production Console is served at **http://127.0.0.1:8080/console** and connects to `/ws/console` on the same origin. For frontend-only work, Vite's development URL is **http://127.0.0.1:5173/console.dev.html**; `client/vite.config.js` proxies its WebSocket to `ws://127.0.0.1:8080`.

The WebSocket route currently calls the CORE-10/11 stub in `app/agent.py`, which echoes `You said: ...` and returns `Stopped.` for Escape. This verifies the route and event plumbing, but it is not the autonomous browser agent. `npm run build` must be run before startup; FastAPI then serves the self-contained `client/console.html` at `/console`. The page receives Section 12 events over `/ws/console`; the real agent and command routing still depend on M1's CORE-10/11 integration.

## E. Handy input workflow

1. Install and start Handy. Allow microphone access in **Windows Settings → Privacy & security → Microphone** for microphone access, app access, and desktop-app access. Grant any additional OS input/accessibility permission if Handy requests it.
2. In Handy Settings, select/download a speech model and configure its hold-to-talk shortcut. Handy's model is for transcription; it is separate from the optional Piper output voice.
3. Start the backend and Vite development server as above. Open the Console URL and leave the Console input focused. The input is visually hidden and re-focuses itself after blur.
4. Hold Handy's shortcut while speaking, then release it. Handy transcribes locally and pastes the text into the focused Console input.
5. The Console sends the pasted text after 900 ms without more input, or immediately on Enter, as an `utterance` WebSocket event. The current backend stub echoes the text. No wake word is used.

Handy installation and physical microphone/headset behavior have not been tested on this host. If the Console loses focus, Handy can paste into the wrong application; always verify the target input before dictating sensitive text.

## F. Known limitations

- Piper playback has only been exercised with mocked output streams; this host has neither `piper` nor `sounddevice` installed, and physical playback is unverified.
- Handy is not installed on this host; microphone permissions, Handy model download, and headset capture/paste are unverified.
- The production page is self-contained and served by FastAPI at `/console`. The dev WebSocket proxy is configured and the FastAPI smoke test covers echo/stop events, but the agent handler remains a stub. Vite preview has no WebSocket proxy.
- React Bits TargetCursor and CursorGrid are included as source components. Live Playwright click highlighting is not connected because no browser target/coordinate event is available to the Console.
- The Console is a web page. An always-on-top desktop window and OS-level refocus helper are not implemented.
- CORE-14's OS startup-shortcut script is not present in the current default branch. Start the backend and Vite manually for this build.
- NVDA is not installed on this host; screen-reader verification remains a manual check.
- The Vite dev server must be run from `client`; the backend must be running at port 8080 for its WebSocket proxy to connect.

## G. Troubleshooting

- **PowerShell activation is blocked:** run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then run `& "$PWD\.venv\Scripts\Activate.ps1"` from the repository root.
- **Python or Node commands are missing:** install Python 3.11+ and Node.js/npm, reopen PowerShell, and check `python --version`, `node --version`, and `npm --version`.
- **Missing Python package:** activate `.venv`, then run `python -m pip install -r requirements.txt`. For Piper-only imports, install `piper-tts` and `sounddevice` separately.
- **Missing npm packages:** from `client`, run `npm ci`.
- **Port 5173 is busy:** stop the old Vite process with `Ctrl+C`; or start on another free frontend port with `npm run dev -- --port 5174`. Keep backend port 8080 available for the configured proxy.
- **Port 8080 is busy:** stop the existing backend process and restart it. The Vite WebSocket proxy is fixed to port 8080 in `client/vite.config.js`.
- **Console says reconnecting:** keep the backend running in its own terminal, use the Vite development URL (port 5173), and confirm `/health` responds on port 8080. The production preview does not currently proxy WebSockets.
- **Piper reports a missing model:** confirm `PIPER_VOICE` is the full path to the `.onnx` file and its downloaded `.onnx.json` sidecar is next to it.
- **Piper imports fail or audio is silent:** install `piper-tts` and `sounddevice` in the same virtual environment used by `python -m app.main`; verify the Windows default output device and the model path. Physical audio has not been tested here.
- **Handy paste goes elsewhere or is stale:** refocus the Console input before holding Handy's shortcut. See `SETUP.md` for Handy's paste troubleshooting and reliable-paste settings.

## H. UI-03 NVDA verification (Windows)

This host does not have NVDA installed, so these steps are instructions rather than a claimed test result. Install the current stable NVDA release from [NV Access](https://www.nvaccess.org/download/) or run `winget install --id NVAccess.NVDA`. Start NVDA from the Windows Start menu. The default NVDA modifier is `Insert`; NVDA can also be configured to use `Caps Lock`. The [NVDA User Guide](https://api.nvaccess.org/documentation/userGuide.html) documents these commands.

1. Build with browser speech enabled and start FastAPI using sections B and D. Open **http://127.0.0.1:8080/console** in Chrome or Edge.
2. On startup Handy has a focused paste target. Press `Tab` to move to the orb and verify its visible focus ring. Open Activity with `Alt+I`, then press `Tab` to reach the Activity Panel. The Console must not pull focus back to the input.
3. Press `Alt+T` from any Console control. The task input should become visible and focused. Type a harmless request such as `hello accessibility test`; inspect the text before the 900 ms debounce sends it. The visible input uses large, high-contrast text.
4. With BrowserTTS enabled, the response is spoken by browser speech and the agent-message log is not a live region. With BrowserTTS disabled, the agent-message log announces the response once. In either mode the status region announces state changes, not a duplicate copy of the response.
5. Press `Escape` while the input, orb, or Activity Panel has focus. NVDA should announce **Stopped.** and the Console should return to its ready state.
6. In Windows **Settings → Accessibility → Contrast themes**, apply a high-contrast theme and confirm the input, activity text, table borders, and keyboard focus indicators remain visible. Restore the previous theme after checking.

Record the NVDA version, browser, whether each announcement was heard once, any focus loss, and any contrast issue. A clean NVDA run is required before marking UI-03's screen-reader acceptance complete.

## I. First Handy voice check (safe stub)

This verifies Handy paste, Console transport, and speech output with the current backend stub. It does not exercise autonomous browser actions or spoken command routing.

1. Build the production Console with `$env:VITE_TTS_BACKEND = "browser"` and `npm run build` from `client`.
2. In a second PowerShell at the repository root, run `$env:TTS_BACKEND = "browser"` and `python -m app.main`. If port 8080 is occupied, set `$env:PORT = "8081"` before starting and use port 8081 below.
3. Open the matching FastAPI URL, `http://127.0.0.1:8080/console` (or `:8081/console`). Wait for the orb to indicate a connected Console.
4. Start Handy, select its configured hold-to-talk key, and speak `hello from Handy`. Release the key and keep the Console window in front.
5. Within about 900 ms, the Console should send the pasted transcript, show the answering state, and speak `You said: hello from Handy` through browser speech.
6. Press `Escape` on the keyboard. The stub should emit and speak `Stopped.`. Do not use personal data for this check.

For the first complete autonomous run, M1 must finish CORE-10/11 command routing and stop/interruption control. The current agent stub only echoes text. The production browser click overlay also needs a browser-side target interface from M3; no target event has been added to Section 12.

## J. Full mock-site rehearsal (after CORE-10/11 integration)

Use only the mock portal and its planted fake data. Do not enter real profile or banking information.

1. Build the production Console, start FastAPI, and start Handy as described above. Start the mock site in another PowerShell window from the repository root with `python -m http.server 8000 --directory .\mock_site`.
2. Start the integrated M1/M3 browser flow when CORE-10/11 is available. Open the agent browser on `http://127.0.0.1:8000/portal/apply.html` and keep the Console window available.
3. With Handy, speak a simple reversible instruction such as `read the heading on the demo portal`. Verify the Console receives the utterance, shows the agent state and step, and speaks the response.
4. During a longer response, speak a second harmless instruction. Verify the Console stops its current browser speech immediately and the backend begins the newer instruction.
5. Ask the agent to perform one reversible mock-site action and verify the page changed as requested.
6. Say `stop` during the task and verify the agent halts; also press `Escape` and verify the explicit Console stop key.
7. Record the Handy transcript, Console events, browser result, interruption result, and stop result. Repeat only with fake data.

As of this run, steps 1 and the Console/WebSocket echo path work. The current `app/agent.py` is still the CORE-10/11 echo stub, so steps 2–6 are a **not-yet-runnable procedure**, not a passing E2E result. M1 owns the missing command/task control path; M3 owns browser-side execution and focus. The separate M3 focus check is described in section K below.

## K. Observed milestone checks (2026-10-31)

- `npm run build` with `VITE_TTS_BACKEND=browser`: passed with Vite 7.3.7; 95 modules transformed. The FastAPI page is self-contained.
- `python -m pytest -q`: **394 passed, 1 skipped**, with one existing AnyIO/Pytest deprecation warning (68.18 s).
- `python -m compileall app tests`: passed.
- On `ui/UI-06-voice`, `python -m pytest -q tests/test_voice.py`: **22 passed**, with the same warning.
- Chromium/Playwright against the production FastAPI page: **passed**. Verified WebSocket connection, 900 ms debounce, Enter submission, `speak` event playback callback, speech cancellation when new input arrives, activity panel, and reconnect after a backend restart.
- A mock Section 12 WebSocket: **passed**. Verified `state`, `speak`, `step`, `field_table`, `pending`, `alert`, `input_mode`, plus Console `utterance` and Escape `key`; the sensitive input switched to password mode.
- `python -m pytest -q tests/test_console_accessibility.py`: **12 passed** against both BrowserTTS and Piper production builds served by FastAPI. Covered tab order, focus retention, transcript visibility before debounce, one response announcement per mode, semantic field-table headers, Escape, contrast, and forced colors.
- M3 `scripts/focus_test.py` in headed mode could not launch Chromium here (`BrowserType.launch: spawn UNKNOWN`). A headless run of the same five mock controls with `refocus_console()` passed **5/5 page-focus checks**. OS foreground focus remains unverified.
- NVDA and Handy were not available, and Piper/sounddevice/model playback was not available. Screen-reader, Handy/microphone, Piper audio, and OS-level window-focus checks remain manual. These results do not claim a hardware E2E pass.
