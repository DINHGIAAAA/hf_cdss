# Week 3 Clinical Recommendation MVP

Version: v1

Week 3 turns the patient clinical pipeline into a minimal end-to-end CDSS flow. The system now accepts a patient payload, normalizes clinical variables, extracts risk flags, builds medication-class constraints, and returns structured GDMT recommendation statuses.

## Scope

This milestone intentionally stays rule-based and transparent. Graph retrieval, vector retrieval, LLM reasoning, dose checking, interaction checking, and multi-agent verification remain later milestones.

## End-to-End Flow

1. Receive `POST /recommend` with a `PatientProfile`.
2. Normalize HF phenotype, renal status, potassium status, blood pressure status, heart rate status, comorbidities, medications, and allergies.
3. Extract risk flags with severity and evidence strings.
4. Apply constraint rules from `constraints_v1.json`.
5. Generate one recommendation status for each MVP GDMT class.
6. Return a clinical decision support disclaimer.

## Medication Classes

| Internal class | Display class | Week-3 behavior |
| --- | --- | --- |
| `ARNI/ACEi/ARB` | RAAS inhibition / ARNI | Consider for HFrEF, caution with low BP or hyperkalemia. |
| `beta_blocker` | Evidence-based beta blocker | Consider for HFrEF, caution with bradycardia. |
| `MRA` | Mineralocorticoid receptor antagonist | Avoid when hard renal or potassium constraints are detected. |
| `SGLT2i` | SGLT2 inhibitor | Consider for HFrEF, caution/review with reduced renal function. |

## Recommendation Status Values

| Status | Meaning |
| --- | --- |
| `consider` | Relevant HFrEF GDMT class without detected patient-specific constraints. |
| `consider_with_caution` | Relevant class, but one or more caution, monitoring, dose, or broad GDMT constraints apply. |
| `avoid` | A hard safety constraint applies to the class. |
| `review` | HF phenotype or patient context requires clinician review before applying HFrEF GDMT assumptions. |

## Overall Status Values

| Status | Meaning |
| --- | --- |
| `approved` | No risk flags or medication constraints detected. |
| `approved_with_warnings` | Risk flags or caution constraints detected, but no hard avoid constraint. |
| `blocked` | At least one hard avoid constraint is present in the recommendation trace. |

## Acceptance Criteria

- `POST /recommend` uses `clinical_normalization`, `risk_extraction`, and `constraint_builder`.
- Response includes patient summary, risk flags, constraints, recommendations, overall status, and disclaimer.
- Constraint objects include `constraint_type` for hard, soft, dose, and monitoring traceability.
- MRA is never returned as `consider` when a hard MRA constraint is detected.
- Clean HFrEF cases return `consider` for the four MVP GDMT classes.
- Non-HFrEF cases return `review` statuses instead of applying HFrEF assumptions directly.
- Frontend chat workflow can accept free-text patient status, parse core clinical facts, call `/recommend`, and display summary, risks, constraints, medication-class statuses, and evidence references.
- Backend test suite passes.

## Week-3 Test Coverage

The backend tests cover:

- Normalization thresholds.
- Risk extraction edge cases.
- Constraint rule loading and matching.
- `/normalize`, `/risks`, and `/constraints` API responses.
- `/recommend` clean, caution, blocked, and non-HFrEF behavior.
- Synthetic case validation against expected risk labels.
