"""Page perception: compact snapshot and readable main text (PRD Section 12).

Owner: M3 (Sudeepti).

snapshot() tags every element it reports with a data-agent-id attribute and stores a CSS locator
string in session.locators[id]. Main-frame locators work directly with page.locator(); elements
inside iframes get "<iframe css> >>> <element css>", which locate() resolves via frame_locator.

Sensitive values (Aadhaar, bank, IFSC, passwords, card, OTP) are never returned (hard rule 4):
a filled sensitive field reports value "(filled)".
"""
import re
from urllib.parse import urlparse

MAX_ELEMENTS = 60
MAX_LABEL = 59          # labels stay under 60 characters
MAX_FRAMES = 5
FRAME_SEP = " >>> "
PREFIXES = ("f", "b", "l", "t")

# Irreversible controls (hard rule 2). BRW-08 extends this with target hints and full tests.
IRREVERSIBLE_KINDS = [
    ("pay", re.compile(r"\b(pay|payment|checkout now|buy|purchase|place (your )?order|confirm order|order now)\b", re.I)),
    ("send", re.compile(r"\bsend\b", re.I)),
    ("post", re.compile(r"\b(post|publish|tweet|share now)\b", re.I)),
    ("delete", re.compile(r"\b(delete|remove account|discard|trash|erase)\b", re.I)),
    ("accept", re.compile(r"\b(accept|agree|i agree|consent)\b", re.I)),
    ("submit", re.compile(r"\b(submit|apply now|finish|confirm|sign up|register)\b", re.I)),
]

# Runs in each frame. Collects visible interactive elements, tags them, returns raw entries.
SNAPSHOT_JS = r"""
({counts, budget, sensitiveRe}) => {
  const SENS = new RegExp(sensitiveRe, 'i');
  document.querySelectorAll('[data-agent-id]').forEach(e => e.removeAttribute('data-agent-id'));
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el.isConnected || el.closest('[hidden],[aria-hidden="true"],[inert]')) return false;
    if (el.checkVisibility && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const byIds = ids => clean((ids || '').split(/\s+/).map(i => {
    const n = i && document.getElementById(i); return n ? n.textContent : '';
  }).join(' '));
  const nearbyText = el => {
    let n = el.previousElementSibling;
    for (let i = 0; n && i < 3; i++, n = n.previousElementSibling) {
      if (n.matches('input,select,textarea,button') || n.querySelector('input,select,textarea,button')) continue;
      const t = clean(n.innerText); if (t) return t;
    }
    const p = el.parentElement;
    if (p) { const t = clean(Array.from(p.childNodes).filter(c => c.nodeType === 3).map(c => c.textContent).join(' ')); if (t) return t; }
    return '';
  };
  const fieldLabel = el => {
    if (el.labels && el.labels.length) {
      const t = clean(Array.from(el.labels).map(l => l.innerText).join(' ')); if (t) return t;
    }
    return byIds(el.getAttribute('aria-labelledby')) || clean(el.getAttribute('aria-label')) ||
      clean(el.getAttribute('placeholder')) || clean(el.getAttribute('title')) || nearbyText(el) ||
      clean(el.getAttribute('name')) || clean(el.id);
  };
  const controlText = el => byIds(el.getAttribute('aria-labelledby')) || clean(el.getAttribute('aria-label')) ||
    clean(el.innerText) || clean(el.value) || clean(el.getAttribute('title')) ||
    clean(Array.from(el.querySelectorAll('img[alt]')).map(i => i.alt).join(' ')) || clean(el.getAttribute('name')) || clean(el.id);
  const fieldError = el => {
    const parts = (el.getAttribute('aria-describedby') || '').split(/\s+/)
      .concat((el.getAttribute('aria-errormessage') || '').split(/\s+/))
      .map(i => i && document.getElementById(i)).filter(Boolean)
      .filter(n => /error|invalid/i.test(n.id + ' ' + n.className) || n.getAttribute('role') === 'alert')
      .map(n => clean(n.textContent)).filter(Boolean);
    if (parts.length) return parts.join(' ');
    return el.getAttribute('aria-invalid') === 'true' ? 'invalid' : null;
  };

  const fieldSel = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=image]):not([type=reset]),' +
    'textarea,select,[contenteditable=""],[contenteditable=true],[role=textbox],[role=combobox],[role=checkbox],[role=radio],[role=switch]';
  const buttonSel = 'button,input[type=submit],input[type=button],input[type=image],input[type=reset],[role=button],summary';
  const out = {fields: [], buttons: [], tabs: [], links: []};
  const seen = new Set();
  const take = (list, sel, make) => {
    for (const el of document.querySelectorAll(sel)) {
      if (budget <= 0) return;
      if (seen.has(el) || !visible(el)) continue;
      const entry = make(el);
      if (!entry) continue;
      seen.add(el);
      el.setAttribute('data-agent-id', entry.id);
      list.push(entry); budget--;
    }
  };
  const nextId = p => p + (++counts[p]);

  // Priority when the cap is hit: fields, buttons, tabs, links.
  take(out.fields, fieldSel, el => {
    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? (el.type || 'text') : tag === 'select' ? 'select' :
      tag === 'textarea' ? 'textarea' : (el.getAttribute('role') || 'text');
    const label = fieldLabel(el);
    const hint = [label, el.name, el.id, el.getAttribute('autocomplete')].join(' ');
    const sensitive = type === 'password' || SENS.test(hint);
    let value;
    if (type === 'checkbox' || type === 'radio') value = el.checked ? 'checked' : 'unchecked';
    else if (type === 'select') value = el.selectedIndex >= 0 && el.value ? clean(el.options[el.selectedIndex].text) : '';
    else value = 'value' in el ? el.value : clean(el.innerText);
    if (sensitive && value) value = '(filled)';
    const entry = {id: nextId('f'), label, type, required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      value, error: fieldError(el), sensitive_hint: sensitive};
    if (type === 'select') entry.options = Array.from(el.options).map(o => clean(o.text)).filter(Boolean).slice(0, 15);
    return entry;
  });
  take(out.buttons, buttonSel, el => {
    if (el.getAttribute('role') === 'tab') return null;
    const form = el.form || el.closest('form');
    const type = (el.getAttribute('type') || (el.tagName === 'BUTTON' && form ? 'submit' : 'button')).toLowerCase();
    return {id: nextId('b'), text: controlText(el), type,
            form_method: form ? (form.getAttribute('method') || 'get').toLowerCase() : null};
  });
  take(out.tabs, '[role=tab]', el => ({id: nextId('t'), text: controlText(el), selected: el.getAttribute('aria-selected') === 'true'}));
  take(out.links, 'a[href]', el => {
    const text = controlText(el);
    return text ? {id: nextId('l'), text, href: el.getAttribute('href') || '', new_tab: el.target === '_blank'} : null;
  });

  // h1 first (the page's main heading), then the rest in document order.
  const hs = Array.from(document.querySelectorAll('h1,h2,h3,[role=heading]')).filter(visible);
  const headings = hs.filter(h => h.tagName === 'H1').concat(hs.filter(h => h.tagName !== 'H1'))
    .map(h => clean(h.innerText)).filter(Boolean).slice(0, 10);
  const errors = Array.from(document.querySelectorAll('[role=alert]'))
    .filter(visible).map(n => clean(n.innerText)).filter(Boolean);
  return {out, counts, budget, headings, errors};
}
"""

# Runs in the main frame. Picks readable blocks, skipping navigation, menus, footers and banners.
MAIN_TEXT_JS = r"""
() => {
  const SKIP = 'nav,aside,form,script,style,noscript,template,svg,button,select,' +
    '[role=navigation],[role=banner],[role=contentinfo],[role=complementary],[role=search],[role=dialog],' +
    '[aria-hidden="true"],[hidden],.navbox,.mw-editsection,.reference,.reflist,.toc,#toc,.mw-jump-link,.catlinks,' +
    '[class*="cookie" i],[id*="cookie" i],[class*="sidebar" i],[class*="menu" i],[class*="breadcrumb" i],' +
    '[class*="share" i],[class*="advert" i],[class*="banner" i]';
  // Most specific article body first (Wikipedia, schema.org), then generic landmarks.
  const candidates = ['#mw-content-text .mw-parser-output', '[itemprop=articleBody]', 'article', 'main,[role=main]']
    .flatMap(sel => Array.from(document.querySelectorAll(sel)));
  const root = candidates.find(el => el.innerText.trim().length >= 200) || document.body;
  if (!root) return '';
  const h1 = document.querySelector('h1');
  const title = h1 && !root.contains(h1) ? h1.innerText.trim() : '';
  const blockOf = node => {
    let el = node.parentElement;
    while (el && el !== root && getComputedStyle(el).display.startsWith('inline')) el = el.parentElement;
    return el || root;
  };
  const taken = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => n.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT });
  const blocks = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const parent = n.parentElement;
    if (!parent || parent.closest(SKIP)) continue;
    // Page header/footer is chrome; a header inside the article (headline) is content.
    const hf = parent.closest('header,footer');
    if (hf && !(root.tagName === 'ARTICLE' && root.contains(hf))) continue;
    if (parent.checkVisibility && !parent.checkVisibility({checkVisibilityCSS: true})) continue;
    const block = blockOf(n);
    if (taken.some(t => t === block || t.contains(block))) continue;
    // Table rows read as "Header: value" (infoboxes).
    const row = block.closest('tr');
    const target = row && root.contains(row) ? row : block;
    if (taken.some(t => t === target || t.contains(target))) continue;
    taken.push(target);
    const text = target === row
      ? Array.from(row.cells).map(c => c.innerText.trim()).filter(Boolean).join(': ')
      : target.innerText;
    blocks.push(text);
  }
  const text = blocks.join('\n');
  // Pages that are mostly a form or app shell: fall back to the visible text of the root.
  const body = text.trim().length >= 80 ? text : root.innerText;
  return title ? title + '\n' + body : body;
}
"""

SENSITIVE_RE = (r"aadha+r|\buid\b|bank.?acc|account.?(no|num)|acc(ount)?.?number|ifsc|password|passcode|"
                r"\botp\b|one.?time|verification.?code|cvv|cvc|card.?num|cc-(number|csc|exp)|\bmpin\b|upi.?pin|"
                r"\bpin\b(?!.?code)")


def classify_button(text: str, btn_type: str = "button", form_method: str | None = None) -> tuple[bool, str]:
    """Return (irreversible, kind) for a button. kind is submit|pay|send|post|delete|accept|other."""
    for kind, pattern in IRREVERSIBLE_KINDS:
        if pattern.search(text or ""):
            return True, kind
    if btn_type == "submit" and form_method == "post":
        return True, "submit"   # a POST form submit changes server state whatever its label
    return False, "other"


def locate(page, session, element_id: str):
    """Playwright Locator for an id from the last snapshot (handles iframe locators)."""
    parts = session.locators[element_id].split(FRAME_SEP)
    if len(parts) == 1:
        return page.locator(parts[0])
    frame = page.frame_locator(parts[0])
    for sel in parts[1:-1]:
        frame = frame.frame_locator(sel)
    return frame.locator(parts[-1])


async def _frame_chain(frame, frame_ids: dict, counter: list) -> str | None:
    """CSS chain ("iframe[...] >>> iframe[...]") from the main frame to this frame."""
    if frame.parent_frame is None:
        return ""
    if frame in frame_ids:
        return frame_ids[frame]
    parent_chain = await _frame_chain(frame.parent_frame, frame_ids, counter)
    if parent_chain is None:
        return None
    try:
        handle = await frame.frame_element()
        counter[0] += 1
        n = counter[0]
        await handle.evaluate("(el, n) => el.setAttribute('data-agent-frame', String(n))", n)
    except Exception:
        return None
    own = f'[data-agent-frame="{n}"]'
    frame_ids[frame] = f"{parent_chain}{FRAME_SEP}{own}" if parent_chain else own
    return frame_ids[frame]


def _cut(text: str, limit: int = MAX_LABEL) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _summary(title: str, headings: list, fields: list, buttons: list, links: list, tabs: list,
             errors: list, lead: str) -> str:
    parts = [f'Page "{title}".' if title else "Untitled page."]
    if headings:
        parts.append(f'Main heading: "{headings[0]}".')
    if tabs:
        parts.append("Tabs: " + ", ".join(t["text"] + (" (selected)" if t["selected"] else "") for t in tabs) + ".")
    if fields:
        req = sum(f["required"] for f in fields)
        empty_req = sum(f["required"] and f["value"] in ("", "unchecked") for f in fields)
        bad = sum(bool(f["error"]) for f in fields)
        parts.append(f"A form with {len(fields)} fields ({req} required, {empty_req} required still empty"
                     + (f", {bad} with errors" if bad else "") + ").")
    risky = [b["text"] for b in buttons if b["irreversible"]]
    parts.append(f"{len(buttons)} buttons" + (f", irreversible: {', '.join(risky[:3])}" if risky else "")
                 + f"; {len(links)} links.")
    if errors:
        parts.append(f"Errors shown: {_cut(errors[0], 120)}")
    if lead:
        parts.append(f"Starts: {_cut(lead, 200)}")
    return re.sub(r"\s+", " ", " ".join(parts))


async def snapshot(page, session) -> dict:
    """Compact page state for the LLM. Fills session.locators[id]. Caps: 60 elements, labels < 60 chars.

    buttons[].kind is submit|pay|send|post|delete|accept|other.
    """
    counts = {p: 0 for p in PREFIXES}
    budget = MAX_ELEMENTS
    result = {"fields": [], "buttons": [], "tabs": [], "links": []}
    headings, errors, locators = [], [], {}
    frame_ids, frame_counter = {}, [0]

    frames = [page.main_frame] + [f for f in page.frames if f is not page.main_frame][:MAX_FRAMES]
    for frame in frames:
        if budget <= 0:
            break
        if frame.is_detached():
            continue
        chain = await _frame_chain(frame, frame_ids, frame_counter)
        if chain is None:
            continue
        try:
            raw = await frame.evaluate(SNAPSHOT_JS, {"counts": counts, "budget": budget, "sensitiveRe": SENSITIVE_RE})
        except Exception:
            continue    # frame navigated or was detached mid-snapshot
        counts, budget = raw["counts"], raw["budget"]
        headings += raw["headings"]
        errors += raw["errors"]
        for kind, entries in raw["out"].items():
            for e in entries:
                css = f'[data-agent-id="{e["id"]}"]'
                locators[e["id"]] = f"{chain}{FRAME_SEP}{css}" if chain else css
                result[kind].append(e)

    fields = [{"id": f["id"], "label": _cut(f["label"]), "type": f["type"], "required": f["required"],
               "value": _cut(f["value"], 200) if not f["sensitive_hint"] else f["value"],
               "error": _cut(f["error"], 120) if f["error"] else None, "sensitive_hint": f["sensitive_hint"],
               **({"options": [_cut(o) for o in f["options"]]} if "options" in f else {})}
              for f in result["fields"]]
    buttons = []
    for b in result["buttons"]:
        irreversible, kind = classify_button(b["text"], b["type"], b["form_method"])
        buttons.append({"id": b["id"], "text": _cut(b["text"]), "irreversible": irreversible, "kind": kind})
    links = [{"id": l["id"], "text": _cut(l["text"])} for l in result["links"]]
    tabs = [{"id": t["id"], "text": _cut(t["text"]), "selected": t["selected"]} for t in result["tabs"]]
    errors = list(dict.fromkeys(_cut(e, 200) for e in errors))
    headings = [_cut(h, 100) for h in dict.fromkeys(headings)]

    for key in [k for k in session.locators if k[:1] in PREFIXES and k[1:].isdigit()]:
        del session.locators[key]
    session.locators.update(locators)

    title = await page.title()
    try:
        lead = await main_text(page, max_chars=300)
    except Exception:
        lead = ""
    return {
        "page_title": title,
        "url": page.url,
        "domain": urlparse(page.url).hostname or "",
        "summary": _summary(title, headings, fields, buttons, links, tabs, errors, lead),
        "headings": headings,
        "fields": fields,
        "links": links,
        "tabs": tabs,
        "buttons": buttons,
        "errors": errors,
    }


async def main_text(page, max_chars: int = 4000) -> str:
    """Readable article text without menus, at most max_chars."""
    text = await page.main_frame.evaluate(MAIN_TEXT_JS)
    text = re.sub(r"\[(\d+|[a-z]|citation needed|edit)\]", "", text or "")   # footnote markers
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(" ")
    return (cut[:space] if space > max_chars * 0.8 else cut).rstrip() + "…"
