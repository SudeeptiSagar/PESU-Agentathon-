# LLM reliability (CORE-03), 2026-10-31

Run with `python scripts/reliability_test.py` on a Windows laptop, `main` after PR #49.

- Model: `qwen3:8b`, Ollama 0.32.14
- NUM_CTX: 8192, temperature 0, thinking off, target 9/10 each

| Suite | Result | Mean per call | Slowest |
|---|---|---|---|
| `fill_field` (10 scenarios) | **10/10**, meets target | 1.9 s | 8.4 s (first call, model load) |
| `click` (10 scenarios) | **10/10**, meets target | 0.9 s | 0.9 s |

**Model choice: `qwen3:8b`.** A step costs about 1 to 2 seconds, so a 30-step task is roughly a minute of model time on this laptop (the browser and speech add to that).

**Caveats**
- 20 hand-made scenarios at temperature 0 is a small sample. Real pages are larger and messier than these.
- The click scenarios include an ad and an "ignore all previous instructions" link, and neither was chosen.
- The test uses its own short system prompt. CORE-10 will write the real agent prompt, so re-run the script after that.
- "The right link" in the click scenarios is a design choice (an encyclopedia, Britannica or NASA page).
