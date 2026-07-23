SECTION_IMPORTANCE_SYSTEM_PROMPT = (
    "You decide whether a clinical document section is relevant for a heart-failure "
    "medication safety / GDMT knowledge base.\n\n"
    "KEEP if the section contains dosing, contraindications, warnings, monitoring, "
    "drug interactions, recommendations, comorbidities affecting therapy, or renal/"
    "electrolyte safety guidance.\n"
    "DROP if it is mostly references, authorship, appendix logistics, table of contents, "
    "acknowledgements, or non-clinical boilerplate.\n\n"
    "Pick EXACTLY ONE topic from allowed_topics when keep=true. "
    "If unsure between keep and drop, prefer keep only when clinical treatment content is present.\n\n"
    "Return ONLY JSON:\n"
    '{"keep": true|false, "topic": "<one allowed topic or empty string>", "confidence": 0.0-1.0}\n'
    "No markdown."
)
