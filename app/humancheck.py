"""Detects pages that need a human: CAPTCHA, OTP, password, payment (PRD Section 10).

Owner: M3 (Sudeepti). Hard rule 6: the agent never automates these. It pauses, tells the user
what is needed, waits for "done", then calls challenge_present() again: None means the
challenge is gone and the agent may resume.

When each challenge counts as gone:
  captcha   the check box is ticked / the CAPTCHA is solved, or no CAPTCHA is visible
  otp       every visible one-time-code field is filled, or none is visible
  payment   every visible card field is filled, or none is visible (the agent then reaches the
            held "Place order" button, which still needs "confirm")
  password  no password field or sign-in page is visible any more (the user finishes the login;
            a filled password does not count, so the agent never presses "Sign in")
"""
from urllib.parse import urlparse

HINTS = {
    "captcha": "There is a robot check on the page. Please complete it, then say done.",
    "otp": "The page is asking for a one-time code. Please type the code yourself, then say done.",
    "password": "The page is asking you to sign in. Please sign in yourself, then say done.",
    "payment": "The page is asking for payment details. Please enter them yourself, then say done.",
}
# Order matters: a checkout's CVV is a password-type input, so payment is checked before password.
ORDER = ("captcha", "otp", "payment", "password")

# Sign-in pages that are human-only by domain, even before a password field appears.
LOGIN_DOMAINS = ("accounts.google.com", "login.microsoftonline.com", "login.live.com", "appleid.apple.com")
CAPTCHA_FRAMES = ("recaptcha", "hcaptcha", "challenges.cloudflare.com", "turnstile", "arkoselabs", "funcaptcha")
PAYMENT_FRAMES = ("js.stripe.com", "checkout.razorpay.com", "api.razorpay.com", "securegw.paytm", "paypal.com/checkoutnow")

# Runs in each frame. Returns {kind: "pending" | "done"} for every challenge seen in that frame.
SCAN_JS = r"""
({captchaFrames, paymentFrames}) => {
  const visible = el => {
    if (!el.isConnected || el.closest('[hidden],[aria-hidden="true"],[inert]')) return false;
    if (el.checkVisibility && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const all = sel => Array.from(document.querySelectorAll(sel)).filter(visible);
  const filled = el => el.type === 'checkbox' || el.type === 'radio' ? el.checked : (el.value || '').trim() !== '';
  const describe = el => [el.name, el.id, el.getAttribute('autocomplete'), el.getAttribute('aria-label'),
    el.getAttribute('placeholder'), el.labels && Array.from(el.labels).map(l => l.innerText).join(' ')].join(' ');
  const state = els => els.length === 0 ? null : (els.every(filled) ? 'done' : 'pending');
  const out = {};
  const put = (kind, s) => { if (s && out[kind] !== 'pending') out[kind] = s; };
  const inputs = all('input:not([type=hidden]):not([type=submit]):not([type=button])');

  // CAPTCHA: our mock check, reCAPTCHA / hCaptcha / Turnstile widgets and their iframes.
  for (const box of all('[data-humancheck=captcha],.fake-captcha,.g-recaptcha,.h-captcha,.cf-turnstile')) {
    if (box.getAttribute('data-size') === 'invisible' || box.classList.contains('grecaptcha-badge')) continue;
    const check = box.querySelector('input[type=checkbox]');
    const token = box.querySelector('textarea[name$="-response"],input[name$="-response"]');
    put('captcha', check ? (check.checked ? 'done' : 'pending') : token ? (token.value ? 'done' : 'pending') : 'pending');
  }
  const capFrames = all('iframe').filter(f => captchaFrames.some(s => (f.src || '').includes(s)) &&
    !(f.src || '').includes('size=invisible') && f.getBoundingClientRect().width >= 60 && f.getBoundingClientRect().height >= 40);
  if (capFrames.length) {
    const token = document.querySelector('[name="g-recaptcha-response"],[name="h-captcha-response"],[name="cf-turnstile-response"]');
    put('captcha', token && token.value ? 'done' : 'pending');
  }

  // OTP: one-time-code fields, or fields named / labelled as OTP or verification code.
  const otpRe = /\botp\b|one[- ]?time|verification code|security code|passcode|2fa|two[- ]factor/i;
  put('otp', state(inputs.filter(el => el.getAttribute('autocomplete') === 'one-time-code' ||
    (otpRe.test(describe(el)) && !/cc-|cvv|cvc/i.test(describe(el))))));

  // Payment: our mock marker, card fields, or a payment provider's iframe.
  const cardRe = /cc-(number|exp|csc|name)|card.?(number|no)|cvv|cvc|expiry|expiration/i;
  const marked = all('[data-humancheck=payment]');
  const cardFields = inputs.filter(el => cardRe.test(describe(el)) || marked.some(m => m.contains(el)));
  put('payment', state(cardFields));
  if (!cardFields.length && marked.length) put('payment', 'pending');
  if (all('iframe').some(f => paymentFrames.some(s => (f.src || '').includes(s)))) put('payment', 'pending');

  // Password: any visible password field that is not a card's CVV. Filling it is not enough.
  if (inputs.some(el => el.type === 'password' && !cardRe.test(describe(el)))) put('password', 'pending');
  return out;
}
"""


async def challenge_present(page) -> dict | None:
    """Return {"kind": "captcha"|"otp"|"password"|"payment", "hint": str}, or None."""
    found: dict[str, str] = {}
    host = (urlparse(page.url).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in LOGIN_DOMAINS):
        found["password"] = "pending"

    for frame in page.frames:
        if frame.is_detached():
            continue
        url = frame.url.lower()
        if frame is not page.main_frame and any(s in url for s in CAPTCHA_FRAMES):
            # News and shop sites load invisible reCAPTCHA v3 / hidden challenge frames on every page.
            # Only a widget the user can actually see is a check to hand over (false-stall fix, issue #3).
            if await _frame_shown(frame, url):
                found.setdefault("captcha", "pending")   # cross-origin widget; solved state is read from the parent
            continue
        try:
            seen = await frame.evaluate(SCAN_JS, {"captchaFrames": list(CAPTCHA_FRAMES),
                                                  "paymentFrames": list(PAYMENT_FRAMES)})
        except Exception:
            continue   # frame navigated or detached mid-scan
        for kind, state in seen.items():
            if found.get(kind) != "pending":
                found[kind] = state

    # A solved reCAPTCHA keeps its iframe; the parent's response token decides.
    if found.get("captcha") == "pending" and await _captcha_token_set(page):
        found["captcha"] = "done"

    for kind in ORDER:
        if found.get(kind) == "pending":
            return {"kind": kind, "hint": HINTS[kind]}
    return None


async def _frame_shown(frame, url: str) -> bool:
    """True if a CAPTCHA iframe is on screen at a usable size (not invisible reCAPTCHA or a hidden bframe)."""
    if "size=invisible" in url:
        return False
    try:
        el = await frame.frame_element()
        if not await el.is_visible():
            return False
        box = await el.bounding_box()
        return bool(box and box["width"] >= 60 and box["height"] >= 40)
    except Exception:
        return False


async def _captcha_token_set(page) -> bool:
    try:
        return await page.main_frame.evaluate(
            """() => Array.from(document.querySelectorAll(
                 '[name="g-recaptcha-response"],[name="h-captcha-response"],[name="cf-turnstile-response"]'))
               .some(t => (t.value || '').trim() !== '')""")
    except Exception:
        return False
