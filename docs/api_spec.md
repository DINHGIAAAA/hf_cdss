# API Specification

Version: v1 week-1 skeleton

All responses are JSON. Error responses use:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": []
  }
}
```

## System

### `GET /health`

Returns application liveness.

Response:

```json
{
  "status": "ok",
  "service": "Heart Failure CDSS"
}
```

### `GET /version`

Returns release and environment metadata.

Response:

```json
{
  "version": "0.1.0",
  "environment": "development"
}
```

## Recommendation

### `POST /recommend`

Week 3 exposes a constraint-aware clinical recommendation contract. The route uses normalization, risk extraction, and constraint rules before generating structured medication-class statuses. GraphRAG and verification agents are exposed as separate MVP endpoints so the recommendation pipeline remains transparent and testable.

Request:

```json
{
  "patient": {
    "case_id": "CASE_001",
    "lvef": 30,
    "egfr": 38,
    "potassium": 5.4,
    "systolic_bp": 92,
    "heart_rate": 58,
    "comorbidities": ["CKD", "Diabetes"],
    "current_medications": [],
    "allergies": []
  }
}
```

Response:

```json
{
  "case_id": "CASE_001",
  "patient_summary": {
    "hf_type": "HFrEF",
    "lvef": 30,
    "egfr": 38,
    "potassium": 5.4,
    "sbp": 92,
    "heart_rate": 58,
    "comorbidities": ["CKD", "Diabetes"]
  },
  "risk_flags": [
    {
      "name": "renal_impairment",
      "severity": "moderate",
      "evidence": "eGFR = 38"
    },
    {
      "name": "hyperkalemia",
      "severity": "moderate",
      "evidence": "Potassium = 5.4"
    }
  ],
  "constraints": [
    {
      "constraint_id": "CASE_001:SGLT2I_RENAL_REVIEW",
      "case_id": "CASE_001",
      "target_drug_class": "SGLT2i",
      "action": "caution",
      "reason": "SGLT2 inhibitor eligibility and monitoring should be reviewed when renal function is reduced.",
      "constraint_type": "dose",
      "evidence_ref": "week2_rule:SGLT2I_RENAL_REVIEW"
    }
  ],
  "dose_warnings": [
    {
      "warning_id": "dose_mra_renal_potassium_review",
      "case_id": "CASE_001",
      "category": "dose_checking",
      "severity": "high",
      "target": "MRA",
      "message": "MRA dose or continuation requires potassium and renal function review.",
      "evidence_ref": "week7_dose_rule:MRA_RENAL_K_REVIEW",
      "related_medications": ["spironolactone"],
      "related_observations": {
        "egfr": 38,
        "potassium": 5.4
      }
    }
  ],
  "interaction_warnings": [
    {
      "warning_id": "interaction_raasi_mra_hyperkalemia_monitoring",
      "case_id": "CASE_001",
      "category": "interaction_checking",
      "severity": "high",
      "target": "RAASi_MRA",
      "message": "RAAS-inhibiting therapy combined with an MRA requires potassium and renal function monitoring.",
      "evidence_ref": "week7_interaction_rule:RAASI_MRA_K_RENAL_MONITORING",
      "related_medications": ["lisinopril", "spironolactone"],
      "related_observations": {
        "egfr": 38,
        "potassium": 5.4
      }
    }
  ],
  "recommendations": [
    {
      "drug_class": "SGLT2 inhibitor",
      "status": "consider_with_caution",
      "rationale": "SGLT2 inhibitor may be relevant for HFrEF, but patient-specific risks require review.",
      "evidence": ["week3_pipeline:patient_profile", "week3_pipeline:constraint_rules_v1"],
      "warnings": ["SGLT2 inhibitor eligibility and monitoring should be reviewed when renal function is reduced."],
      "constraint_ids": ["CASE_001:SGLT2I_RENAL_REVIEW"],
      "safety_warning_ids": []
    }
  ],
  "overall_status": "approved_with_warnings",
  "disclaimer": "This recommendation is for clinical decision support only and must be reviewed by a licensed physician."
}
```

## Status Values

- `approved`: no risk flags or medication constraints detected.
- `approved_with_warnings`: one or more risk flags or caution constraints detected, without a hard avoid constraint.
- `blocked`: one or more hard avoid constraints are present in the recommendation trace.

## Medication Safety

### `POST /dose/check`

Runs Week-7 deterministic dose and monitoring checks against current medications and
patient labs/vitals. This endpoint does not prescribe doses; it flags medication classes
that require clinician review.

Current checks include:

- digoxin with reduced or missing renal function
- MRA with low eGFR or elevated potassium
- loop diuretic lab and volume monitoring
- beta-blocker dose escalation with low or missing heart rate

### `POST /interaction/check`

Runs Week-7 deterministic drug-drug and drug-lab interaction checks.

Current checks include:

- ACE inhibitor + ARB combination
- RAAS-inhibiting therapy + MRA potassium/renal monitoring
- RAAS-inhibiting therapy + NSAID renal risk
- anticoagulant + antiplatelet bleeding review

Request shape:

```json
{
  "patient": {
    "case_id": "CASE_001",
    "egfr": 24,
    "potassium": 5.6,
    "heart_rate": 54,
    "current_medications": ["lisinopril", "spironolactone", "digoxin"],
    "comorbidities": ["CKD"],
    "allergies": []
  }
}
```

Response:

```json
{
  "case_id": "CASE_001",
  "warnings": [
    {
      "warning_id": "dose_digoxin_renal_review",
      "category": "dose_checking",
      "severity": "high",
      "target": "digoxin",
      "message": "Digoxin dosing requires renal function review because reduced eGFR increases toxicity risk.",
      "evidence_ref": "week7_dose_rule:DIGOXIN_RENAL_REVIEW"
    }
  ]
}
```

## GraphRAG and Verification

### `POST /graphrag/context`

Retrieves local graph facts and evidence chunks from Week-3 artifacts. This is GraphRAG v0: it uses the generated JSONL artifacts as a local retrieval index before Neo4j/Chroma integration.

Request:

```json
{
  "patient": {
    "case_id": "CASE_001",
    "lvef": 28,
    "egfr": 32,
    "potassium": 5.2,
    "systolic_bp": 94,
    "heart_rate": 56,
    "comorbidities": ["CKD", "Atrial fibrillation"],
    "current_medications": ["metoprolol", "furosemide", "apixaban"],
    "allergies": []
  },
  "top_k": 8
}
```

Response includes `query_terms`, `graph_facts`, `evidence_chunks`, and `context_summary`.

### `POST /verify`

Runs MVP verification agents against a patient and optional recommendation payload. If no recommendation is supplied, the backend builds one first.

Agents:

- `safety_agent`
- `missing_data_agent`
- `evidence_agent`
- `guideline_alignment_agent`
- `final_reviewer_agent`

Response includes GraphRAG context, agent results, and `final_verdict`.

### `POST /llm/answer`

Generates a natural-language explanation from the structured recommendation and optional verification context. The LLM is only used as an explanation layer: medication status, constraints, and safety verdicts still come from the deterministic CDSS pipeline and verification agents.

If `HF_CDSS_OPENAI_API_KEY` is not configured, the endpoint returns a deterministic fallback answer so the demo remains usable offline.

Request:

```json
{
  "user_input": "Male 68 with HFrEF, EF 28%, SBP 88 and HR 54...",
  "patient": {
    "case_id": "CASE_001",
    "lvef": 28,
    "egfr": 48,
    "potassium": 4.9,
    "systolic_bp": 88,
    "heart_rate": 54,
    "comorbidities": ["Atrial fibrillation"],
    "current_medications": ["metoprolol", "furosemide", "apixaban"],
    "allergies": []
  },
  "recommendation": {},
  "verification": {}
}
```

Response:

```json
{
  "case_id": "CASE_001",
  "answer": "Natural-language explanation...",
  "model": "gpt-4o-mini",
  "used_llm": true,
  "safety_note": "LLM answer is constrained to explain structured CDSS output and must not replace physician review."
}
```

## Audit

### `GET /audit/{case_id}`

Returns persisted PostgreSQL audit events for a case when audit storage is enabled.

## Clinical Pipeline

### `POST /normalize`

Returns the normalized clinical profile for a patient payload.

### `POST /risks`

Returns normalized profile plus extracted risk flags.

### `POST /constraints`

Returns normalized profile, extracted risk flags, and medication constraints.

Request shape for all three endpoints:

```json
{
  "patient": {
    "case_id": "W2_CASE_001",
    "lvef": 30,
    "egfr": 78,
    "potassium": 4.2,
    "systolic_bp": 118,
    "heart_rate": 76,
    "comorbidities": ["Hypertension"],
    "current_medications": ["amlodipine"],
    "allergies": []
  }
}
```
