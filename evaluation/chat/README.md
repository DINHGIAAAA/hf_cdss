# Chat vignette evaluation

~80 clinical chat scenarios (single Q → multi-Q → missing data → follow-up → language → patient-based dose calculation).

## Files

| File | Purpose |
|------|---------|
| `vignettes.json` | Test case definitions |
| `../reports/chat_vignette_results_*.json` | Run output |
| `../reports/chat_vignette_results_latest.json` | Symlink-like latest copy |

## Run

In-process (uses `process_chat` directly — needs backend deps + Ollama for full LLM answers):

```powershell
cd c:\Users\VinhNgo\hf_cdss\backend
python scripts/run_chat_vignette_eval.py --limit 3
```

Against running Docker backend:

```powershell
python scripts/run_chat_vignette_eval.py --api-url http://127.0.0.1:8000/api/v1 --api-key change-me
```

Filter:

```powershell
python scripts/run_chat_vignette_eval.py --case-id mq-en-02
python scripts/run_chat_vignette_eval.py --category patient_based_dose --limit 5
```

## Output structure

Each result entry includes:

- `input` — message, language, patient profile, conversation_id
- `detection` — auto language, rule split, question planner output
- `output` — status, answer, missing_check, clinical_state, recommendation_summary, evidence, verification, LLM metadata
- `timestamp`, `duration_ms`, `error`

Multi-question cases auto-run a `continue` turn when the first response is `multi_question_confirm`.
