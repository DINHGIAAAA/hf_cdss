# Data Schema

Version: v1

This document defines the initial structured data contracts for the Heart Failure CDSS demo. Field names use snake_case to match the backend Pydantic schemas.

## Patient Profile

Represents one heart failure patient case.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| case_id | string | yes | Stable case identifier, for example `CASE_001`. |
| age | integer | no | Years. |
| sex | string | no | `male`, `female`, or `unknown`. |
| lvef | number | no | Left ventricular ejection fraction in percent. |
| egfr | number | no | Estimated glomerular filtration rate. |
| creatinine | number | no | Serum creatinine. |
| potassium | number | no | Serum potassium. |
| systolic_bp | number | no | Systolic blood pressure. |
| heart_rate | number | no | Beats per minute. |
| nyha_class | string | no | NYHA class I-IV. |
| comorbidities | string[] | yes | Comorbid conditions relevant to recommendation safety. |
| current_medications | string[] | yes | Current medication names or classes. |
| allergies | string[] | yes | Known medication allergies. |

## Medication

Represents a drug or drug class relevant to heart failure GDMT.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| medication_id | string | yes | Stable identifier. |
| name | string | yes | Medication or drug class display name. |
| drug_class | string | yes | ACEi, ARB, ARNI, beta_blocker, MRA, SGLT2i, loop_diuretic, etc. |
| route | string | no | Oral, IV, or other. |
| typical_starting_dose | string | no | Human-readable starting dose for reference only. |
| contraindications | string[] | yes | Major contraindication statements. |
| monitoring_requirements | string[] | yes | Labs or vitals to monitor. |

## Observation

Represents a measured clinical value.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| observation_id | string | yes | Stable identifier. |
| case_id | string | yes | Related patient case. |
| name | string | yes | LVEF, eGFR, potassium, SBP, HR, creatinine. |
| value | number/string | yes | Numeric or categorical result. |
| unit | string | no | Percent, mmol/L, mL/min/1.73m2, mmHg, bpm. |
| observed_at | string | no | ISO 8601 datetime if available. |

## Diagnosis

Represents a condition or heart failure classification.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| diagnosis_id | string | yes | Stable identifier. |
| case_id | string | yes | Related patient case. |
| name | string | yes | Diagnosis name. |
| category | string | no | Heart failure type, comorbidity, or risk condition. |
| evidence | string | no | Observation or source supporting the diagnosis. |

## Recommendation

Represents one medication recommendation output.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| case_id | string | yes | Related patient case. |
| patient_summary | object | yes | Normalized patient summary used for reasoning. |
| risk_flags | object[] | yes | Extracted safety risks. |
| recommendations | object[] | yes | Medication class decisions. |
| overall_status | string | yes | `approved`, `approved_with_warnings`, or `blocked`. |
| disclaimer | string | yes | Required clinical decision support disclaimer. |

## Risk Flag

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| name | string | yes | Example: renal_impairment, hyperkalemia, hypotension. |
| severity | string | yes | low, moderate, high. |
| evidence | string | yes | Source value or rule explanation. |

## Constraint

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| constraint_id | string | yes | Stable identifier. |
| case_id | string | yes | Related patient case. |
| target_drug_class | string | yes | Drug class affected by the constraint. |
| action | string | yes | recommend, consider, caution, avoid. |
| reason | string | yes | Clinical reason. |
| evidence_ref | string | no | Guideline, graph, vector chunk, or rule reference. |

## Evidence

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| evidence_id | string | yes | Stable identifier. |
| source_type | string | yes | guideline, drug_label, graph, rule. |
| title | string | yes | Human-readable source title. |
| excerpt | string | no | Short supporting text. |
| metadata | object | yes | Page, section, version, retrieval score, etc. |

## Audit Log

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| audit_id | string | yes | Stable identifier. |
| case_id | string | yes | Related patient case. |
| input | object | yes | Request payload. |
| context | object | yes | GraphRAG and constraint context. |
| output | object | yes | Recommendation response. |
| agent_results | object[] | yes | Verification agent pass/fail/warning results. |
| created_at | string | yes | ISO 8601 datetime. |
