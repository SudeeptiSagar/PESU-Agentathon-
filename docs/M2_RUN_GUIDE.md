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
cd client
npm ci
npm run build
cd ..
```

This compiles the React application into `client/dist/` (served at `/console` and `/assets`) and writes `client/console.html` and `client/dist/console.html`. For production integration, start FastAPI after the build (`python -m app.main`) and open **http://127.0.0.1:8080/console**.

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
