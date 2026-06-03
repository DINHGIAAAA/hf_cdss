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

Week 1 exposes a stable contract and placeholder reasoning service. Clinical logic is intentionally minimal until normalization, risk extraction, GraphRAG, dose checking, and verification modules are implemented in later weeks.

Request:

```json
{
  "patient": {
    "case_id": "CASE_001",
    "lvef": 30,
    "egfr": 28,
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
    "egfr": 28,
    "potassium": 5.4,
    "sbp": 92,
    "heart_rate": 58,
    "comorbidities": ["CKD", "Diabetes"]
  },
  "risk_flags": [
    {
      "name": "renal_impairment",
      "severity": "high",
      "evidence": "eGFR = 28"
    },
    {
      "name": "hyperkalemia",
      "severity": "moderate",
      "evidence": "Potassium = 5.4"
    }
  ],
  "recommendations": [
    {
      "drug_class": "SGLT2 inhibitor",
      "status": "consider",
      "rationale": "Potential GDMT option pending physician review and contraindication checks.",
      "evidence": ["Guideline evidence placeholder"],
      "warnings": []
    }
  ],
  "overall_status": "approved_with_warnings",
  "disclaimer": "This recommendation is for clinical decision support only and must be reviewed by a licensed physician."
}
```

## Status Values

- `approved`: no week-1 placeholder risk flags.
- `approved_with_warnings`: one or more risk flags.
- `blocked`: reserved for later hard contraindication logic.

## Future Routes

The following routes are planned but not implemented in week 1:

- `POST /normalize`
- `POST /risk-flags`
- `POST /constraints`
- `POST /graphrag/context`
- `POST /verify`
- `GET /audit/{case_id}`

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
