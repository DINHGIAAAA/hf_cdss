# Guideline Scope v1

Week 1 fixes the scope for later retrieval and reasoning work. The MVP focuses on adult heart failure medication support, especially HFrEF GDMT selection, contraindication checks, and physician-facing explanation.

## Primary Clinical Scope

- Adult patients with suspected or established heart failure.
- HFrEF-oriented GDMT decisions where LVEF is less than or equal to 40%.
- Safety checks around renal function, potassium, blood pressure, heart rate, allergies, and current medications.
- Output categories: `recommend`, `consider`, `caution`, and `avoid`.

## Out of Scope for MVP

- Pediatric heart failure.
- Acute shock or ICU titration protocols.
- Device therapy selection.
- Automated prescribing or autonomous medication changes.
- Full EHR integration.

## Guideline Families To Ingest Later

- ACC/AHA/HFSA heart failure guideline material.
- ESC heart failure guideline material.
- Drug labels or institutional dosing references for common GDMT medications.
- Local hospital notes can be added later as a separate source type.

## Week 1 Data Artifacts

- `gdmt_medication_groups.json`: initial medication class vocabulary.
- `clinical_risk_table.json`: risk flags and affected drug classes.
- `synthetic_cases/day1_sample_cases.json`: 10 manually authored patient profiles.
