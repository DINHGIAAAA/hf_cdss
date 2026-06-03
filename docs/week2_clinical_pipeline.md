# Week 2 Clinical Pipeline

Version: v1

Week 2 converts raw patient JSON into a normalized clinical profile, extracts patient-specific risk flags, and builds medication constraints from JSON rules.

## Pipeline Design

1. Receive a `PatientProfile` payload.
2. Normalize clinical variables and text lists.
3. Classify heart failure phenotype and safety dimensions.
4. Extract risk flags with severity and evidence.
5. Apply constraint rules to the risk flags.
6. Return normalized profile, risks, and constraints.

## APIs

| Route | Purpose |
| --- | --- |
| `POST /normalize` | Returns normalized patient profile. |
| `POST /risks` | Returns normalized profile and risk flags. |
| `POST /constraints` | Returns normalized profile, risk flags, and constraints. |

## Normalization Functions

| Function | Output examples |
| --- | --- |
| `classify_hf_type` | `HFrEF`, `HFmrEF`, `HFpEF`, `unknown` |
| `classify_renal_status` | `preserved`, `mildly_reduced`, `moderately_reduced`, `severely_reduced`, `kidney_failure`, `missing` |
| `classify_potassium_status` | `low`, `normal`, `elevated`, `high`, `missing` |
| `classify_bp_status` | `hypotension`, `low`, `acceptable`, `elevated`, `missing` |
| `classify_hr_status` | `bradycardia`, `acceptable`, `tachycardia`, `missing` |
| `detect_polypharmacy` | `true` when medication count is at least 5 |

## Clinical Rule Thresholds v1

| Dimension | Rule |
| --- | --- |
| HFrEF | LVEF <= 40 |
| HFmrEF | LVEF 41-49 |
| HFpEF | LVEF >= 50 |
| Moderate renal impairment | eGFR 30-44 |
| Severe renal impairment | eGFR < 30 |
| Kidney failure bucket | eGFR < 15 |
| Elevated potassium | K+ 5.0-5.4 |
| High potassium | K+ >= 5.5 |
| Hypotension | SBP < 90 |
| Low blood pressure | SBP 90-99 |
| Bradycardia | HR < 60 |
| Polypharmacy | Current medication count >= 5 |

## Constraint Classes

| Class | Meaning | Example |
| --- | --- | --- |
| Hard | Strong avoid/defer signal | Avoid MRA with severe renal impairment or high potassium. |
| Soft | Caution or sequencing signal | Use caution with ARNI/ACEi/ARB when BP is low. |
| Dose | Dose or eligibility review | Review SGLT2i eligibility when renal function is reduced. |
| Monitoring | Lab/vital follow-up needed | Monitor potassium and renal function with MRA/RAASi. |

## Rule File

Constraint rules live in:

`backend/app/modules/constraint_builder/rules/constraints_v1.json`

The rule engine matches risk names and severity levels, then emits structured `Constraint` objects.

## Example Request

```json
{
  "patient": {
    "case_id": "W2_CASE_019",
    "lvef": 22,
    "egfr": 12,
    "potassium": 5.8,
    "systolic_bp": 86,
    "heart_rate": 52,
    "comorbidities": ["CKD", "Diabetes"],
    "current_medications": ["furosemide", "warfarin", "digoxin", "atorvastatin", "aspirin", "metoprolol"],
    "allergies": ["ACEi angioedema"]
  }
}
```

## Example `/constraints` Output

```json
{
  "normalized_profile": {
    "case_id": "W2_CASE_019",
    "hf_type": "HFrEF",
    "renal_status": "kidney_failure",
    "potassium_status": "high",
    "bp_status": "hypotension",
    "hr_status": "bradycardia",
    "has_polypharmacy": true,
    "normalized_comorbidities": ["ckd", "diabetes"],
    "normalized_current_medications": ["furosemide", "warfarin", "digoxin", "atorvastatin", "aspirin", "metoprolol"],
    "normalized_allergies": ["acei angioedema"],
    "observations": {
      "lvef": 22,
      "egfr": 12,
      "potassium": 5.8,
      "systolic_bp": 86,
      "heart_rate": 52
    }
  },
  "risk_flags": [
    {"name": "renal_impairment", "severity": "high", "evidence": "eGFR = 12"},
    {"name": "hyperkalemia", "severity": "high", "evidence": "Potassium = 5.8"},
    {"name": "hypotension", "severity": "high", "evidence": "SBP = 86"},
    {"name": "bradycardia", "severity": "moderate", "evidence": "Heart rate = 52"},
    {"name": "polypharmacy", "severity": "moderate", "evidence": "Current medication count >= 5."},
    {"name": "diabetes", "severity": "low", "evidence": "Diabetes listed in comorbidities."}
  ],
  "constraints": [
    {
      "constraint_id": "W2_CASE_019:MRA_HARD_RENAL_OR_K",
      "case_id": "W2_CASE_019",
      "target_drug_class": "MRA",
      "action": "avoid",
      "reason": "Avoid or defer MRA when renal impairment is severe or potassium is high.",
      "evidence_ref": "week2_rule:MRA_HARD_RENAL_OR_K"
    }
  ]
}
```

## Week-2 Data Assets

- `data/heart_failure/evaluation/synthetic_cases/week2_30_cases.json`
- `data/heart_failure/evaluation/gold_labels/week2_expected_risks.json`
- `backend/app/modules/constraint_builder/rules/constraints_v1.json`

## Week-2 Acceptance Criteria

- The three APIs return structured JSON.
- The 30 synthetic cases validate against `PatientProfile`.
- Expected risk labels match extracted risk names.
- Unit tests cover normalization, risk extraction, constraints, API behavior, and edge cases.
