# Comorbidity Scope

Version: v1 week-1 scope

This document defines the comorbidities and clinical risk conditions included in the MVP.

## Included Comorbidities And Risk Conditions

| Condition | Input signal | Why it matters | Initial use |
| --- | --- | --- | --- |
| Chronic kidney disease | comorbidity text, eGFR, creatinine | Affects eligibility, dosing, and monitoring for several GDMT classes | Risk extraction and constraints |
| Diabetes mellitus | comorbidity text | Relevant to SGLT2 inhibitor context and general cardiovascular risk | Patient summary and explanation |
| Hypertension | comorbidity text, SBP | Common heart failure comorbidity; affects GDMT sequencing and BP tolerance | Patient summary |
| Atrial fibrillation | comorbidity text, current medications | Affects rate-control context and interaction review | Patient summary and later interaction checks |
| COPD or asthma | comorbidity text, bronchodilator use | Relevant caution for beta blocker selection and explanation | Later constraint check |
| Hypotension | SBP, symptoms if available | Can limit ARNI, ACEi, ARB, beta blocker, or diuretic titration | Risk extraction |
| Bradycardia | heart rate | Can limit beta blocker initiation or titration | Risk extraction |
| Hyperkalemia | potassium | Can limit MRA and RAAS-inhibiting drugs | Risk extraction |
| Polypharmacy | current medication count | Increases interaction and adherence risk | Later verification |

## Initial Risk Flags

The week-1 placeholder service detects:

- `renal_impairment`: eGFR less than 30.
- `hyperkalemia`: potassium greater than or equal to 5.0.

The week-2 risk extraction module should expand these into a dedicated service using `data/guideline_scope/clinical_risk_table.json`.

## Out Of Scope For MVP

- Oncology-related cardiomyopathy protocols.
- Congenital heart disease.
- Pregnancy-specific cardiomyopathy.
- Advanced liver disease dosing pathways.
- Dialysis-specific medication optimization.
- Rare genetic cardiomyopathy treatment selection.

## Representation Rules

- Store comorbidities as a list of strings in week 1.
- Normalize names in later modules before applying rules.
- Preserve original user-entered text for auditability.
- Use objective observations when available instead of text-only labels.
- Map each risk flag to evidence, severity, and affected medication classes.

## Severity Plan

Risk severity uses:

- `low`: relevant context but unlikely to block medication choice alone.
- `moderate`: requires caution, monitoring, or sequencing.
- `high`: may block or strongly constrain medication choice.

## Week-1 Acceptance Criteria

- Comorbidity and risk-condition scope is documented.
- Synthetic cases include several comorbidity combinations.
- Risk table seed file maps risks to inputs and affected medication classes.
- Placeholder recommendation output includes risk flags with evidence and severity.
