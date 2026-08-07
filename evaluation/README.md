# Extraction evaluation

## Automatic (recommended — no manual labeling)

```powershell
cd c:\Users\VinhNgo\hf_cdss
$env:PYTHONPATH="."
$env:HF_CDSS_DATA_ROOT="c:\Users\VinhNgo\hf_cdss\data\heart_failure"

# Staged filter (updates claims_filtered.jsonl + claim_filter_progression.*)
py -m scraper.eval.filter_claims_for_quality --per-type 30 --seed 42

# Fast: heuristic only on raw claims
py -m scraper.eval.run_auto_eval --no-llm --per-type 20

# Semantic LLM judge on filtered corpus (runtime KG input)
py -u -m scraper.eval.run_auto_eval `
  --input data/heart_failure/artifacts/claims/claims_filtered.jsonl `
  --per-type 10 --seed 42 --model qwen2.5:7b --timeout-seconds 300

# Safety-only semantic sample (exclude noisy guideline_recommendation)
py -u -m scraper.eval.run_auto_eval `
  --input data/heart_failure/artifacts/claims/claims_filtered.jsonl `
  --exclude-types guideline_recommendation `
  --per-type 10 --seed 42 --model qwen2.5:7b

# Raw corpus (pre-filter) — expect lower estimated_precision until re-extract with latest gates
py -u -m scraper.eval.run_auto_eval `
  --input data/heart_failure/artifacts/claims/claims.jsonl `
  --per-type 10 --seed 42 --model qwen2.5:7b
```

Outputs:

- `evaluation/reports/auto_eval_latest.json` — metrics (`estimated_precision`, hard-types, per-type)
- `evaluation/reports/auto_eval_*_judgments.jsonl` — per-claim verdicts
- `evaluation/reports/claim_filter_progression.json` — structural quality after each filter pass

`estimated_precision` = auto-judge accept rate on a stratified sample (not clinician-certified).

**Interpretation:** Report ~53% on **raw** `claims.jsonl` reflects unfiltered extraction noise. **Filtered** `claims_filtered.jsonl` is what the pipeline uses after passes 1–8 (type cues, off-scope drugs, SPL boilerplate, trials, ADR actionability, shared type gates). Re-run `create_claims` after gate changes to raise raw precision on the next extraction.

### Snapshot (2026-07-31, seed=42, per-type=10)

| Corpus | Judge | Report | `estimated_precision` | Notes |
|--------|-------|--------|-------------------------|--------|
| Raw `claims.jsonl` | LLM 7B | `auto_eval_20260731T082704Z.json` | **53.3%** (48/90) | Pre-fix baseline |
| Filtered `claims_filtered.jsonl` | Heuristic | `auto_eval_20260731T094556Z.json` | **100%** (90/90) | Post-fix filter; structural gates align with auto_judge heuristics |
| Filtered | LLM 7B | `auto_eval_20260731T111954Z.json` | **81.1%** (73/90); hard types **74%** (37/50) | Same seed/per-type as raw baseline; guideline type **90%** vs **10%** pre-fix |

Filter progression (`claim_filter_progression.json`): **7648 → 3438** claims; pass 8 `strict_structural_precision` **100%** on stratified sample (262 claims).

Re-extract after gate changes: `py -m scraper.process.create_claims` (optionally `HF_CDSS_CLAIM_LLM_ENABLED=false` for regex-only). If validation aborts with `>20% drop rate`, the corpus still reflects prior extraction until alignment tuning — filtered eval above uses post-filter gates on the existing file.

## Optional clinician gold

Manual JSON labeling is **optional**. Only use if you later want certified ≥95% claims.
See `annotation_guide.md` and `gold/`.

```powershell
py -m scraper.eval.evaluate_claims_against_gold
py -m pytest scraper/eval/test_evaluate_claims_against_gold.py -q
```
