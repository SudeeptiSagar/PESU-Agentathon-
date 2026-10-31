# Real-site notes (M3)

Findings from running the agent's browser against real sites. Owner: Sudeepti (M3).

## BRW-07 step 1: signed-in Chrome survives a restart (31 Oct 2026, 22:30 IST)

Script: `scripts/chrome_login_test.py`. It starts the installed Chrome as a normal process (not
through Playwright's launch) with `--remote-debugging-port=9222 --user-data-dir=<AGENT_PROFILE_DIR>
--no-first-run --no-default-browser-check`, attaches with Playwright's `connect_over_cdp`, lets the
user sign in to Gmail by hand, closes Chrome, starts it again with the same profile and checks
where Gmail lands. It prints only host names and yes/no checks, never page or email text.

| Item | Result |
|---|---|
| OS | Windows 11 (10.0.26300) |
| Chrome | 156.0.8078.76, `C:\Program Files\Google\Chrome\Application\chrome.exe` (auto-detected) |
| Remote debugging with the agent profile folder | Worked. `/json/version` answered on `http://127.0.0.1:9222` |
| Debug port bound to | `127.0.0.1:9222` only (checked with `netstat`) |
| Playwright `connect_over_cdp` | Worked; 1 browser context (the profile's default context) |
| Sign-in | By hand, in the agent Chrome window; the script typed nothing |
| Google warning ("This browser or app may not be secure") | None |
| After restarting Chrome with the same profile | Landed in the Gmail inbox. It held across two restarts in a row |
| **Result** | **PASS** |

Notes:
- Chrome 136 and later ignore `--remote-debugging-port` on the default profile: "These switches must
  now be accompanied by the `--user-data-dir` switch to point to a non-standard directory"
  ([Chrome blog](https://developer.chrome.com/blog/remote-debugging-port)). So the agent profile is
  a separate folder, `AGENT_PROFILE_DIR` (default `~/.voiceagent/chrome-profile`, outside the repo).
- Signed out, `mail.google.com` first shows the Gmail product page on `workspace.google.com`; the
  user may sign in from another tab. Code that waits for the inbox must look at every tab.
- Nothing hides the automation: no `--disable-blink-features=AutomationControlled`, no fake user
  agent, no `navigator.webdriver` changes.

## BRW-07 step 2: chrome mode (31 Oct 2026, 23:00 IST)

- `scripts/focus_test.py --mode chrome` with Chrome 156: **5/5**, against both the stand-in and the
  real backend Console. The Console is its own window of the same Chrome; the Windows foreground
  helper brings it forward.
- `close()` on a Chrome the agent started shuts it down via CDP `Browser.close` (cookies are
  saved) and keeps the profile folder; on a Chrome it attached to, only its own windows close.

## BRW-07 step 3: Task D on the real Gmail (31 Oct 2026, 23:20 IST)

Checked in the signed-in agent profile with the agent's own functions (`goto`, `snapshot`,
`locate(...).click()`, `main_text`), printing structure and yes/no checks only, never email text.

| Finding | What was done |
|---|---|
| Signed in, Gmail opens the inbox; `humancheck` stays silent on the inbox and on a message | nothing needed |
| Inbox rows have no `<a href>`: each row's clickable part is a `div[role=link]` | `snapshot` collects `[role=link]` as links |
| 50 row checkboxes are ARIA `role=checkbox` divs and filled the 60-element cap before any link | ARIA toggles now come after links; their state is read from `aria-checked` |
| 50 per-row "Not starred" buttons then filled the cap | a button text repeated on many rows is listed twice at most |
| Gmail renders after "load" | on `mail.google.com`, `snapshot` and `main_text` wait up to 10 s for inbox rows or a message |
| The generic reader started from `[role=main]` and hit the 4000-character cap before the body | a Gmail reader returns the subject, then each message newest first (From, Date, body) |
| On an open message, Delete and Unsubscribe are flagged irreversible (`delete`) | nothing needed |

Result: open inbox (15 row links in the snapshot, newest first), click the newest row, `main_text`
starts with the subject, has the sender and the full body, and no Gmail UI words.

## Search and site reachability (BRW-05, 31 Oct 2026, 21:55 IST)

Checked from this network with Playwright's Chromium.

| Site | Headless | Headed |
|---|---|---|
| en.wikipedia.org | 200 | 200 |
| www.thehindu.com | 200 | not needed |
| www.bbc.com/news | 200 | not needed |
| socialjustice.gov.in, www.mygov.in | 200 | not needed |
| www.india.gov.in, www.pmindia.gov.in | 403 "Access Denied", also with a desktop user agent | not checked |
| html.duckduckgo.com, lite.duckduckgo.com | 403, also with a desktop user agent | 200, 10 results |
| duckduckgo.com/?q= | redirects to an error page | 200, 20 results |
| www.bing.com/search?q= | not checked | 200, 10 results |
| mail.google.com (signed out) | redirects to accounts.google.com | same |

So the default `SEARCH_URL` (DuckDuckGo HTML) works for the agent, which runs headed, but headless
tests that hit real search are blocked; they should use the mock search.
