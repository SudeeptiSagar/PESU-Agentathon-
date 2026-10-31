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

## When the browser cannot draw the orb

The orb is decoration and needs hardware WebGL. If the browser has none, or only software WebGL (SwiftShader, llvmpipe,
"Microsoft Basic Render Driver"), or the orb crashes while drawing, the Console shows a plain glowing circle in the same
state colour. The input box, speech, keys and activity panel never depend on the orb: Handy pastes into that input box.
`/console?orb=off` forces the plain circle and `/console?orb=on` forces the WebGL orb, which helps to tell an orb problem from an
input problem. `tests/test_console_webgl.py` covers all of this against the page the backend really serves.

After changing anything in `client/`, run `npm run build` and commit the rewritten `client/console.html`: the backend serves that
self-contained file, so a laptop without Node gets the latest Console too.

## React Bits

React Bits Crystalized Ball is the active visual. Target Cursor and Cursor Grid are installed as editable sources under `src/components/`, but the Section 12 event contract has no live browser screenshot, target coordinates, or browser DOM reference. The Console does not fake click locations; wiring those effects to the real Playwright window needs a browser-target event from the browser/backend owners.
