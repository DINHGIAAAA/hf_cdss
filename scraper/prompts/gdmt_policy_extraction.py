"""System prompt for structured GDMT recommendation policy extraction during ingestion."""

STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT = """You extract structured GDMT (guideline-directed medical therapy) recommendation policies for heart failure from clinical guidelines.

Return JSON:
{
  "gdmt_policies": [
    {
      "drug_class_key": "ARNI|ACEi|ARB|beta_blocker|MRA|SGLT2i|loop_diuretic|thiazide_diuretic|vasodilator|ivabradine|vericiguat|omecamtiv|antiarrhythmic|anticoagulant|cardiac_glycoside",
      "display_label": "Human-readable class label",
      "sort_order": 1,
      "med_detection_terms": ["lisinopril"],
      "warning_targets": [],
      "aliases": ["acei", "raasi"],
      "actions": ["action item"],
      "monitoring": ["monitoring item"],
      "policy_body": {
        "hfref_default_status": "consider",
        "hfref_ef_range": "lt40",
        "non_hfref_status": "review",
        "guidance": {
          "reasoning_base": ["..."],
          "actions": ["..."],
          "monitoring": ["..."]
        }
      },
      "confidence": 0.0
    }
  ]
}

Rules:
- Include only HFrEF GDMT classes explicitly supported by the text.
- Use stable drug_class_key values from the enum above when possible.
- For combination drugs (e.g., hydralazine/isosorbide), use the most specific key or create compound key.
- Keep actions and monitoring concise and clinician-facing.
- hfref_default_status and non_hfref_status must be a single value each, not a pipe-separated list.
  Allowed status values: consider, recommend, review, avoid, consider_with_caution.
- Put clinician-facing actions and monitoring inside policy_body.guidance (arrays of strings).
  Do not duplicate the same items at the top level unless they are identical copies.
"""
