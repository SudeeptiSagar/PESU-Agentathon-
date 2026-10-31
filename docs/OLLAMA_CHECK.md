# Check llm.py against a real Ollama (CORE-02)

For a teammate or an agent (for example Antigravity) on a machine that has Ollama and `qwen3:8b`.
It takes about 5 minutes. Nothing here uses profile data or secrets.

## Run

```bash
git clone https://github.com/SudeeptiSagar/PESU-Agentathon-.git && cd PESU-Agentathon-
git checkout core/CORE-02-llm          # until PR #45 is merged
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

ollama pull qwen3:8b                 # skip if already installed; Ollama must be running
cp .env.example .env                   # defaults: OLLAMA_URL=http://localhost:11434/v1, LLM_MODEL=qwen3:8b
python scripts/check_llm.py
pytest -q                              # should print 38 passed
```

If Ollama runs on another machine, set `OLLAMA_URL=http://<that-machine>:11434/v1` in `.env`.
If your model tag differs, set `LLM_MODEL` to the exact name from `ollama list`.

## What the script checks

| Check | Pass means |
|---|---|
| ollama reachable | `/api/tags` answers; lists installed models |
| model installed | `LLM_MODEL` is in that list |
| plain text reply | `llm()` returns text |
| tool call (fill_field f2) | the model picks `fill_field` for the date-of-birth field and the call passes schema validation |
| num_ctx honoured | a ~6000-token prompt is accepted whole (`prompt_tokens > 4096`) and a fact placed at the start is recalled |

It exits 1 if any check fails.

## Report back

Paste the full script output into issue #7 (CORE-02), plus the output of `ollama list`.

- **All pass:** `llm.py` works with your Ollama (CORE-02 was verified this way and issue #7 is closed).
- **`num_ctx honoured` fails:** `llm.py` now uses Ollama's native `/api/chat`, which takes `num_ctx` under `options`. If this still fails, send the output plus `ollama --version` to Prashanth and do not edit `llm.py` yourself.
- **`tool call` fails:** note the printed output. The model may need a different tag; this feeds CORE-03.
- **A connection error:** check that Ollama is running and the URL and firewall allow the request.

## CORE-03: model reliability test (issue #8)

Measures how often the model picks the right tool call. It sends 10 different `fill_field` scenarios
(right field id and the right `{placeholder}`) and 10 different `click` scenarios (the reliable
search result among ads, look-alikes and a page that tries to inject an instruction). The target is
9 out of 10 on each. It takes a few minutes. Needs Ollama running with the model; uses made-up pages
only.

```bash
git checkout main && git pull origin main      # the script is on main once its PR is merged
source .venv/bin/activate                      # Windows PowerShell: .venv\Scripts\Activate.ps1
python scripts/reliability_test.py
```

To compare another model you have installed, add `--model <name>` (for example `--model qwen2.5:1.5b`).

**Report back:** paste the whole output, including the markdown report at the end, into issue #8.
Exit code 0 means both suites met the target, 1 means one is below it, 2 means Ollama could not be reached.
