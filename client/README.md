# PESU Agent Console

The Console is a minimal screen companion: the large React Bits Crystalized Ball is the only default visual. Its color reflects agent state. Click the orb or press `Alt+I` to reveal connection status, recent steps, transcript, masked fields, pending actions, and alerts. Pending actions and alerts open the activity panel automatically.

Handy pastes into a visually hidden, always-focused input. Text is sent after 900 ms or on Enter; Escape sends the stop key. `typed_secret` switches the input to password mode and transcript history stores only a redacted marker.

## Run locally

```bash
npm install
npm run dev
```

Vite serves `console.html` and proxies `/ws/console` to the FastAPI service at `http://127.0.0.1:8080`. `npm run build` creates a production page and sibling assets under `dist/`.

The current FastAPI `/console` route returns `client/console.html` directly, while this Vite source page still needs Vite to transform JSX and serve its dependencies. Serving the production bundle through `/console` requires the backend to serve `dist/console.html` and `dist/assets/` together.

## React Bits

React Bits Crystalized Ball is the active visual. Target Cursor and Cursor Grid are installed as editable sources under `src/components/`, but the Section 12 event contract has no live browser screenshot, target coordinates, or browser DOM reference. The Console does not fake click locations; wiring those effects to the real Playwright window needs a browser-target event from the browser/backend owners.
