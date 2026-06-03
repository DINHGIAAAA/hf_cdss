# Medication Scope

Version: v1 week-1 scope

This document defines the medication classes included in the MVP and how they will be represented in later reasoning, constraints, and explanations.

## Included Medication Classes

| Class | Examples | Role in MVP | Key safety dimensions |
| --- | --- | --- | --- |
| ARNI | sacubitril/valsartan | Core HFrEF GDMT class | blood pressure, renal function, potassium, ACE inhibitor washout, angioedema history |
| ACE inhibitor | enalapril, lisinopril | Core HFrEF GDMT alternative | renal function, potassium, cough, angioedema, pregnancy |
| ARB | losartan, valsartan | Core HFrEF GDMT alternative | renal function, potassium, blood pressure |
| Beta blocker | bisoprolol, carvedilol, metoprolol succinate | Core HFrEF GDMT class | heart rate, blood pressure, congestion status, COPD/asthma caution |
| MRA | spironolactone, eplerenone | Core HFrEF GDMT class | eGFR, potassium, renal monitoring |
| SGLT2 inhibitor | dapagliflozin, empagliflozin | Core HFrEF GDMT class | eGFR, ketoacidosis risk, genital infection risk, volume status |
| Loop diuretic | furosemide, torsemide, bumetanide | Symptom and congestion management | renal function, electrolytes, volume status |

## Initial Vocabulary

The implementation uses medication class vocabulary before full drug-level modeling. The current seed file is `data/guideline_scope/gdmt_medication_groups.json`.

Preferred canonical class names:

- `ARNI`
- `ACEi`
- `ARB`
- `beta_blocker`
- `MRA`
- `SGLT2i`
- `loop_diuretic`

## Decision Status By Class

Every recommendation should eventually produce one status per relevant medication class:

- `recommend`
- `consider`
- `caution`
- `avoid`

Week 1 only returns a placeholder SGLT2 inhibitor recommendation to stabilize the API contract.

## Medication Facts To Capture Later

For each class or drug:

- Indication context.
- Contraindications.
- Relative cautions.
- Starting dose.
- Target dose if needed for explanation.
- Renal thresholds.
- Potassium thresholds.
- Blood pressure or heart-rate constraints.
- Monitoring requirements.
- Evidence source references.

## Excluded Medication Areas

Excluded from MVP:

- Device therapy medications or procedural decisions.
- Inotropes and vasopressors for acute shock.
- Anticoagulation decision support beyond current-medication awareness.
- Lipid, diabetes, and hypertension therapy except where they affect heart failure medication safety.
- Full drug formulary management.

## Week-1 Acceptance Criteria

- Medication classes are documented.
- Initial GDMT group seed file exists.
- Recommendation schema supports drug class, status, rationale, evidence, and warnings.
- Future constraint work can map risks to affected medication classes.
