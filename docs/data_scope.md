# Data Scope

Version: v1 week-1 scope

This document fixes the data boundaries for the heart failure medication CDSS MVP.

## Included Data Domains

| Domain | Included fields | Purpose |
| --- | --- | --- |
| Patient profile | case ID, age, sex, LVEF, eGFR, creatinine, potassium, SBP, heart rate, NYHA class | Summarize clinical state for recommendation logic |
| Comorbidities | CKD, diabetes, hypertension, atrial fibrillation, COPD, hypotension, bradycardia, polypharmacy | Drive risk extraction and constraint building |
| Current medications | medication names or classes | Support interaction and duplication checks |
| Allergies | medication allergy text | Support avoidance logic |
| Observations | measured values with units and optional timestamps | Preserve raw clinical evidence |
| Diagnoses | heart failure type and relevant comorbidities | Support graph and explanation context |
| Recommendations | drug class, status, rationale, evidence, warnings | Main system output |
| Audit logs | input, context, output, verification results | Reproducibility and thesis evaluation |

## Patient Population

Included:

- Adults with suspected or established heart failure.
- Patients where medication class selection is clinically relevant.
- HFrEF-focused cases, especially LVEF less than or equal to 40%.
- Borderline and safety-risk cases for renal function, potassium, blood pressure, and heart rate.

Excluded from MVP:

- Pediatric patients.
- Pregnancy-specific heart failure.
- Acute shock or ICU titration.
- Device therapy decisions.
- Surgical or transplant pathway decisions.
- Automated prescriptions.

## Initial Input Variables

Required for week-1 schema:

- `case_id`
- `comorbidities`
- `current_medications`
- `allergies`

Optional but recommended:

- `age`
- `sex`
- `lvef`
- `egfr`
- `creatinine`
- `potassium`
- `systolic_bp`
- `heart_rate`
- `nyha_class`

## Derived Variables

Later modules may derive:

- Heart failure phenotype: HFrEF, HFmrEF, HFpEF, or unclassified.
- Renal impairment severity.
- Hyperkalemia severity.
- Hypotension flag.
- Bradycardia flag.
- Polypharmacy flag.
- Medication-class constraints.

## Output Categories

Medication decisions use four categories:

- `recommend`: evidence-supported option without detected blocking constraints.
- `consider`: possible option requiring physician review or additional information.
- `caution`: option may be appropriate but needs monitoring, dose adjustment, or sequencing care.
- `avoid`: option should not be used under detected constraints.

## Week-1 Data Assets

- `data/heart_failure/evaluation/synthetic_cases/day1_sample_cases.json`
- `data/heart_failure/scope/gdmt_medication_groups.json`
- `data/heart_failure/scope/clinical_risk_table.json`
- `docs/data_schema.md`

## Data Out Of Scope

- Real EHR data.
- Billing codes.
- Imaging files.
- Genomics.
- Free-text clinical notes, except optional future teaching examples.
- Longitudinal medication adherence data.

## Acceptance Criteria

Week 1 is complete when all included fields are documented, represented in Pydantic schemas where needed, and validated against 10 synthetic patient cases.
