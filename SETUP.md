# Handy setup for demo machines

Complete these steps on every machine that will run the voice demo. Handy transcribes locally and pastes into the focused text field.

## Install Handy

- On Windows, install from PowerShell with:

  ```powershell
  winget install --id cjpais.Handy --scope user --skip-dependencies --accept-package-agreements --accept-source-agreements
  ```

  Use `--skip-dependencies` because the standard winget command failed on a VulkanRT dependency-manifest resolution error. This skips winget's problematic dependency step while installing Handy itself.
- Verify that winget lists the installed package, then open **Handy** from the Windows Start menu. Confirm its window opens and its tray icon is available. If the window does not appear, check Task Manager for `handy.exe` and relaunch Handy from Start.
- On macOS, `brew install --cask handy` is available. On Debian or Ubuntu, install the downloaded `.deb` with `sudo apt install ./Handy_*.deb` so required dependencies are installed.
- Handy's project notes that its winget and Homebrew packages are maintained by third parties. The official release page is also available at [Handy releases](https://github.com/cjpais/Handy/releases).

## First launch, permissions, and model

1. Start Handy and complete its first-run GUI setup. Allow microphone access when Windows prompts. On macOS, allow microphone access and Accessibility when requested. If onboarding offers a model, choose one that supports the demo language and start its download.
2. If Windows does not show a permission prompt, open **Settings → Privacy & security → Microphone** and enable **Microphone access**, **Let apps access your microphone**, and **Let desktop apps access your microphone**. Restart Handy after changing a denied permission.
3. Open Handy **Settings → Models** if onboarding did not offer model selection. Download a speech model, wait until it shows **Downloaded**, select it, and test a short harmless phrase. Model files can be large; finish downloading before the demo.
4. If the model cannot download because of network restrictions, follow the [official manual model installation steps](https://github.com/cjpais/Handy#manual-model-installation-for-proxy-users-or-network-restrictions). Keep the model's original filename and restart Handy so it can detect the file.
5. Confirm a transcription appears in Handy. This checks its local model; still test paste into the Voice Console with the procedure below.

The Handy first-run screen and model list can vary by release. The official README's quick-start covers permissions and shortcuts, and its model section describes selecting and testing downloaded models: [Handy README](https://github.com/cjpais/Handy/blob/main/README.md).

## Set the in-app hold-to-talk shortcut

1. In Handy **Settings**, configure a hold-to-talk shortcut. Handy's README describes configuring shortcuts in Settings but does not prescribe a particular settings-page name.
2. Pick a key combination that does not conflict with the OS start shortcut or common app shortcuts. On macOS, avoid `fn`/Globe if using a non-Apple external keyboard; Handy documents that key as Apple-keyboard-only.
3. Hold the shortcut while speaking, then release it. Confirm the transcript is pasted into the focused Voice Console. Handy does not provide a spoken wake word in this workflow.

The project has a separate OS shortcut for starting the application (CORE-14). Handy's hold-to-talk shortcut is only used after the application is running.

## Fix stale or missing pastes

1. Focus the Voice Console's text box, open Handy's settings window, then open Handy's debug settings with `Cmd+Shift+D` on macOS or `Ctrl+Shift+D` on Windows/Linux.
2. On macOS or Windows, if a clipboard paste method is selected, try **Reliable Paste (Beta)** and test it in the Voice Console. Handy marks this feature experimental.
3. If Reliable Paste is unavailable or unreliable, disable it and test the standard paste path. Increase **Paste Delay (After)** a little at a time if the previous clipboard contents replace the transcript. **Paste Delay (Before)** delays the paste keystroke; **Paste Delay (After)** delays restoring the previous clipboard. These delay settings apply to the standard path, not Reliable Paste.
4. Retest after every change with harmless text and digits. Never use real profile data as a paste test. Record the Handy version, OS, paste method, Reliable Paste setting, and before/after delays if troubleshooting is still needed; redact dictated text from logs.

## Per-machine check before the demo

- [ ] `winget list --id cjpais.Handy` lists Handy, and the Start-menu app opens with its tray icon.
- [ ] Windows microphone access, app access, and desktop-app access are enabled.
- [ ] First-run setup is complete; a model is downloaded, selected, and transcribes a short phrase.
- [ ] Hold-to-talk starts recording while held and stops on release; the transcript appears in Handy.
- [ ] With the Voice Console input focused, repeat five harmless hold-to-talk attempts; each transcript is visible before it sends and lands in the Console without stale clipboard text.
- [ ] Repeat the 10-utterance focus gate in `docs/M2_RUN_GUIDE.md` when validating the Handy/Console handoff.
- [ ] The wired headset microphone and headphone output both work.

The Handy application, physical microphone, model download, transcription, and wired-headset steps have not been performed on this host. The checklist is a per-machine verification procedure, not a claimed pass.

## Build the Voice Console

FastAPI serves the Voice Console at `/console` from `client/dist`. Before starting the backend, install dependencies and build the frontend:

```powershell
cd client
npm ci
npm run build
cd ..
```

The build compiles the React application into:
- `client/dist/` (static assets and `console.html`)
- `client/console.html` (self-contained fallback page)

To run the application:
```powershell
python -m app.main
```
Then open `http://localhost:8080/console` (or `http://127.0.0.1:8080/console`).

## References

- [Handy README and troubleshooting](https://github.com/cjpais/Handy/blob/main/README.md)
- [Handy releases](https://github.com/cjpais/Handy/releases)
- [Microsoft: microphone permissions in Windows](https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows)
- [Apple: control microphone access on Mac](https://support.apple.com/en-us/guide/mac-help/mchla1b1e1fe/mac)
- [Apple: allow accessibility apps on Mac](https://support.apple.com/en-us/guide/mac-help/mh43185/mac)
