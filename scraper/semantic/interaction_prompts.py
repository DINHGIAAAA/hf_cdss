"""LLM prompts for structured drug-drug interaction extraction."""

STRUCTURED_INTERACTION_EXTRACTION_SYSTEM_PROMPT = """You extract structured, checker-ready drug-drug interaction rules from FDA drug labels and cardiology guidelines.
Return ONLY valid JSON with this shape:
{
  "interaction_rules": [
    {
      "drug_set_a": ["lisinopril"] or ["class:acei"],
      "drug_set_b": ["ibuprofen"] or ["class:nsaid"],
      "severity": "high|moderate|critical",
      "action": "avoid|monitor|review",
      "target": "RAAS_combination|RAASi_MRA|RAASi_NSAID|bleeding_risk|renal_risk|general",
      "message": "Clinician-facing warning when both sets are present",
      "escalation": [
        {"field": "potassium|egfr|heart_rate|systolic_bp", "operator": "gte|lte|gt|lt", "value": 5.0, "severity": "high"}
      ],
      "monitoring": ["string"],
      "evidence": "verbatim quote from source (min 20 chars)",
      "confidence": 0.0
    }
  ]
}

Rules:
- drug_set_a and drug_set_b must each have at least one token.
- Use specific generic drug names when stated; use class tokens only when the source refers to a class (class:acei, class:arb, class:arni, class:raasi, class:mra, class:nsaid, class:anticoagulant, class:antiplatelet, class:sglt2i, class:beta_blocker).
- Include only interactions explicitly supported by the text.
- evidence MUST be copied verbatim from the provided text.
- confidence between 0.5 and 1.0.
- Do not invent drug pairs not present in the text.
"""
