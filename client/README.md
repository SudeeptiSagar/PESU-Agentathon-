# PESU Agent Console

The Console is a minimal screen companion: the large React Bits Crystalized Ball is the only default visual. Its color reflects agent state. Click the orb or press `Alt+I` to reveal connection status, recent steps, transcript, masked fields, pending actions, and alerts. Pending actions and alerts open the activity panel automatically.

Handy pastes into a visually hidden, always-focused input. Text is sent after 900 ms or on Enter; Escape sends the stop key. `typed_secret` switches the input to password mode and transcript history stores only a redacted marker.

## Run locally

```bash
npm install
npm run dev
```

Vite serves `console.dev.html` and proxies `/ws/console` to FastAPI at `http://127.0.0.1:8080`. Run `npm run build` to create a self-contained production page at `client/console.html`; the FastAPI `/console` route serves that page directly. The `dist/` directory remains Vite's asset-based preview output.

The Console voices `speak` events with the browser's `speechSynthesis` by default. If the backend uses Piper, set `VITE_TTS_BACKEND=piper` in the environment used to run Vite or build the Console so browser audio does not duplicate Piper playback. New input and Escape cancel browser speech; Escape also sends the stop key.

For production, build before starting FastAPI so `client/console.html` contains the latest frontend. The page connects to `/ws/console` on the same origin. The FastAPI route does not need to serve Vite's `dist/assets/` directory.

## React Bits

React Bits Crystalized Ball is the active visual. Target Cursor and Cursor Grid are installed as editable sources under `src/components/`, but the Section 12 event contract has no live browser screenshot, target coordinates, or browser DOM reference. The Console does not fake click locations; wiring those effects to the real Playwright window needs a browser-target event from the browser/backend owners.
