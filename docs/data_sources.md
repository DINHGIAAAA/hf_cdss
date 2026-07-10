# Data Sources

Version: v1 week-1 scope

This document defines which source families the thesis MVP will use for guideline retrieval, medication facts, synthetic cases, and evaluation labels. Week 1 records the source plan only; full ingestion and chunking are scheduled for later milestones.

## Source Priority

| Priority | Source family | Planned use | Week-1 status |
| --- | --- | --- | --- |
| P1 | Heart failure clinical guidelines | GDMT indications, contraindication logic, decision rationale | Scoped |
| P1 | Drug labels and prescribing references | Dosing, renal restrictions, safety warnings, monitoring | Scoped |
| P1 | Synthetic patient cases | Local development, contract tests, early evaluation | Created |
| P2 | Local hospital or teaching notes | Optional local explanation context | Deferred |
| P2 | Published trial summaries | Evidence snippets for explanation | Deferred |
| P3 | EHR extracts | Real-world validation if permitted | Out of scope for MVP |

## Registry expansion (v4)

**Single source of truth:** `data/heart_failure/sources/sources.example.json` — chỉnh sửa trực tiếp file JSON này (không khai báo source trong script Python).

Validate / thống kê registry:

```powershell
python -m scraper.scripts.sources_registry
```

Sau khi sửa JSON, re-download và re-run ingestion:

```powershell
python -m scraper.acquisition.download_sources --registry data/heart_failure/sources/sources.example.json --storage s3 --allow-failures
python -m scraper.orchestration.run_ingestion_pipeline --skip-download
```

**Expected chunk corpus after full ingest:** ~1,800–2,500 chunks (up from ~700), improving hybrid retrieval candidate pools and rerank quality.

**Chunking note:** long drug-label SPL sections (≥600 tokens) now use the same semantic breakpoint strategy as guidelines.

## Guideline Sources

Primary guideline families:

- 2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure.
- 2021 ESC Guidelines for the Diagnosis and Treatment of Acute and Chronic Heart Failure.
- 2023 ESC Focused Update of the 2021 ESC Heart Failure Guidelines.

These sources should be stored later as raw PDF/HTML files under `data/raw/guidelines/`, then converted to clean text chunks under `data/guideline_chunks/`.

## Medication Sources

Medication data should be collected from official labels or trusted prescribing references. Initial medication classes are limited to:

- ARNI, ACE inhibitor, ARB.
- Evidence-based beta blocker.
- Mineralocorticoid receptor antagonist.
- SGLT2 inhibitor.
- Loop diuretic.

For each medication or class, the ingestion target is:

- Generic and brand names.
- Drug class.
- Typical starting dose.
- Renal considerations.
- Potassium or blood pressure cautions.
- Contraindications.
- Monitoring requirements.
- Source URL, version, and access date.

## Synthetic Cases

Week 1 created `data/heart_failure/evaluation/synthetic_cases/day1_sample_cases.json` with 10 manually authored cases. These cases are not patient records and must remain synthetic. They are intended for:

- Backend schema validation.
- Frontend demo placeholders.
- Early recommendation contract tests.
- Regression tests when week-2 risk extraction begins.

## Gold Labels

Gold labels live in `data/heart_failure/evaluation/gold_labels/` and include:

- Expected risk flags.
- Expected recommendation category by drug class.
- Expected caution or avoidance reasons.
- Reviewer notes.
- Label version.

## Data Governance Rules

- Do not commit real patient-identifiable information.
- Store source metadata with every guideline or label chunk.
- Preserve enough citation information for thesis reporting.
- Keep synthetic cases clearly marked as synthetic.
- Separate raw sources, processed chunks, and evaluation labels.

## Week-1 Decision

The MVP starts with source planning and synthetic data only. Guideline ingestion, drug-label extraction, graph seeding, vector indexing, and gold-label creation are later tasks.
