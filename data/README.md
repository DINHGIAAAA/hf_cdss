# Data Layout

This directory keeps domain data grouped by clinical scope.

## `heart_failure/`

- `raw/`: original source files, including guideline PDFs and DailyMed drug labels.
- `processed/`: parsed guideline/drug-label documents, sections, and tables.
- `artifacts/`: generated intermediate artifacts used by retrieval, rule generation, and graph construction.
  - `claims/`: extracted evidence claims.
  - `chunks/`: retrieval-ready text chunks.
  - `entities/`: extracted clinical entities.
  - `relationships/`: graph relationship edges.
  - `rules/`: generated and curated medication rules.
  - `manifests/`: source download manifests.
- `schemas/`: input schemas for patient context and evaluation data.
- `evaluation/`: test and evaluation datasets.
  - `clinical_cases/`: medication recommendation and safety cases.
  - `synthetic_cases/`: backend patient-profile synthetic cases.
  - `gold_labels/`: expected labels for synthetic cases.
- `scope/`: project-level scope files for guideline sources, medication groups, and clinical risk tables.
- `scripts/`: data processing and rule-generation utilities.

Run heart-failure data scripts from `data/heart_failure` so their default relative paths resolve correctly.
