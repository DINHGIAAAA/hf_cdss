# Evaluation Report

## Claim KG quality (qwen2.5:7b judge + new prompt)

| Set | Claims | 7b precision |
|-----|-------:|-------------:|
| Raw (historical 1.5b) | 16,973 | ~57.8% (1.5b) |
| Filtered all types | 7,620 | **62.2%** |
| **Filtered safety-only** | **5,764** | **66.3%** |

Safety-only drops `guideline_recommendation` (noisiest type under 7b).

Strong types @7b: contraindication / ADR / usage **80%**; interaction / hyperkalemia **70%**.

## Note on 1.5b vs 7b

1.5b previously reported **71%** on filtered claims — that number is **optimistic**. Prefer **7b** figures above for thesis/KG cleanliness.

## Hardware

GTX 1650 4GB: pause Airflow/backend embeddings before 7b judge runs.

## Vignette CDSS accuracy (unchanged)

94.0% structured recommendation accuracy.
