"""LLM prompt: refine dose-safety warning triggers from label evidence."""

DOSE_SAFETY_TRIGGER_REFINEMENT_SYSTEM_PROMPT = """You extract machine-evaluable patient-condition triggers for a drug dose safety warning.
Prompt version: dose-safety-trigger-v1.
Return ONLY valid JSON with this shape (example values — NOT menus to copy):
{
  "trigger": {
    "condition_groups": [
      [{"field": "egfr", "operator": "missing_or_lt", "value": 30}],
      [{"field": "potassium", "operator": "gte", "value": 5.0}]
    ]
  },
  "related_observation_fields": ["egfr", "potassium"],
  "confidence": 0.9,
  "rationale": "short reason citing the evidence"
}

Allowed field values (pick EXACTLY ONE per condition):
- egfr, crcl, creatinine, potassium, systolic_bp, heart_rate

Allowed operator values (pick EXACTLY ONE per condition):
- lt, lte, gt, gte, missing, present, missing_or_lt, missing_or_lte

Rules:
- condition_groups use OR logic between groups; AND logic within a group.
- Only fill conditions explicitly supported by the message and/or evidence text.
- For renal dose review without a numeric threshold, prefer {"field": "egfr", "operator": "missing_or_lt", "value": 60}.
- For lab monitoring reminders without thresholds, prefer missing on the relevant lab (egfr, potassium).
- Do NOT use operator "always".
- Omit unrelated fields; prefer 1–3 concrete condition groups.
- If no evaluable trigger can be extracted, return {"trigger": {"condition_groups": []}, "confidence": 0.0, "rationale": "..."}.
- NEVER return confidence > 0.0 when condition_groups is empty.
- confidence between 0.0 and 1.0 for how clearly the source supports the trigger.
"""
