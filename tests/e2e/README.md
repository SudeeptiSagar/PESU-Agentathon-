# JEV-07 end-to-end tests

Scripted typed runs of demo tasks A, B and C over the real `/ws/console` WebSocket, plus
the safety-chain checks for the verifier, gate, read-back and audit log.

The tests are honest about the current build. CORE-11 (`app/agent.py` integration) is
still a stub, so the three demo scenarios report **BLOCKED** with the exact stub names.
Nothing here turns stub behaviour into a pass.

## What is here

| File | Purpose |
|---|---|
| `harness.py` | In-process uvicorn on a random port, async Console client, scripted fake LLM, fixture server, stub detector, safety assertions, redacted event dumps |
| `scenarios.py` | Shared A/B/C scenario functions used by both pytest and the CLI |
| `test_safety_chain.py` | Real Playwright `page.set_content` checks, plus verifier, gate, read-back and audit checks |
| `test_demo_a.py` | Task A: mock search, article, answer contains Karnal, step events |
| `test_demo_b.py` | Task B: portal fill, truncated PIN caught, human check, read-back, confirm, acknowledgment |
| `test_demo_c.py` | Task C: add to cart, held Place order with total, no order before confirm, payment hand-off |
| `run_demo.py` | `A/B/C: PASS/FAIL/BLOCKED` and `RESULT`; exits 0 only when all three pass |
| `fixtures/` | Self-contained pages served on a random localhost port |

The fixture pages do not depend on `mock_site/` or the network:

| Page | What it does |
|---|---|
| `search.html?q=...` | Search results with a Kalpana Chawla article link |
| `article.html` | Article text with "born in Karnal" |
| `portal.html` | Name, DOB, PIN code, Aadhaar, submit. JavaScript drops the last PIN digit once, on the first six-digit entry. Fake robot checkbox clears only after a simulated human mark |
| `shop.html` | Add to cart, total 249, Place order, payment section with card fields |
| `inbox.html`, `message.html` | Task D mock inbox and newest message, including an instruction-injection sentence |

## Dependency matrix

The stub detector uses `inspect.getsource` and looks for `STUB:`. A dependency is
satisfied only when the real implementation replaces the marker. Partial stub behaviour
is never accepted.

| Area | Contract members | Ticket | Needed by |
|---|---|---|---|
| Agent loop | `agent.handle_utterance`, `agent.run_task` | CORE-10, CORE-11 | A, B, C |
| Tools | `tools.ToolExecutor.run`, `tools.commit_pending` | CORE-08, CORE-12 | A, B, C |
| Browser | `browser.BrowserController.start`, `.goto` | BRW-02 | A, B, C |
| Perception | `perception.snapshot`, `.main_text` | BRW-03 | A, B, C |
| Human check | `humancheck.challenge_present` | BRW-04 | B, C |
| Gate | `gate.check` | JEV-04, JEV-05 | B, C |
| Verifier | `verifier.verify` | JEV-02 | B |
| Read-back | `readback.build_readback`, `.describe_pending` | JEV-03 | B, C |
| Audit | `audit.log_event` | JEV-06 | safety chain |

Current state: every row above is still a CORE-01 stub, so A, B and C are BLOCKED.
The safety-chain fixture, Console transport and event-guard tests run now; the verifier,
gate, read-back and audit checks skip with the same stub names.

## Run

From the repository root:

```bash
python -m pip install pytest-asyncio
python -m playwright install chromium

python -m pytest tests/e2e/test_safety_chain.py -q
python -m pytest tests/e2e -q
python -m tests.e2e.run_demo
python -m pytest tests/test_smoke.py -q
```

`pytest.ini` already sets `asyncio_mode = auto`, so the async tests need no plugin flag.
The harness starts and stops its own FastAPI server, so port 8080 does not need to be free
or running. The fixture server picks its own free port.

## How to flip BLOCKED to PASS

The skip reason names the exact source member. Replace the stub body, keep the Section 12
signature, and rerun. The detector clears as soon as `inspect.getsource` no longer sees
`STUB:` for that member.

One-line unblock per scenario:

- **A:** land CORE-11's real `agent.handle_utterance` / `run_task` plus CORE-08's
  `ToolExecutor.run`, BRW-02's `BrowserController.start/goto`, and BRW-03's
  `perception.snapshot/main_text`.
- **B:** A plus JEV-02 `verifier.verify`, JEV-03 read-back, JEV-04/05 `gate.check`,
  BRW-04 `humancheck.challenge_present`, and CORE-12 `commit_pending`.
- **C:** B's gate, read-back and human check plus CORE-12 `commit_pending`; the pending
  description must include the total 249.

When CORE-11 lands, run `python -m tests.e2e.run_demo` first. It prints the failing
assertion with a redacted Console event log and the scripted LLM calls, so the first
mismatch is easy to locate.

## What each demo asserts

**A:**
- `web_search` and article navigation produce `step` events with `n`, `action`, `result`.
- The spoken answer contains "Karnal".
- The task reaches `DONE`.
- No error alert and no raw sensitive value in any Console event.

**B:**
- The first click on Submit is held; the portal server records zero submissions.
- A spoken or step-level signal reports the truncated PIN code (`56000` instead of
  `560001`).
- The agent pauses for the fake robot check; the test marks the human step done, sends
  `done`, and the agent resumes.
- `pending` names the submit action.
- Read-back masks Aadhaar (last four only), leaves the non-sensitive PIN code unmasked,
  and ends with exactly:
  `Say confirm to go ahead, or say change followed by the field name.`
- No submission happens before `confirm`.
- `confirm` commits exactly once and the acknowledgment number is spoken.

**C:**
- `pending` names Place order and includes total 249.
- The shop server records zero orders before `confirm`.
- After `confirm`, exactly one order is recorded.
- The agent hands off at payment and never types card, CVV or expiry values.

Every scenario also asserts that no raw Aadhaar, bank account or IFSC value appears in
Console events or in the scripted LLM prompts (hard rules 1 and 4). Failure dumps are
redacted before printing, so a bug cannot leak a sensitive value into CI output.

## Harness notes

- **Fake LLM:** `fake_llm()` replaces `app.llm.llm` and any imported copy in
  `app.agent`. Calls without tools are treated as planning or answer calls and do not
  consume the queue. Script entries can be static tool calls or functions that read the
  latest snapshot to resolve an element id.
- **Fake profile:** `fake_profile()` returns the fictional CORE-01 profile for any PIN,
  so a typed run never depends on a real profile file.
- **Test site map:** `fixture_config()` writes a temporary `sites.json` and points
  `SEARCH_URL` at the fixture search page. The mock domain `127.0.0.1` is trusted in that
  temporary map only; `app/sites.json` is untouched.
- **Human simulation:** `fixture_site().mark_human_done()` flips the portal's fake check
  and the test sends `done`. This simulates the person, it does not bypass the agent's
  human-check pause.
- **Counters:** the fixture server counts real portal submit attempts and submissions plus
  shop orders. That is stronger than inspecting the DOM and proves nothing irreversible ran
  before `confirm`.
- **Event dump:** on failure, the Console event log and the scripted LLM call summary are
  appended to the assertion. Sensitive values are masked with `****`.

## Task D note

Task D ("open my Gmail and read me my last mail") is the stretch goal and needs BRW-07's
CDP attach to the user's own Chrome. It is read-only: email text is untrusted data and
must never be followed as an instruction. Reply, send and delete stay irreversible and
need "confirm"; a Google login page is a human-only step.

The offline fixtures `inbox.html` and `message.html` are ready for that test, and the
temporary site map includes `e2e_inbox` with `trusted: false`. A future Task D test should
open `inbox.html`, follow the newest message, read the text, and assert that no
`type_text`, `fill_field` or irreversible click was sent to reply, send or delete. Until
BRW-07 lands, Task D is not part of the pass/fail result.
