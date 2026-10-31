"""DOM verifier: expected vs actual page values (PRD Section 10). Owner: M4 (Abishek).

Reads the values that are actually on the page, normalises them by field type and
reports what is wrong. The returned records always carry masked values for sensitive
fields (hard rule 4), and `verify` never raises on a missing element or a broken page.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app import config

_MAX_TEXT = 300
_TRUTHY = frozenset({"true", "1", "yes", "y", "on", "checked", "t"})
_FALSY = frozenset({"false", "0", "no", "n", "off", "unchecked", "f", ""})
_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# --------------------------------------------------------------------------- helpers

def _text(value: Any) -> str:
    """A safe string for a value that may be None, a bool or a number."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _collapse(value: Any) -> str:
    return re.sub(r"\s+", " ", _text(value)).strip()


def _normalise_text(value: Any) -> str:
    """Casefold, collapse whitespace and drop a trailing full stop."""
    text = _collapse(value)
    text = re.sub(r"\s*\.+$", "", text)
    return text.casefold()


def _parse_date(value: Any) -> str | None:
    """Parse the date shapes a portal may show, day-first where ambiguous."""
    text = _collapse(value)
    if not text:
        return None
    parsed: tuple[int, int, int] | None = None
    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if match:
        parsed = int(match.group(1)), int(match.group(2)), int(match.group(3))
    else:
        match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
        if match:
            parsed = int(match.group(3)), int(match.group(2)), int(match.group(1))
        else:
            match = re.fullmatch(
                r"(\d{1,2})(?:st|nd|rd|th)?[\s-]+([A-Za-z]+)\.?,?[\s-]+(\d{4})", text
            )
            if match:
                month = _MONTHS.get(match.group(2).casefold())
                if month:
                    parsed = int(match.group(3)), month, int(match.group(1))
            else:
                match = re.fullmatch(
                    r"([A-Za-z]+)\.?[\s-]+(\d{1,2})(?:st|nd|rd|th)?,?[\s-]+(\d{4})", text
                )
                if match:
                    month = _MONTHS.get(match.group(1).casefold())
                    if month:
                        parsed = int(match.group(3)), month, int(match.group(2))
    if not parsed:
        return None
    try:
        return date(*parsed).isoformat()
    except ValueError:
        return None


def _phone_digits(value: Any) -> str:
    digits = re.sub(r"\D", "", _text(value))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def _decimal(value: Any) -> Decimal | None:
    text = _text(value)
    text = re.sub(
        r"(?i)(?<![a-z])(?:rs\.?|inr|usd|eur|gbp|rupees?)(?![a-z])", " ", text
    )
    text = re.sub(r"[,\s]", "", text)
    text = text.replace("₹", "").replace("$", "").replace("€", "").replace("£", "")
    text = text.replace("%", "")
    text = re.sub(r"/-$", "", text)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _truthy(value: Any) -> bool | None:
    text = _normalise_text(value)
    if text in _TRUTHY:
        return True
    if text in _FALSY:
        return False
    return None


def _semantic(expected: dict, meta: dict, label: str) -> str:
    """Pick the comparison rule from the profile key, label and DOM type, in that order."""
    kind = _text(expected.get("type")).strip().casefold()
    source = _text(expected.get("source")).strip().casefold()
    key = source.split(":", 1)[1].strip() if source.startswith("profile:") else ""
    label_low = _normalise_text(label)
    tag = _text(meta.get("tag")).casefold()
    input_type = _text(meta.get("type")).casefold()

    if key:
        if key in ("aadhaar",):
            return "aadhaar"
        if key in ("ifsc",):
            return "ifsc"
        if key in ("bank_account", "account_number"):
            return "bank_account"
        if key in ("pin_code", "pincode", "postal_code", "postal_pin"):
            return "pin_code"
        if key in ("dob", "date_of_birth"):
            return "date"
        if key in ("phone", "mobile"):
            return "phone"
        if key in ("annual_income", "disability_percent"):
            return "number"
        if key == "email":
            return "email"

    if "aadhaar" in label_low:
        return "aadhaar"
    if "ifsc" in label_low:
        return "ifsc"
    if "bank account" in label_low or "account number" in label_low:
        return "bank_account"
    if (
        "pin code" in label_low or "pincode" in label_low
        or "postal code" in label_low or "postal pin" in label_low
    ):
        return "pin_code"
    if "date of birth" in label_low or re.search(r"\bdob\b", label_low) \
            or "birth date" in label_low or "birthdate" in label_low \
            or label_low == "date":
        return "date"
    if "phone" in label_low or "mobile" in label_low or "telephone" in label_low:
        return "phone"
    if "income" in label_low or "amount" in label_low or "percent" in label_low:
        return "number"

    if kind in ("date", "dob") or input_type == "date":
        return "date"
    if kind in ("tel", "phone", "mobile") or input_type == "tel":
        return "phone"
    if kind in ("number", "amount", "currency") or input_type == "number":
        return "number"
    if kind in ("checkbox", "radio") or input_type in ("checkbox", "radio"):
        return "boolean"
    if kind in ("email",) or input_type == "email":
        return "email"
    if kind in ("ifsc",):
        return "ifsc"
    if kind in ("aadhaar",):
        return "aadhaar"
    if kind in ("pin_code", "pincode"):
        return "pin_code"
    if tag == "select" or kind in ("select", "dropdown", "option", "textarea",
                                   "contenteditable", "text"):
        return "text"
    return "text"


def _values_match(expected: Any, actual: Any, semantic: str) -> bool:
    if semantic == "date":
        left, right = _parse_date(expected), _parse_date(actual)
        if left and right:
            return left == right
        return _normalise_text(expected) == _normalise_text(actual)
    if semantic == "phone":
        left, right = _phone_digits(expected), _phone_digits(actual)
        if left and right:
            return left == right
        return _normalise_text(expected) == _normalise_text(actual)
    if semantic == "aadhaar":
        left, right = re.sub(r"\D", "", _text(expected)), re.sub(r"\D", "", _text(actual))
        return left == right
    if semantic == "ifsc":
        def clean(v: Any) -> str:
            return re.sub(r"[\s-]+", "", _text(v)).upper()
        return clean(expected) == clean(actual)
    if semantic == "bank_account":
        def clean(v: Any) -> str:
            return re.sub(r"[\s-]+", "", _text(v)).casefold()
        return clean(expected) == clean(actual)
    if semantic == "pin_code":
        def clean(v: Any) -> str:
            return re.sub(r"[\s-]+", "", _text(v)).casefold()
        return clean(expected) == clean(actual)
    if semantic == "number":
        left, right = _decimal(expected), _decimal(actual)
        if left is not None and right is not None:
            return left == right
        return _normalise_text(expected) == _normalise_text(actual)
    if semantic == "boolean":
        left, right = _truthy(expected), _truthy(actual)
        if left is not None and right is not None:
            return left == right
        return _normalise_text(expected) == _normalise_text(actual)
    return _normalise_text(expected) == _normalise_text(actual)


def _matches(expected: str, candidates: Iterable[str], semantic: str) -> bool:
    for candidate in candidates:
        if _values_match(expected, candidate, semantic):
            return True
    return False


def _is_sensitive(expected: dict | None, label: str) -> bool:
    """Hard rule 4: Aadhaar, bank account, IFSC and the unlock PIN are sensitive."""
    expected = expected or {}
    source = _text(expected.get("source")).strip().casefold()
    if source.startswith("profile:"):
        key = source.split(":", 1)[1].strip()
        if key in ("pin_code", "pincode", "postal_code", "postal_pin"):
            return False
        if key in config.SENSITIVE_KEYS:
            return True
    low = _normalise_text(label)
    if "aadhaar" in low or "bank account" in low or "account number" in low or "ifsc" in low:
        return True
    return False


def _mask(value: Any) -> str:
    """Last four characters only, e.g. "ending 9 0 1 2"."""
    compact = re.sub(r"[^0-9A-Za-z]", "", _text(value))
    if not compact:
        return ""
    return "ending " + " ".join(compact[-4:])


def _secret_variants(value: Any) -> set[str]:
    compact = re.sub(r"[^0-9A-Za-z]", "", _text(value))
    if not compact:
        return set()
    variants = {compact, compact.upper(), compact.lower()}
    groups = " ".join(re.findall(r".{1,4}", compact))
    variants.add(groups)
    variants.add(groups.replace(" ", "-"))
    return {v for v in variants if v}


def _scrub_message(value: Any, secrets: Iterable[str], sensitive: bool) -> str:
    text = _text(value)
    patterns = [re.escape(variant) for secret in secrets
                for variant in _secret_variants(secret) if variant]
    if sensitive:
        # Mask, in one pass, an IFSC or any run of four or more digits (a PIN,
        # Aadhaar, phone or account number), including spaced or hyphenated groups.
        patterns[:0] = [
            r"\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b",
            r"(?<!\d)(?:\d[\s-]?){3,}\d(?!\d)",
        ]
    if patterns:
        text = re.sub(
            "|".join(patterns),
            lambda match: _mask(match.group(0)),
            text,
            flags=re.IGNORECASE,
        )
    return text[:_MAX_TEXT]


def _split_selector(selector: str) -> tuple[str, str]:
    """M3 iframe locators: "iframe-css >>> element-css"."""
    if ">>>" in selector:
        frame_selector, inner = selector.split(">>>", 1)
        return frame_selector.strip(), inner.strip()
    return "", selector.strip()


def _locator(page, selector: str):
    frame_selector, inner = _split_selector(selector)
    if not inner:
        raise ValueError("empty selector")
    if frame_selector:
        return page.frame_locator(frame_selector).locator(inner)
    return page.locator(inner)


def _error_text(meta: dict, actual: str) -> str:
    """A visible validation message for this control, if any."""
    if not meta.get("visible", True):
        return ""
    own = _text(meta.get("ownError")).strip()
    if own:
        return own[:_MAX_TEXT]
    container = _text(meta.get("containerError")).strip()
    if container:
        return container[:_MAX_TEXT]
    message = _text(meta.get("validationMessage")).strip()
    if message:
        # The browser's default "please fill out" message on an empty required
        # control is the "missing" case, not a separate error.
        if actual.strip() or not meta.get("required"):
            return message[:_MAX_TEXT]
    return ""


# ----------------------------------------------------------------------------- DOM JS

_META_JS = """
el => {
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    if (typeof node.checkVisibility === "function") {
      try { return node.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); }
      catch (e) {}
    }
    const style = window.getComputedStyle(node);
    if (!style || style.display === "none" || style.visibility === "hidden"
        || style.visibility === "collapse" || style.opacity === "0") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || node.getClientRects().length > 0;
  };
  const textOf = (node) => {
    const raw = node ? (node.innerText || node.textContent || "") : "";
    return String(raw).replace(/\\s+/g, " ").trim().slice(0, 300);
  };
  const classesOf = (node) => {
    const raw = node && node.getAttribute ? (node.getAttribute("class") || "") : "";
    return raw.toLowerCase().split(/\\s+/).filter(Boolean);
  };
  const looksError = (node) => {
    const role = node && node.getAttribute
      ? (node.getAttribute("role") || "").toLowerCase() : "";
    if (role === "alert") return true;
    return classesOf(node).some((name) =>
      ["error", "errors", "field-error", "input-error", "form-error",
       "validation-error", "invalid", "is-invalid", "has-error", "help-error",
       "error-message", "error-text", "text-danger"].includes(name)
      || name.endsWith("-error") || name.endsWith("-invalid"));
  };
  const labelOf = (node) => {
    if (!node || !node.getAttribute) return "";
    let label = (node.getAttribute("aria-label") || "").trim();
    if (!label && node.id) {
      try {
        const escaped = window.CSS && CSS.escape ? CSS.escape(node.id) : node.id;
        const found = document.querySelector('label[for="' + escaped + '"]');
        if (found) label = textOf(found);
      } catch (e) {}
    }
    if (!label) {
      const wrapper = node.closest ? node.closest("label") : null;
      if (wrapper) label = textOf(wrapper);
    }
    if (!label) label = (node.getAttribute("placeholder") || "").trim();
    if (!label) label = (node.getAttribute("title") || "").trim();
    if (!label) label = (node.getAttribute("name") || "").trim();
    if (!label) label = node.id || "";
    return label.slice(0, 80);
  };

  const tag = (el.tagName || "").toLowerCase();
  const type = (tag === "input"
    ? (el.getAttribute("type") || "text")
    : (el.getAttribute("type") || "")).toLowerCase();
  const visible = isVisible(el);
  const ariaInvalid = (el.getAttribute("aria-invalid") || "").toLowerCase();

  let describedError = "";
  const describedIds = (el.getAttribute("aria-describedby") || "")
    .split(/\\s+/).filter(Boolean);
  for (const id of describedIds) {
    const node = document.getElementById(id);
    if (node && isVisible(node) && (looksError(node) || ariaInvalid === "true")) {
      describedError = textOf(node);
      if (describedError) break;
    }
  }

  let ownError = describedError;
  if (!ownError && ariaInvalid === "true") {
    ownError = "invalid value";
    let scope = el.closest("form") || el.ownerDocument;
    if (scope) {
      const nearby = scope.querySelectorAll(
        '[role="alert"], .error, .field-error, [class*="-error"], [class*="-invalid"]');
      for (const node of nearby) {
        if (node !== el && looksError(node) && isVisible(node)) {
          const found = textOf(node);
          if (found) { ownError = found; break; }
        }
      }
    }
  }

  let containerError = "";
  if (visible) {
    let parent = el.parentElement;
    let depth = 0;
    while (parent && depth < 4) {
      const nodes = parent.querySelectorAll(
        '[role="alert"], .error, .field-error, [class*="-error"], [class*="-invalid"]');
      for (const node of nodes) {
        if (node !== el && looksError(node) && isVisible(node)) {
          const found = textOf(node);
          if (found) { containerError = found; break; }
        }
      }
      if (containerError) break;
      if ((parent.tagName || "").toLowerCase() === "form") break;
      parent = parent.parentElement;
      depth += 1;
    }
  }

  let selectedText = "";
  let selectedValue = "";
  if (tag === "select" && el.selectedIndex >= 0 && el.options && el.options[el.selectedIndex]) {
    selectedText = textOf(el.options[el.selectedIndex]);
    selectedValue = String(el.options[el.selectedIndex].value || "").trim();
  }

  return {
    tag: tag,
    type: type,
    visible: visible,
    contenteditable: !!(el.isContentEditable
      || el.getAttribute("contenteditable") === "true"
      || el.getAttribute("contenteditable") === ""),
    checked: ("checked" in el) ? !!el.checked : null,
    value: ("value" in el) ? String(el.value == null ? "" : el.value) : "",
    text: textOf(el),
    selectedText: selectedText,
    selectedValue: selectedValue,
    ariaInvalid: ariaInvalid,
    validationMessage: (visible && el.validationMessage)
      ? String(el.validationMessage).slice(0, 300) : "",
    ownError: String(ownError || "").slice(0, 300),
    containerError: String(containerError || "").slice(0, 300),
    label: labelOf(el),
    required: !!el.required,
    disabled: !!el.disabled,
    readOnly: ("readOnly" in el) ? !!el.readOnly : false,
    id: el.id || "",
    name: (el.getAttribute && el.getAttribute("name")) || "",
    dataAgentId: (el.getAttribute && el.getAttribute("data-agent-id")) || ""
  };
}
"""

_ERROR_JS = """
el => {
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    if (typeof node.checkVisibility === "function") {
      try { return node.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); }
      catch (e) {}
    }
    const style = window.getComputedStyle(node);
    if (!style || style.display === "none" || style.visibility === "hidden"
        || style.visibility === "collapse" || style.opacity === "0") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || node.getClientRects().length > 0;
  };
  const textOf = (node) => {
    const raw = node ? (node.innerText || node.textContent || "") : "";
    return String(raw).replace(/\\s+/g, " ").trim().slice(0, 300);
  };
  const tag = (el.tagName || "").toLowerCase();
  const isField = (node) => node
    && /^(input|select|textarea)$/i.test(node.tagName || "");
  let field = null;
  if (isField(el)) {
    field = el;
  } else if (isField(el.previousElementSibling)) {
    field = el.previousElementSibling;
  } else {
    const container = el.closest(
      "form, fieldset, .field, .form-group, .form-field, .input-group, .form-control, td, li");
    if (container) field = container.querySelector("input, select, textarea");
  }
  const labelOf = (node) => {
    if (!node || !node.getAttribute) return "";
    let label = (node.getAttribute("aria-label") || "").trim();
    if (!label && node.id) {
      try {
        const escaped = window.CSS && CSS.escape ? CSS.escape(node.id) : node.id;
        const found = document.querySelector('label[for="' + escaped + '"]');
        if (found) label = textOf(found);
      } catch (e) {}
    }
    if (!label) {
      const wrapper = node.closest ? node.closest("label") : null;
      if (wrapper) label = textOf(wrapper);
    }
    if (!label) label = node.getAttribute("name") || node.id || "";
    return label.slice(0, 80);
  };
  const ownText = textOf(el);
  const invalid = isField(el)
    && (el.getAttribute("aria-invalid") || "").toLowerCase() === "true";
  return {
    text: ownText
      || (invalid ? (el.validationMessage || "invalid value") : ""),
    containsField: !isField(el) && !!el.querySelector
      && !!el.querySelector("input, select, textarea"),
    identifier: field
      ? String(field.getAttribute("data-agent-id")
          || field.getAttribute("name") || field.id || "").trim() : "",
    id: field ? (field.id || "") : "",
    name: field ? ((field.getAttribute && field.getAttribute("name")) || "") : "",
    dataAgentId: field
      ? ((field.getAttribute && field.getAttribute("data-agent-id")) || "") : "",
    label: labelOf(field)
  };
}
"""

_VALIDITY_JS = """
() => {
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    if (typeof node.checkVisibility === "function") {
      try { return node.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); }
      catch (e) {}
    }
    const style = window.getComputedStyle(node);
    if (!style || style.display === "none" || style.visibility === "hidden"
        || style.visibility === "collapse" || style.opacity === "0") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || node.getClientRects().length > 0;
  };
  const textOf = (node) => {
    const raw = node ? (node.innerText || node.textContent || "") : "";
    return String(raw).replace(/\\s+/g, " ").trim().slice(0, 300);
  };
  const labelOf = (node) => {
    if (!node || !node.getAttribute) return "";
    let label = (node.getAttribute("aria-label") || "").trim();
    if (!label && node.id) {
      try {
        const escaped = window.CSS && CSS.escape ? CSS.escape(node.id) : node.id;
        const found = document.querySelector('label[for="' + escaped + '"]');
        if (found) label = textOf(found);
      } catch (e) {}
    }
    if (!label) {
      const wrapper = node.closest ? node.closest("label") : null;
      if (wrapper) label = textOf(wrapper);
    }
    if (!label) label = (node.getAttribute("placeholder") || "").trim();
    if (!label) label = (node.getAttribute("title") || "").trim();
    if (!label) label = node.getAttribute("name") || node.id || "";
    return label.slice(0, 80);
  };
  const looksErrorText = (text) => {
    const low = String(text || "").toLowerCase();
    return ["error", "invalid", "incorrect", "not valid", "is required",
            "required field", "wrong", "failed", "cannot", "must not"]
      .some((word) => low.includes(word));
  };

  const results = [];
  for (const el of document.querySelectorAll("input, select, textarea")) {
    const nativeMessage = el.validationMessage
      ? String(el.validationMessage).slice(0, 300) : "";
    let message = nativeMessage;
    if (!message) {
      const ids = (el.getAttribute("aria-describedby") || "").split(/\\s+/).filter(Boolean);
      const ariaInvalid = (el.getAttribute("aria-invalid") || "").toLowerCase() === "true";
      for (const id of ids) {
        const node = document.getElementById(id);
        if (!node || !isVisible(node)) continue;
        const described = textOf(node);
        if (described && (ariaInvalid || looksErrorText(described))) {
          message = described;
          break;
        }
      }
    }
    if (!message) continue;
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || (tag === "input" ? "text" : "")).toLowerCase();
    if (type === "hidden" || el.disabled || el.readOnly) continue;
    if (!isVisible(el)) continue;
    // An empty required control is the "missing" case, not a separate error.
    if (type === "radio") {
      const name = el.getAttribute("name") || "";
      const group = name
        ? Array.from(document.querySelectorAll('input[type="radio"]'))
            .filter((node) => node.getAttribute("name") === name)
        : [el];
      if (group.some((node) => node.required) && !group.some((node) => node.checked)) continue;
      if (el.required && !el.checked) continue;
    }
    const emptyRequired = (type === "checkbox" || type === "radio")
      ? (el.required && !el.checked)
      : (el.required && !String(el.value == null ? "" : el.value).trim());
    if (emptyRequired) continue;
    results.push({
      message: message,
      id: el.id || "",
      name: (el.getAttribute("name") || ""),
      dataAgentId: (el.getAttribute("data-agent-id") || ""),
      label: labelOf(el)
    });
  }
  return results;
}
"""

_REQUIRED_JS = """
() => {
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    if (typeof node.checkVisibility === "function") {
      try { return node.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }); }
      catch (e) {}
    }
    const style = window.getComputedStyle(node);
    if (!style || style.display === "none" || style.visibility === "hidden"
        || style.visibility === "collapse" || style.opacity === "0") return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || node.getClientRects().length > 0;
  };
  const textOf = (node) => {
    const raw = node ? (node.innerText || node.textContent || "") : "";
    return String(raw).replace(/\\s+/g, " ").trim().slice(0, 300);
  };
  const labelOf = (node) => {
    if (!node || !node.getAttribute) return "";
    let label = (node.getAttribute("aria-label") || "").trim();
    if (!label && node.id) {
      try {
        const escaped = window.CSS && CSS.escape ? CSS.escape(node.id) : node.id;
        const found = document.querySelector('label[for="' + escaped + '"]');
        if (found) label = textOf(found);
      } catch (e) {}
    }
    if (!label) {
      const wrapper = node.closest ? node.closest("label") : null;
      if (wrapper) label = textOf(wrapper);
    }
    if (!label) label = (node.getAttribute("placeholder") || "").trim();
    if (!label) label = (node.getAttribute("title") || "").trim();
    if (!label) label = node.getAttribute("name") || node.id || "";
    return label.slice(0, 80);
  };

  const results = [];
  const seenRadioGroups = new Set();
  let index = 0;
  const nodes = document.querySelectorAll("input[required], select[required], textarea[required]");
  for (const el of nodes) {
    index += 1;
    const tag = (el.tagName || "").toLowerCase();
    const type = (el.getAttribute("type") || (tag === "input" ? "text" : "")).toLowerCase();
    if (type === "hidden" || el.disabled || el.readOnly) continue;
    if (!isVisible(el) || el.closest("[hidden]")) continue;

    const descriptor = {
      tag: tag,
      type: type,
      label: labelOf(el),
      id: el.id || "",
      name: (el.getAttribute("name") || ""),
      dataAgentId: (el.getAttribute("data-agent-id") || ""),
      selector: el.id
        ? ("#" + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id))
        : (el.getAttribute("name")
            ? (tag + '[name="' + el.getAttribute("name").replace(/"/g, '\\\\"') + '"]')
            : "")
    };

    if (type === "radio") {
      const groupName = el.getAttribute("name") || "";
      const key = groupName || ("radio-" + index);
      if (seenRadioGroups.has(key)) continue;
      seenRadioGroups.add(key);
      const group = groupName
        ? Array.from(document.querySelectorAll('input[type="radio"]'))
            .filter((node) => node.getAttribute("name") === groupName && !node.disabled)
        : [el];
      if (group.some((node) => node.checked)) continue;
      results.push(descriptor);
      continue;
    }

    let empty;
    if (tag === "select") {
      const option = el.selectedIndex >= 0 && el.options ? el.options[el.selectedIndex] : null;
      empty = !el.value
        || el.selectedIndex < 0
        || (option && String(option.value || "") === ""
            && String(option.text || "").trim() === "");
    } else if (type === "checkbox") {
      empty = !el.checked;
    } else {
      empty = String(el.value == null ? "" : el.value).trim() === "";
    }
    if (empty) results.push(descriptor);
  }
  return results;
}
"""


# ------------------------------------------------------------------------- reading

async def _read_actual(loc, meta: dict) -> tuple[str, list[str]]:
    tag = _text(meta.get("tag")).casefold()
    input_type = _text(meta.get("type")).casefold()
    if tag == "select":
        selected_text = _text(meta.get("selectedText"))
        selected_value = _text(meta.get("selectedValue"))
        candidates = [value for value in (selected_text, selected_value) if value.strip()]
        return selected_text or selected_value, candidates
    if input_type in ("checkbox", "radio"):
        try:
            checked = bool(await loc.is_checked())
        except Exception:
            checked = bool(meta.get("checked"))
        actual = "true" if checked else "false"
        if input_type == "radio":
            # A recorded radio may carry the chosen value ("Male") rather than "true".
            candidates = [actual]
            if checked:
                for value in (meta.get("value"), meta.get("label"),
                              "yes", "checked", "1"):
                    text = _text(value).strip()
                    if text:
                        candidates.append(text)
            else:
                candidates.extend(["no", "unchecked", "0"])
            return actual, candidates
        return actual, [actual]
    if meta.get("contenteditable") and tag not in ("input", "textarea"):
        try:
            value = await loc.inner_text()
        except Exception:
            value = _text(meta.get("text"))
        return _text(value), [_text(value)]
    if tag in ("input", "textarea"):
        try:
            value = _text(await loc.input_value())
            return value, [value]
        except Exception:
            pass
    try:
        value = _text(await loc.inner_text())
    except Exception:
        value = _text(meta.get("text"))
    return value, [value]


# ------------------------------------------------------------------------- scan parts

async def _check_expected(page, session, add, reported_ids: set[str]) -> None:
    expected_all = getattr(session, "expected", None)
    locators = getattr(session, "locators", None)
    if not isinstance(expected_all, dict):
        expected_all = {}
    if not isinstance(locators, dict):
        locators = {}

    for raw_id, raw_expected in expected_all.items():
        field_id = _text(raw_id)
        if isinstance(raw_expected, dict):
            expected = raw_expected
        else:
            expected = {"value": raw_expected}
        expected_value = _text(expected.get("value"))
        selector = (
            locators.get(raw_id) or locators.get(field_id)
            or expected.get("selector") or ""
        )
        if isinstance(selector, dict):
            selector = selector.get("selector") or selector.get("value") or ""
        selector = _text(selector).strip()
        label = _collapse(expected.get("label")) or field_id
        sensitive = _is_sensitive(expected, label)

        if not selector:
            add(field_id, label, expected_value, "", "missing", sensitive)
            continue

        count = 0
        try:
            loc = _locator(page, selector)
            count = await loc.count()
        except Exception:
            count = 0
        if not count:
            add(field_id, label, expected_value, "", "missing", sensitive)
            continue

        meta: dict = {}
        try:
            loc = loc.first
            meta = await loc.evaluate(_META_JS)
        except Exception:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        if not _collapse(expected.get("label")):
            label = _collapse(meta.get("label")) or field_id
            sensitive = _is_sensitive(expected, label)
        elif not sensitive:
            # A generic recorded label must not hide an Aadhaar/IFSC DOM label.
            sensitive = _is_sensitive(expected, _collapse(meta.get("label")))

        try:
            actual, candidates = await _read_actual(loc, meta)
        except Exception:
            actual, candidates = "", [""]

        semantic = _semantic(expected, meta, label)
        problem = None
        if not actual.strip():
            # Any recorded field that is empty on the page is missing, whether or
            # not the control also carries the HTML required attribute.
            problem = "missing"
        elif expected_value.strip():
            if not _matches(expected_value, candidates, semantic):
                problem = "mismatch"

        identifiers = {
            field_id,
            _text(meta.get("id")), _text(meta.get("name")), _text(meta.get("dataAgentId")),
        }
        identifiers.discard("")
        if problem:
            add(field_id, label, expected_value, actual, problem, sensitive, meta, identifiers)
        else:
            error = _error_text(meta, actual)
            if error:
                add(field_id, label, expected_value, error, "error", sensitive, meta,
                    identifiers)


async def _scan_validity(page, add, reported_ids: set[str]) -> None:
    for frame in _frames(page):
        try:
            items = await frame.evaluate(_VALIDITY_JS)
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            message = _collapse(item.get("message"))
            if not message:
                continue
            identifiers = {
                _text(item.get("dataAgentId")), _text(item.get("id")),
                _text(item.get("name")),
            }
            identifiers.discard("")
            if identifiers & reported_ids:
                continue
            field_id = (
                _text(item.get("dataAgentId")) or _text(item.get("name"))
                or _text(item.get("id")) or "page"
            )
            label = _collapse(item.get("label")) or field_id
            add(field_id, label, "", message, "error", _is_sensitive(None, label), None,
                identifiers)


async def _scan_errors(page, add, reported_ids: set[str]) -> None:
    selector = '[role="alert"], .error, .field-error, [aria-invalid="true"]'
    for frame in _frames(page):
        try:
            nodes = frame.locator(selector)
            count = await nodes.count()
        except Exception:
            continue
        for index in range(min(count, 25)):
            try:
                node = nodes.nth(index)
                if not await node.is_visible():
                    continue
                info = await node.evaluate(_ERROR_JS)
            except Exception:
                continue
            if not isinstance(info, dict):
                continue
            if info.get("containsField"):
                continue
            message = _collapse(info.get("text"))
            if not message:
                continue
            identifiers = {
                _text(info.get("dataAgentId")), _text(info.get("id")),
                _text(info.get("name")), _text(info.get("identifier")),
            }
            identifiers.discard("")
            if identifiers & reported_ids:
                continue
            field_id = (
                _text(info.get("identifier")) or _text(info.get("name"))
                or _text(info.get("id")) or "page"
            )
            label = _collapse(info.get("label")) or field_id
            add(field_id, label, "", message, "error", _is_sensitive(None, label), None,
                identifiers)


async def _scan_required(page, add, reported_ids: set[str]) -> None:
    for frame in _frames(page):
        try:
            items = await frame.evaluate(_REQUIRED_JS)
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            data_id = _text(item.get("dataAgentId")).strip()
            name = _text(item.get("name")).strip()
            element_id = _text(item.get("id")).strip()
            selector = _text(item.get("selector")).strip()
            identifiers = {data_id, name, element_id, selector}
            identifiers.discard("")
            if identifiers & reported_ids:
                continue
            field_id = data_id or name or element_id or selector or f"required_{index}"
            label = _collapse(item.get("label")) or field_id
            add(field_id, label, "", "", "missing", _is_sensitive(None, label), None,
                identifiers)


def _frames(page) -> list:
    try:
        frames = list(page.frames)
    except Exception:
        return []
    return frames


def _collect_secrets(expected_all: Any) -> list[str]:
    secrets: list[str] = []
    if not isinstance(expected_all, dict):
        return secrets
    for raw_expected in expected_all.values():
        if not isinstance(raw_expected, dict):
            continue
        label = _collapse(raw_expected.get("label"))
        if _is_sensitive(raw_expected, label):
            value = _text(raw_expected.get("value")).strip()
            if value:
                secrets.append(value)
    return secrets


# ----------------------------------------------------------------------------- public

async def verify(page, session) -> list[dict]:
    """Return problems: [{"field_id","label","expected","actual","kind"}].

    kind is "mismatch", "missing" or "error".
    """
    problems: list[dict] = []
    expected_all = getattr(session, "expected", None) or {}

    def add(field_id: str, label: str, expected_value: str, actual_value: str, kind: str,
            sensitive: bool = False, meta: dict | None = None,
            identifiers: Iterable[str] = ()) -> None:
        field_id = _collapse(field_id) or "page"
        label = _collapse(label) or field_id
        if kind == "error":
            expected_out = _mask(expected_value) if sensitive else _collapse(expected_value)
            actual_out = _scrub_message(actual_value, secrets, sensitive)
        else:
            expected_out = _mask(expected_value) if sensitive else _collapse(expected_value)
            actual_out = _mask(actual_value) if sensitive else _collapse(actual_value)
        actual_out = actual_out[:_MAX_TEXT]
        key = (field_id, kind, actual_out.casefold())
        if key in seen:
            return
        seen.add(key)
        record = {
            "field_id": field_id,
            "label": label,
            "expected": expected_out[:_MAX_TEXT],
            "actual": actual_out,
            "kind": kind,
        }
        problems.append(record)
        if meta:
            for value in (meta.get("id"), meta.get("name"), meta.get("dataAgentId")):
                text = _text(value).strip()
                if text:
                    reported_ids.add(text)
        for value in identifiers:
            text = _text(value).strip()
            if text:
                reported_ids.add(text)

    secrets = _collect_secrets(expected_all)
    reported_ids: set[str] = set()
    seen: set[tuple[str, str, str]] = set()

    try:
        await _check_expected(page, session, add, reported_ids)
        await _scan_validity(page, add, reported_ids)
        await _scan_errors(page, add, reported_ids)
        await _scan_required(page, add, reported_ids)
    except Exception:
        # A broken or half-loaded page must never take the agent loop down.
        pass
    return problems
