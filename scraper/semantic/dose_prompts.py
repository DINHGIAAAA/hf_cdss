"""Prompts for structured dose-rule extraction from clinical sources."""

STRUCTURED_DOSE_EXTRACTION_SYSTEM_PROMPT = """You extract structured, calculator-ready dose rules from FDA drug labels and cardiology guidelines.
Return ONLY valid JSON with this shape:
{
  "dose_rules": [
    {
      "drug": "generic drug name",
      "drug_class": "beta_blocker|ACEi|ARB|ARNI|MRA|SGLT2i|anticoagulant|loop_diuretic|cardiac_glycoside|anticoagulant_vka",
      "drug_keys": ["generic name", "brand if stated"],
      "indication": "heart_failure|atrial_fibrillation|hypertension|null",
      "calculation_type": "fixed_titration|step_titration|fixed_dose|crcl_threshold_dose|criteria_reduction|dual_criteria_reduction|dabigatran_dose|warfarin_inr|crcl_bracket|weight_adjusted_target|congestion_range",
      "standard_dose": {"value": number, "unit": "mg", "frequency": "once daily|twice daily", "label": "optional display label"},
      "reduced_dose": {"value": number, "unit": "mg", "frequency": "...", "label": "..."},
      "starting_dose": {"value": number, "unit": "mg", "frequency": "..."},
      "target_dose": {"value": number, "unit": "mg", "frequency": "..."},
      "recommended_dose": {"value": number, "unit": "mg", "frequency": "..."},
      "renal_reduced_dose": {"value": number, "unit": "mg", "frequency": "..."},
      "dose_steps": [{"label": "24/26 mg", "value": 24, "unit": "mg", "frequency": "twice daily"}],
      "reduction_criteria": [{"field": "age|weight_kg|creatinine|crcl", "operator": "gte|lte|between", "value": 80, "value_low": 15, "value_high": 50, "label": "human label"}],
      "reduction_min_matches": 2,
      "crcl_threshold": 50,
      "crcl_minimum": 15,
      "inr_target_low": 2.0,
      "inr_target_high": 3.0,
      "step_interval_weeks": 2,
      "step_multiplier": 2.0,
      "hold_if": {"systolic_bp_lt": 100, "potassium_gte": 5.5, "egfr_lt": 30, "heart_rate_lt": 60},
      "monitoring": ["string"],
      "evidence": "verbatim quote from source supporting this rule",
      "confidence": 0.0
    }
  ]
}

Rules:
- Include ONLY dose rules explicitly supported by the provided text. Do not invent numbers.
- evidence MUST be copied verbatim from the source (minimum 20 characters).
- Prefer calculation_type that matches the source structure:
  - discrete titration steps -> step_titration with dose_steps
  - start/target doubling -> fixed_titration with starting_dose and target_dose
  - renal threshold dose change -> crcl_threshold_dose
  - multiple patient criteria for reduced dose -> dual_criteria_reduction or criteria_reduction
  - single fixed maintenance dose -> fixed_dose with recommended_dose
- Omit fields not stated in the source (use null or omit keys).
- confidence between 0.5 and 1.0 based on clarity and completeness.
- For drug labels, drug must match the label drug when drug-specific.
"""
