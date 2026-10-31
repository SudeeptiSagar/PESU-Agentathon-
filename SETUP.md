# Handy setup for demo machines

Complete these steps on every machine that will run the voice demo. Handy transcribes locally and pastes into the focused text field.

## Install Handy

- Install the latest release from the [Handy releases page](https://github.com/cjpais/Handy/releases). On Windows, the project also documents `winget install cjpais.Handy`; on macOS, `brew install --cask handy` is available. These package-manager entries are maintained by third parties.
- On Debian or Ubuntu, install the downloaded `.deb` with `sudo apt install ./Handy_*.deb` so required dependencies are installed.
- Launch Handy. Allow microphone and accessibility permissions when the operating system asks. If a permission was denied earlier, re-enable it in the operating system's privacy settings and restart Handy. On Windows 11, microphone permissions are under **Settings → Privacy & security → Microphone**; enable microphone access, app access, and desktop-app access. On macOS, enable Handy under **System Settings → Privacy & Security → Microphone** and **Accessibility** when requested.
- Connect the wired headset before the test. Use its microphone (or the computer's built-in microphone) and headphones for playback. Handy's current README warns that Bluetooth headset microphones can reduce playback quality on macOS.

## Download and select a model

1. Open Handy's **Settings → Models**.
2. Download a speech model that supports the languages used in the demo. Wait for its status to show **Downloaded**, then select it and try a short transcription. Model downloads are large, so finish this on each machine before demo day.
3. If Handy cannot download a model because of network restrictions, follow the [official manual model installation steps](https://github.com/cjpais/Handy#manual-model-installation-for-proxy-users-or-network-restrictions). Keep the model's original filename, restart Handy, and confirm it appears as **Downloaded** under **Settings → Models**.

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

- [ ] Handy launches and microphone permission is enabled.
- [ ] A model is downloaded, selected, and transcribes a short phrase.
- [ ] Hold-to-talk starts and stops recording, and text lands in the Voice Console.
- [ ] Repeat five harmless paste attempts; each lands in the focused Console, with no stale clipboard text.
- [ ] Wired headset microphone and headphone output both work.

## References

- [Handy README and troubleshooting](https://github.com/cjpais/Handy/blob/main/README.md)
- [Handy releases](https://github.com/cjpais/Handy/releases)
- [Microsoft: microphone permissions in Windows](https://support.microsoft.com/en-us/windows/privacy/turn-on-app-permissions-for-your-microphone-in-windows)
- [Apple: control microphone access on Mac](https://support.apple.com/en-us/guide/mac-help/mchla1b1e1fe/mac)
- [Apple: allow accessibility apps on Mac](https://support.apple.com/en-us/guide/mac-help/mh43185/mac)
