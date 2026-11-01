# Start key

`scripts/start.ps1` starts the backend (if it is not already running) and shows the Voice Console: the floating orb when
`CONSOLE_MODE=overlay`, otherwise the Console page in the browser. Run it by hand, or bind it to a shortcut.

## Windows shortcut key
1. Right-click the desktop, New, Shortcut. Target:
   `powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\repo\scripts\start.ps1"`
2. Right-click the shortcut, Properties, put the cursor in "Shortcut key" and press the keys (for example Ctrl+Alt+V).
3. The shortcut must stay on the desktop or in the Start menu for the key to work.

## Overlay mode
Install the optional pieces once: `pip install -r requirements-overlay.txt`. Then set in `.env`:

    CONSOLE_MODE=overlay
    OVERLAY_TITLE=PESU Assistant

The overlay is an always-on-top window. Always-on-top is not keyboard focus: Windows decides who receives typing, so the
agent re-focuses the overlay (by its title) after it acts. The overlay speaks through Windows' own speech.
