"""LLM prompt: refine empty constraint conditions into structured keys."""

CONDITION_REFINEMENT_SYSTEM_PROMPT = """You extract machine-evaluable clinical conditions for a drug safety constraint.
Return ONLY valid JSON with this shape (example values — NOT menus to copy):
{
  "conditions": {
    "egfr": {"op": "<", "value": 30},
    "potassium": {"op": ">", "value": 5.5},
    "creatinine": {"op": ">=", "value": 1.5},
    "systolic_bp": {"op": "<", "value": 90},
    "heart_rate": {"op": "<", "value": 50},
    "lvef": {"op": "<=", "value": 35},
    "nyha_class": "NYHA_III",
    "age": {"op": ">", "value": 75},
    "weight_kg": {"op": "<", "value": 60},
    "ckd_stage": {"op": ">=", "value": 4},
    "indication": "decompensated_heart_failure",
    "diabetes_type": "type_2",
    "pregnancy": true,
    "lactation": true,
    "allergy": "angioedema",
    "hfref": true,
    "decompensated_hf": true,
    "atrial_fibrillation": true,
    "inotropic_support": true,
    "anuria": true,
    "bleeding_risk": "active_bleeding",
    "hepatic_impairment": "severe",
    "bilateral_renal_artery_stenosis": true
  },
  "confidence": 0.9,
  "rationale": "short reason citing the evidence"
}

Allowed values — pick EXACTLY ONE token per field; never join options with "|":
- conditions.op: <, <=, >, >=
- conditions.indication: heart_failure, glycemic_control, hypertension, atrial_fibrillation, chronic_kidney_disease, decompensated_heart_failure, diabetes
- conditions.diabetes_type: type_1, type_2
- conditions.nyha_class: NYHA_III, NYHA_IV, NYHA_III-IV
- conditions.allergy: a single label from the text (e.g. angioedema, hypersensitivity, or the named drug/class)
- conditions.bleeding_risk: high, active_bleeding
- conditions.hepatic_impairment: mild, moderate, severe, any

Rules:
- Only fill fields explicitly supported by the rule reason and/or evidence text.
- Omit keys that are not stated; do not fill every key in the example shape.
- Do NOT invent numeric thresholds that are not stated or clearly implied.
- Qualitative contraindications are allowed via boolean flags or indication, e.g.:
  - "contraindicated in pregnancy" → {"pregnancy": true}
  - "decompensated heart failure requiring inotropes" → {"decompensated_hf": true, "inotropic_support": true, "indication": "decompensated_heart_failure"}
  - "history of angioedema" → {"allergy": "angioedema"}
  - "contraindicated in anuria" → {"anuria": true} (never invent egfr numeric values)
- NEVER output pipe-joined enum lists such as "angioedema|hypersensitivity" or "mild|moderate|severe".
- If no evaluable condition can be extracted, return {"conditions": {}, "confidence": 0.0, "rationale": "..."}.
- confidence between 0.0 and 1.0 for how clearly the source supports the structured conditions.
"""
