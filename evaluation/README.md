# Extraction evaluation

## Automatic (recommended — no manual labeling)

```powershell
cd c:\Users\VinhNgo\hf_cdss
$env:PYTHONPATH="."
$env:HF_CDSS_DATA_ROOT="c:\Users\VinhNgo\hf_cdss\data\heart_failure"

# Fast: heuristic only
py -m scraper.eval.run_auto_eval --no-llm --per-type 20

# Stronger: heuristic + Ollama judge (needs LLM reachable; default 300s timeout per claim)
py -u -m scraper.eval.run_auto_eval --per-type 10 --seed 42 --model qwen2.5:7b --timeout-seconds 300
```

Outputs:
- `evaluation/reports/auto_eval_latest.json` — metrics (`estimated_precision`, hard-types, per-type)
- `evaluation/reports/auto_eval_*_judgments.jsonl` — per-claim verdicts

`estimated_precision` = auto-judge accept rate on a stratified sample (not clinician-certified).

## Optional clinician gold

Manual JSON labeling is **optional**. Only use if you later want certified ≥95% claims.
See `annotation_guide.md` and `gold/`.
