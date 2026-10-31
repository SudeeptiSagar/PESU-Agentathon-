// Mock disability pension form: tabs, validation, fake CAPTCHA and the planted PIN-code trap.
(function () {
  "use strict";

  var form = document.getElementById("application");
  var tabs = {
    personal: { tab: document.getElementById("tab-personal"), panel: document.getElementById("panel-personal") },
    bank: { tab: document.getElementById("tab-bank"), panel: document.getElementById("panel-bank") },
  };

  function showTab(name) {
    Object.keys(tabs).forEach(function (key) {
      var on = key === name;
      tabs[key].tab.setAttribute("aria-selected", on ? "true" : "false");
      tabs[key].tab.tabIndex = on ? 0 : -1;
      tabs[key].panel.hidden = !on;
    });
  }

  tabs.personal.tab.addEventListener("click", function () { showTab("personal"); });
  tabs.bank.tab.addEventListener("click", function () { showTab("bank"); });
  document.getElementById("next-bank").addEventListener("click", function () { showTab("bank"); tabs.bank.tab.focus(); });
  document.getElementById("back-personal").addEventListener("click", function () { showTab("personal"); tabs.personal.tab.focus(); });
  document.querySelector('[role="tablist"]').addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      var next = tabs.personal.tab.getAttribute("aria-selected") === "true" ? "bank" : "personal";
      showTab(next);
      tabs[next].tab.focus();
    }
  });

  // PLANTED TRAP (PRD BRW-01): the first time the PIN code reaches 6 digits, the page silently
  // drops the last digit a moment later. Later entries are kept, so the verifier can catch the
  // wrong value and the agent (or a human) can re-enter it and finish the form.
  var pin = document.getElementById("pin_code");
  var pinTrapFired = false;
  pin.addEventListener("input", function () {
    if (pinTrapFired || pin.value.replace(/\D/g, "").length !== 6) return;
    pinTrapFired = true;
    setTimeout(function () { pin.value = pin.value.slice(0, -1); }, 150);
  });

  // Aadhaar is displayed in groups of four ("1234 5678 9012"); validation uses the digits only.
  var aadhaar = document.getElementById("aadhaar");
  aadhaar.addEventListener("input", function () {
    var digits = aadhaar.value.replace(/\D/g, "").slice(0, 12);
    aadhaar.value = digits.replace(/(\d{4})(?=\d)/g, "$1 ");
  });

  var ifsc = document.getElementById("ifsc");
  ifsc.addEventListener("input", function () { ifsc.value = ifsc.value.toUpperCase(); });

  function digits(id) { return document.getElementById(id).value.replace(/\D/g, ""); }
  function value(id) { return document.getElementById(id).value.trim(); }

  // Each rule returns an error message, or "" when the field is valid.
  var rules = [
    ["full_name", "personal", function () { return value("full_name").length >= 2 ? "" : "Enter your full name."; }],
    ["dob", "personal", function () {
      var v = value("dob");
      if (!v) return "Enter your date of birth.";
      return new Date(v) < new Date() ? "" : "Date of birth must be in the past.";
    }],
    ["gender", "personal", function () { return value("gender") ? "" : "Select your gender."; }],
    ["phone", "personal", function () { return /^[6-9]\d{9}$/.test(value("phone")) ? "" : "Enter a 10-digit mobile number."; }],
    ["email", "personal", function () {
      var v = value("email");
      return !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? "" : "Enter a valid email address, or leave it blank.";
    }],
    ["address", "personal", function () { return value("address").length >= 5 ? "" : "Enter your address."; }],
    ["city", "personal", function () { return value("city").length >= 2 ? "" : "Enter your city."; }],
    ["state", "personal", function () { return value("state").length >= 2 ? "" : "Enter your state."; }],
    ["pin_code", "personal", function () { return /^[1-9]\d{5}$/.test(value("pin_code")) ? "" : "Enter a 6-digit PIN code."; }],
    ["aadhaar", "personal", function () {
      return digits("aadhaar").length === 12 && /^[\d ]+$/.test(value("aadhaar")) ? "" : "Enter a 12-digit Aadhaar number.";
    }],
    ["annual_income", "personal", function () {
      var v = value("annual_income");
      return v !== "" && Number(v) >= 0 ? "" : "Enter your annual family income in rupees.";
    }],
    ["category", "personal", function () { return value("category") ? "" : "Select a category."; }],
    ["disability_percent", "personal", function () {
      var v = value("disability_percent"), n = Number(v);
      if (v === "" || !Number.isInteger(n) || n < 0 || n > 100) return "Enter a disability percentage from 0 to 100.";
      return n >= 40 ? "" : "Disability must be 40 percent or more to apply.";
    }],
    ["bank_account", "bank", function () { return /^\d{9,18}$/.test(value("bank_account")) ? "" : "Enter a bank account number of 9 to 18 digits."; }],
    ["ifsc", "bank", function () { return /^[A-Z]{4}0[A-Z0-9]{6}$/.test(value("ifsc")) ? "" : "Enter a valid 11-character IFSC code."; }],
    ["not_robot", "bank", function () { return document.getElementById("not_robot").checked ? "" : "Tick \"I'm not a robot\" to continue."; }],
  ];

  function setError(id, message) {
    var el = document.getElementById(id);
    el.setAttribute("aria-invalid", message ? "true" : "false");
    document.getElementById(id + "-error").textContent = message;
  }

  // Re-check a field when the user leaves it, so stale errors clear.
  rules.forEach(function (rule) {
    document.getElementById(rule[0]).addEventListener("change", function () {
      if (document.getElementById(rule[0]).getAttribute("aria-invalid") === "true") setError(rule[0], rule[2]());
    });
  });

  var summary = document.getElementById("form-errors");
  var summaryList = document.getElementById("form-errors-list");

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var failed = [];
    rules.forEach(function (rule) {
      var message = rule[2]();
      setError(rule[0], message);
      if (message) failed.push({ id: rule[0], tab: rule[1], message: message });
    });

    summaryList.innerHTML = "";
    if (failed.length) {
      failed.forEach(function (f) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = "#" + f.id;
        a.textContent = f.message;
        a.addEventListener("click", function (ev) {
          ev.preventDefault();
          showTab(f.tab);
          document.getElementById(f.id).focus();
        });
        li.appendChild(a);
        summaryList.appendChild(li);
      });
      summary.hidden = false;
      showTab(failed[0].tab);
      summary.focus();
      return;
    }

    summary.hidden = true;
    var ack = "DPP-2026-" + String(Math.floor(100000 + Math.random() * 900000));
    // Only the acknowledgment number and the name travel to the next page; no sensitive values.
    location.href = "ack.html?ack=" + encodeURIComponent(ack) + "&name=" + encodeURIComponent(value("full_name"));
  });
})();
