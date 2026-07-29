"""System prompt for prescriptive clinical claim extraction during ingestion."""

# EXTRACTION GUIDELINES - BALANCED
EXTRACTION_GUIDELINES = """
EXTRACTION GUIDELINES:

1. EXTRACT ALL clinical claims - be comprehensive:
   ✓ "Do not use in pregnancy" → EXTRACT
   ✓ "Monitor potassium regularly" → EXTRACT
   ✓ "Reduce dose to 25mg" → EXTRACT
   ✓ "Avoid concomitant use with X" → EXTRACT
   ✓ "May cause hyperkalemia" → EXTRACT (warning)
   ✓ "Use with caution in renal impairment" → EXTRACT
   ✓ "Drug X may interact with Drug Y" → EXTRACT
   ✓ "In patients with eGFR <30, reduce dose" → EXTRACT
   ✓ "Monitor renal function" → EXTRACT

2. EXCLUDE ONLY clearly informational content:
   ✗ "In clinical trials, 5% experienced headache" → SKIP (incidence statistic)
   ✗ "The study showed 20% reduction (p<0.05)" → SKIP (study result)
   ✗ "Table 3 shows adverse reactions" → SKIP (table reference only)
   ✗ "Pregnancy Category C" → SKIP (label only)
   ✗ "Randomized controlled trial showed..." → SKIP (study description)

3. WHEN IN DOUBT → EXTRACT (better to have more claims than miss important ones)

4. CLINICAL KEYWORDS TO LOOK FOR:
   - dose, dosage, mg, administer, start, stop, reduce, increase
   - contraindication, warning, precaution, avoid, not recommended
   - monitor, check, measure, assess
   - interact, concomitant, renal, hepatic, pregnancy
   - hyperkalemia, potassium, creatinine, egfr
   - adverse, reaction, risk, caution
"""

CHAIN_OF_THOUGHT_PROMPT = """
Follow these steps to extract claims:

Step 1: IDENTIFY - Read the text and identify all clinical statements about:
  - Drug contraindications or warnings
  - Dosage recommendations or adjustments
  - Drug interactions
  - Population restrictions (pregnancy, renal impairment, etc.)
  - Monitoring requirements
  - Adverse reactions

Step 2: CLASSIFY - For each statement, determine:
  - Is this a contraindication, constraint, recommendation, or interaction?
  - What drug(s) does this apply to?
  - What patient conditions trigger this rule?
  - What is the clinical significance (high/medium/low)?

Step 3: EXTRACT - Copy the exact evidence text (minimum 20 characters)
  - Use VERBATIM quotes from the source text
  - Do not paraphrase or summarize

Step 4: STRUCTURE - Map to the JSON schema using allowed values only
  - claim_type must be one of: contraindication, renal_constraint, usage_constraint, hyperkalemia_risk, dose_recommendation, drug_interaction, adverse_reaction, population_constraint, guideline_recommendation, general_monitoring
  - action must be one of: contraindicated, not_recommended, avoid, monitor, recommended, dose_adjust, review
  - Never join options with "|"

Step 5: VALIDATE - Ensure each output field uses exactly one allowed token
  - Check that all numeric thresholds appear verbatim in evidence
  - Verify drug names match source text
  - Set confidence based on clarity (0.5-1.0)
"""

CLAIM_EXTRACTION_SYSTEM_PROMPT = EXTRACTION_GUIDELINES + """

You extract ALL clinical claims from FDA drug labels and cardiology guidelines.
Be COMPREHENSIVE - extract any clinical guidance that affects prescribing decisions.
Only exclude clearly informational content (study results, statistics, table references).
Return ONLY valid JSON with this shape (example values — NOT menus to copy):
{
  "claims": [
    {
      "claim_type": "renal_constraint",
      "evidence": "verbatim quote from the source text",
      "drug": "spironolactone",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {
        "egfr": {"op": "<", "value": 30},
        "potassium": {"op": ">", "value": 5.5},
        "creatinine": {"op": ">=", "value": 1.5},
        "systolic_bp": {"op": "<", "value": 100},
        "heart_rate": {"op": "<", "value": 60},
        "lvef": {"op": "<=", "value": 40},
        "nyha_class": "III",
        "age": {"op": ">", "value": 75},
        "weight_kg": {"op": "<", "value": 70},
        "ckd_stage": {"op": ">=", "value": 4},
        "indication": "heart_failure",
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
      }
    }
  ]
}

Allowed values — pick EXACTLY ONE token per field; never join options with "|":
- claim_type: contraindication, renal_constraint, usage_constraint, hyperkalemia_risk, dose_recommendation, drug_interaction, adverse_reaction, population_constraint, guideline_recommendation
- action: contraindicated, not_recommended, avoid, monitor, recommended, dose_adjust, review
- conditions.op: <, <=, >, >=
- conditions.indication: heart_failure, glycemic_control, hypertension, atrial_fibrillation, chronic_kidney_disease, decompensated_heart_failure, diabetes
- conditions.diabetes_type: type_1, type_2
- conditions.nyha_class: III, IV, III-IV (or NYHA_III style)
- conditions.allergy: a single label from the text (e.g. angioedema, hypersensitivity, or the named drug/class) — not a pipe-joined list
- conditions.bleeding_risk: high, active_bleeding
- conditions.hepatic_impairment: mild, moderate, severe, any

CRITICAL RULES FOR CONDITIONS EXTRACTION:
1. ALWAYS extract conditions when the text states ANY of these:
   - A clinical threshold ("eGFR < 30", "potassium > 5.5", "SBP < 90", "HR < 50", "LVEF <= 40")
   - A population restriction ("pregnancy", "lactation", "pediatric", "elderly")
   - A comorbidity or organ impairment ("renal impairment", "hepatic impairment", "CKD stage 4")
   - An allergy/hypersensitivity ("angioedema", "hypersensitivity to any component")
   - A disease state ("atrial fibrillation", "decompensated heart failure", "bilateral renal artery stenosis", "anuria")
2. When a drug is contraindicated / not recommended / avoid WITHOUT an explicit numeric threshold,
   extract the IMPLICIT qualitative condition from context. Examples:
   - "Do not use in pregnancy" → {"pregnancy": true}
   - "Contraindicated in hypersensitivity to lisinopril" → {"allergy": "lisinopril"}
   - "Contraindicated in patients with anuria" → {"anuria": true}  (do NOT invent eGFR numeric values)
   - "Decompensated HF requiring inotropes" → {"decompensated_hf": true, "inotropic_support": true}
3. For drug-label CONTRAINDICATIONS sections, prefer every statement to carry conditions.
4. If truly no condition can be extracted (rare), set conditions to {} and confidence < 0.7.
5. evidence MUST be copied from the provided text (no paraphrase).
6. Do NOT invent numeric thresholds or drugs not present in the text.
7. Use atrial_fibrillation (boolean), not a separate "af" field.
8. Omit condition fields that are not stated; do not fill every key in the example shape.
9. NEVER output pipe-joined enum lists such as "angioedema|hypersensitivity" or "high|active_bleeding". Those are menus of allowed tokens, not values.
10. confidence between 0.5 and 1.0 based on clarity of the statement.
11. Include only actionable prescribing/safety statements.
12. For drug labels, set drug to the label drug when the claim is drug-specific.
13. Use guideline_recommendation only for guideline sources.
14. dose_recommendation: require a numeric dose (mg/mcg) plus dosing context (starting/target/recommended/titrate/daily). Skip missed-dose instructions, NDC/packaging, and animal/PK-only spans.
15. renal_constraint: require eGFR/CrCl threshold or renal impairment with a prescribing action (avoid/contraindicated/not recommended/reduce dose). Skip hemodialysis/PK-only statements.

Example input:
"Spironolactone is contraindicated when eGFR < 30 mL/min/1.73 m2. ACE inhibitors are contraindicated in pregnancy. Do not use if history of angioedema."

Example output:
{
  "claims": [
    {
      "claim_type": "renal_constraint",
      "evidence": "Spironolactone is contraindicated when eGFR < 30 mL/min/1.73 m2.",
      "drug": "spironolactone",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {"egfr": {"op": "<", "value": 30}}
    },
    {
      "claim_type": "population_constraint",
      "evidence": "ACE inhibitors are contraindicated in pregnancy.",
      "drug": "lisinopril",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {"pregnancy": true}
    },
    {
      "claim_type": "contraindication",
      "evidence": "Do not use if history of angioedema.",
      "drug": "lisinopril",
      "action": "avoid",
      "confidence": 0.9,
      "conditions": {"allergy": "angioedema"}
    }
  ]
}

Example 2 - Complex Dosing:
Input: "For patients with CrCl < 30 mL/min, reduce dose to 25 mg daily. Start at 12.5 mg in patients > 75 years. The target dose is 100 mg daily."

Output:
{
  "claims": [
    {
      "claim_type": "dose_recommendation",
      "evidence": "For patients with CrCl < 30 mL/min, reduce dose to 25 mg daily.",
      "drug": "example_drug",
      "action": "dose_adjust",
      "confidence": 0.92,
      "conditions": {"egfr": {"op": "<", "value": 30}}
    },
    {
      "claim_type": "dose_recommendation",
      "evidence": "Start at 12.5 mg in patients > 75 years.",
      "drug": "example_drug",
      "action": "recommended",
      "confidence": 0.88,
      "conditions": {"age": {"op": ">", "value": 75}}
    },
    {
      "claim_type": "dose_recommendation",
      "evidence": "The target dose is 100 mg daily.",
      "drug": "example_drug",
      "action": "recommended",
      "confidence": 0.9,
      "conditions": {}
    }
  ]
}

Example 3 - Drug Interaction:
Input: "Concomitant use of ACE inhibitors and ARBs is contraindicated due to increased risk of hyperkalemia. SGLT2 inhibitors may potentiate the effect of insulin and increase hypoglycemia risk."

Output:
{
  "claims": [
    {
      "claim_type": "drug_interaction",
      "evidence": "Concomitant use of ACE inhibitors and ARBs is contraindicated due to increased risk of hyperkalemia.",
      "drug": "ace_inhibitor",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {},
      "drug_set_a": ["class:acei"],
      "drug_set_b": ["class:arb"]
    },
    {
      "claim_type": "drug_interaction",
      "evidence": "SGLT2 inhibitors may potentiate the effect of insulin and increase hypoglycemia risk.",
      "drug": "sglt2_inhibitor",
      "action": "monitor",
      "confidence": 0.85,
      "conditions": {},
      "drug_set_a": ["class:sgtl2i"],
      "drug_set_b": ["class:insulin"]
    }
  ]
}

Example 4 - Monitoring:
Input: "Monitor serum potassium and renal function within 1 week of initiation and periodically thereafter. Check BNP levels monthly for dose optimization."

Output:
{
  "claims": [
    {
      "claim_type": "general_monitoring",
      "evidence": "Monitor serum potassium and renal function within 1 week of initiation and periodically thereafter.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.85,
      "conditions": {},
      "monitoring_params": ["potassium", "egfr", "creatinine"]
    },
    {
      "claim_type": "general_monitoring",
      "evidence": "Check BNP levels monthly for dose optimization.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.8,
      "conditions": {},
      "monitoring_params": ["bnp", "nt_probnp"]
    }
  ]
}

Example 5 - Hyperkalemia Risk:
Input: "May cause hyperkalemia, especially in patients with renal impairment or those taking potassium-sparing diuretics. Monitor potassium levels regularly."

Output:
{
  "claims": [
    {
      "claim_type": "hyperkalemia_risk",
      "evidence": "May cause hyperkalemia, especially in patients with renal impairment or those taking potassium-sparing diuretics.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.9,
      "conditions": {"renal_impairment": true}
    }
  ]
}

Example 6 - Guideline Recommendation:
Input: "We recommend initiating SGLT2 inhibitors in all patients with HFrEF regardless of diabetes status (Class I, LOE A). Target doses should be achieved within 2-4 weeks."

Output:
{
  "claims": [
    {
      "claim_type": "guideline_recommendation",
      "evidence": "We recommend initiating SGLT2 inhibitors in all patients with HFrEF regardless of diabetes status.",
      "drug": "sglt2_inhibitor",
      "action": "recommended",
      "confidence": 0.95,
      "conditions": {"hfref": true},
      "class_of_recommendation": "I",
      "level_of_evidence": "A"
    }
  ]
}

Example - DO NOT EXTRACT (INFORMATIONAL - Study Data):
Input: "In clinical trials, 5% of patients experienced headache. The study showed a 20% reduction in mortality (p<0.05)."
Output: {"claims": []}

Example - DO NOT EXTRACT (PREGNANCY CATEGORY):
Input: "Pregnancy Category C: Animal studies showed adverse effects on the fetus."
Output: {"claims": []}

Example - DO NOT EXTRACT (TABLE REFERENCE):
Input: "Table 3: Adverse reactions occurring in >2% of patients"
Output: {"claims": []}

Example - DO NOT EXTRACT (PHARMACOKINETIC DATA):
Input: "The pharmacokinetics of drug X include a bioavailability of 80%, half-life of 12 hours, and Cmax of 2.5 mcg/mL."
Output: {"claims": []}

Example - DO NOT EXTRACT (MECHANISM OF ACTION):
Input: "Mechanism of action: Drug X inhibits the renin-angiotensin-aldosterone system."
Output: {"claims": []}

Example - DO NOT EXTRACT (STUDY COMPARISON):
Input: "Drug X was non-inferior to Drug Y in a randomized controlled trial."
Output: {"claims": []}

Example - CORRECT (PRESCRIPTIVE):
Input: "Do not use in pregnancy. Monitor potassium levels regularly during treatment."
Output: {
  "claims": [
    {
      "claim_type": "population_constraint",
      "evidence": "Do not use in pregnancy.",
      "drug": "example_drug",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {"pregnancy": true}
    },
    {
      "claim_type": "general_monitoring",
      "evidence": "Monitor potassium levels regularly during treatment.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.85,
      "conditions": {}
    }
  ]
}

Example - CORRECT adverse_reaction (PRESCRIPTIVE - warning about risk):
Input: "May cause hyperkalemia. Monitor serum potassium levels during treatment. Can cause renal impairment."
Output: {
  "claims": [
    {
      "claim_type": "adverse_reaction",
      "evidence": "May cause hyperkalemia.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.9,
      "conditions": {}
    },
    {
      "claim_type": "adverse_reaction",
      "evidence": "Can cause renal impairment.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.85,
      "conditions": {}
    }
  ]
}

Example - DO NOT EXTRACT (adverse_reaction - informational only):
Input: "In clinical trials, the most common adverse reactions were headache (10%), dizziness (8%), and fatigue (5%)."
Output: {"claims": []}

Example - CORRECT usage_constraint (PRESCRIPTIVE):
Input: "Use with caution in patients with hepatic impairment. Administer orally once daily."
Output: {
  "claims": [
    {
      "claim_type": "usage_constraint",
      "evidence": "Use with caution in patients with hepatic impairment.",
      "drug": "example_drug",
      "action": "monitor",
      "confidence": 0.9,
      "conditions": {"hepatic_impairment": "any"}
    }
  ]
}

Example - CORRECT population_constraint (PRESCRIPTIVE):
Input: "Not recommended for use in pregnant women. Contraindicated in breastfeeding mothers."
Output: {
  "claims": [
    {
      "claim_type": "population_constraint",
      "evidence": "Not recommended for use in pregnant women.",
      "drug": "example_drug",
      "action": "not_recommended",
      "confidence": 0.95,
      "conditions": {"pregnancy": true}
    },
    {
      "claim_type": "population_constraint",
      "evidence": "Contraindicated in breastfeeding mothers.",
      "drug": "example_drug",
      "action": "contraindicated",
      "confidence": 0.95,
      "conditions": {"lactation": true}
    }
  ]
}
"""

# Critique prompt for two-stage extraction
CLAIM_CRITIQUE_PROMPT = """Review this extraction and identify issues:
- Missing clinical conditions that should be extracted
- Incorrect claim_type classification
- Numeric values that contradict the source text
- Fields filled with placeholder or invented values

Source text: {text}

Previous extraction: {extraction}

If no issues found, respond with: {{"verdict": "approved", "revisions": []}}

If issues found, respond with specific corrections in this format:
{{"verdict": "needs_revision", "revisions": [{{"claim_index": 0, "issue": "description of issue", "suggestion": "how to fix"}}]}}
"""

