"""Why can't the Console get keyboard focus on this Windows laptop? (PRD 8.3, UI-04.) Owner: M1.

Handy pastes into whichever window has OS focus, so after the agent works the Console window must be
brought back to the front. Windows sometimes refuses ("foreground lock"). This script prints facts about the
machine, then tries each known way of taking the foreground and reports which ones work HERE.

    python scripts/focus_diag.py                 # strategies only, about 30 seconds, windows flash on screen
    python scripts/focus_diag.py --handy 5       # then 5 real rounds with your Handy hotkey (you speak)

Run it from the repo root with the venv active, on the laptop that will run the demo, and do not touch the
mouse or keyboard while the strategies run. Nothing here reads or prints page content or profile data.
"""
import argparse
import asyncio
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STAND_IN = ("<!doctype html><title>Voice Console (focus diag)</title><h1>Voice Console (focus diag)</h1>"
            "<textarea id=box rows=4 cols=50 autofocus></textarea>")
TRIES = 3
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x2
SW_MINIMIZE, SW_RESTORE = 6, 9


def setup_win32():
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.GetForegroundWindow.restype = wintypes.HWND
    u.SetForegroundWindow.argtypes = [wintypes.HWND]
    u.SetForegroundWindow.restype = wintypes.BOOL
    u.BringWindowToTop.argtypes = [wintypes.HWND]
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, wintypes.UINT]
    u.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    u.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    k.GetCurrentThreadId.restype = wintypes.DWORD
    k.OpenProcess.restype = wintypes.HANDLE
    return u, k


def window_title(u, hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    u.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def process_name(u, k, hwnd) -> str:
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = k.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return f"pid {pid.value} (no access)"
    try:
        size = wintypes.DWORD(520)
        buf = ctypes.create_unicode_buffer(520)
        if k.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name
        return f"pid {pid.value}"
    finally:
        k.CloseHandle(handle)


def find_window(u, title_part: str):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if u.IsWindowVisible(hwnd) and title_part in window_title(u, hwnd):
            found.append(hwnd)
            return False
        return True
    u.EnumWindows(visit, 0)
    return found[0] if found else None


def foreground(u, k) -> tuple[str, str]:
    hwnd = u.GetForegroundWindow()
    return (window_title(u, hwnd) if hwnd else "", process_name(u, k, hwnd) if hwnd else "")


def report_environment(u, k) -> None:
    import platform
    timeout = wintypes.DWORD()
    u.SystemParametersInfoW(0x2000, 0, ctypes.byref(timeout), 0)    # SPI_GETFOREGROUNDLOCKTIMEOUT
    title, proc = foreground(u, k)
    print("== This machine")
    print(f"Windows: {platform.platform()}")
    print(f"Running as administrator: {bool(ctypes.windll.shell32.IsUserAnAdmin())}")
    print(f"Remote desktop session: {bool(u.GetSystemMetrics(0x1000))}")
    print(f"Foreground lock timeout: {timeout.value} ms (0 means Windows lets programs take focus freely)")
    print(f"Foreground window right now: {proc} ({title[:50]!r})  <- the terminal you ran this in")
    print()


# ---------------------------------------------------------------- strategies: each takes (u, k, hwnd) and tries to foreground it
def _restore(u, hwnd):
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)


def _alt_key(u):
    ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
    ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def s_attach_thread(u, k, hwnd):
    """What app/browser.py does today."""
    fg = u.GetForegroundWindow()
    fg_thread = u.GetWindowThreadProcessId(fg, None) if fg else 0
    me = k.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and u.AttachThreadInput(me, fg_thread, True))
    try:
        _restore(u, hwnd)
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(me, fg_thread, False)


def s_alt_key(u, k, hwnd):
    _alt_key(u)
    _restore(u, hwnd)
    u.SetForegroundWindow(hwnd)


def s_attach_and_alt(u, k, hwnd):
    _alt_key(u)
    s_attach_thread(u, k, hwnd)


def s_allow_any(u, k, hwnd):
    u.AllowSetForegroundWindow(0xFFFFFFFF)                       # ASFW_ANY
    _restore(u, hwnd)
    u.SetForegroundWindow(hwnd)


def s_topmost_toggle(u, k, hwnd):
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    u.SetForegroundWindow(hwnd)


def s_switch_to_this_window(u, k, hwnd):
    u.SwitchToThisWindow(hwnd, True)


def s_minimize_restore(u, k, hwnd):
    u.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(0.15)
    u.ShowWindow(hwnd, SW_RESTORE)
    u.SetForegroundWindow(hwnd)


def s_alt_then_topmost(u, k, hwnd):
    _alt_key(u)
    s_topmost_toggle(u, k, hwnd)
    u.SwitchToThisWindow(hwnd, True)


STRATEGIES = [
    ("attach-thread (today's code)", s_attach_thread),
    ("alt-key then SetForegroundWindow", s_alt_key),
    ("alt-key + attach-thread", s_attach_and_alt),
    ("AllowSetForegroundWindow(any)", s_allow_any),
    ("topmost toggle", s_topmost_toggle),
    ("SwitchToThisWindow", s_switch_to_this_window),
    ("minimize + restore", s_minimize_restore),
    ("alt-key + topmost + SwitchToThisWindow", s_alt_then_topmost),
]


async def main(handy_rounds: int) -> int:
    if sys.platform != "win32":
        print("This diagnostic is for Windows only.")
        return 2
    from app.browser import BrowserController

    u, k = setup_win32()
    report_environment(u, k)
    browser = BrowserController(console_url="data:text/html," + STAND_IN, mode="chromium")
    await browser.start()
    try:
        await browser.goto("about:blank")
        await browser.active.set_content("<title>Agent window (focus diag)</title><h1>Agent window</h1>")
        await asyncio.sleep(1.0)
        console_title = await browser.console_page.title()
        agent_title = await browser.active.title()
        console, agent = find_window(u, console_title), find_window(u, agent_title)
        print(f"Found the Console window: {bool(console)}; the agent window: {bool(agent)}")
        if not (console and agent):
            print("Could not find the browser windows by title, so nothing below is meaningful.")
            return 2

        print(f"\n== Strategies ({TRIES} tries each; the agent window is put in front first)")
        print(f"{'strategy':44} {'agent first':>12} {'Console after':>14}")
        best = []
        for name, strategy in STRATEGIES:
            agent_ok = console_ok = 0
            for _ in range(TRIES):
                try:
                    s_alt_then_topmost(u, k, agent)                     # move focus away with the strongest method
                except Exception:
                    pass
                await asyncio.sleep(0.4)
                agent_ok += agent_title in foreground(u, k)[0]
                try:
                    strategy(u, k, console)
                except Exception as e:
                    print(f"   ({name} raised {type(e).__name__})")
                await asyncio.sleep(0.4)
                console_ok += console_title in foreground(u, k)[0]
            print(f"{name:44} {f'{agent_ok}/{TRIES}':>12} {f'{console_ok}/{TRIES}':>14}")
            if console_ok == TRIES and agent_ok == TRIES:
                best.append(name)

        print()
        if best:
            print("RESULT: these strategies take the focus back every time on this laptop:")
            for name in best:
                print("   -", name)
            print("Send this whole output to Prashanth; the browser code can use the first one that works.")
        elif any(True for _ in STRATEGIES):
            print("RESULT: no strategy worked every time with the agent window in front first. Look at the 'agent first'")
            print("column: if it is also below 3/3, Windows is blocking every programmatic focus change on this laptop")
            print("(try closing other windows, turning Focus assist off, and running this from a normal, non-admin terminal).")

        if handy_rounds:
            await handy_test(u, k, browser, console_title, handy_rounds)
        return 0 if best else 1
    finally:
        await browser.close()


async def handy_test(u, k, browser, console_title: str, rounds: int) -> None:
    sentences = ["nine eight seven six five four three two one zero", "open my gmail and read my last mail",
                 "Dr APJ Abdul Kalam", "stop", "confirm"]
    print(f"\n== Real Handy test: {rounds} rounds. Each round the agent window takes the focus, the code brings the Console")
    print("back (the real browser.refocus_console), then YOU hold your Handy key, say the sentence, and release.")
    arrived = 0
    for n in range(1, rounds + 1):
        sentence = sentences[(n - 1) % len(sentences)]
        await browser.console_page.evaluate("document.getElementById('box').value = ''")
        await browser.active.bring_to_front()
        await asyncio.sleep(0.5)
        await browser.refocus_console()
        await asyncio.sleep(0.4)
        fg_title, fg_proc = foreground(u, k)
        print(f"\nRound {n}/{rounds}. Console in front: {console_title in fg_title} (front window: {fg_proc}).")
        print(f"   SAY: {sentence!r}   (you have 12 seconds)")
        await asyncio.sleep(12)
        got = await browser.console_page.evaluate("document.getElementById('box').value")
        words = got.lower().split()
        ok = bool(got.strip()) and (sentence.split()[0].lower() in words or sentence.lower() in got.lower())
        arrived += ok
        print(f"   ARRIVED in the Console: {got!r}  -> {'OK' if ok else 'MISSING OR WRONG'}")
    print(f"\nHandy result: {arrived}/{rounds} rounds arrived in the Console (target: 9 of 10 with focus held).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--handy", type=int, default=0, metavar="N", help="then run N real rounds with your Handy hotkey")
    sys.exit(asyncio.run(main(ap.parse_args().handy)))
