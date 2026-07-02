"""Prototype sentences for semantic section relevance scoring."""

from __future__ import annotations

DRUG_SECTION_PROTOTYPES: dict[str, list[str]] = {
    "INDICATIONS AND USAGE": [
        "Indications and usage for this drug in heart failure or related conditions.",
        "Approved therapeutic indications and labeled uses.",
    ],
    "DOSAGE AND ADMINISTRATION": [
        "Recommended starting dose, titration, and administration instructions.",
        "Dosing adjustments for renal impairment or special populations.",
    ],
    "CONTRAINDICATIONS": [
        "This drug is contraindicated in patients with specific conditions.",
        "Do not use in patients who have hypersensitivity or absolute contraindications.",
    ],
    "WARNINGS AND PRECAUTIONS": [
        "Warnings and precautions including boxed warnings and serious risks.",
        "Monitor patients for hypotension, hyperkalemia, or renal dysfunction.",
    ],
    "ADVERSE REACTIONS": [
        "Common and serious adverse reactions observed in clinical trials.",
    ],
    "DRUG INTERACTIONS": [
        "Drug-drug interactions with concomitant medications and CYP inhibitors.",
    ],
    "USE IN SPECIFIC POPULATIONS": [
        "Use in pregnancy, lactation, pediatrics, geriatrics, and renal impairment.",
    ],
    "RENAL IMPAIRMENT": [
        "Dose modification or contraindication in renal impairment based on eGFR.",
    ],
}

GUIDELINE_TOPIC_PROTOTYPES: dict[str, list[str]] = {
    "recommendations": [
        "Clinical practice recommendation with class of recommendation and level of evidence.",
        "We recommend initiating guideline-directed medical therapy.",
    ],
    "drug therapy": [
        "Pharmacologic treatment options including ACE inhibitors, beta blockers, and SGLT2 inhibitors.",
        "Initiation and optimization of heart failure drug therapy.",
    ],
    "contraindications": [
        "Treatment is contraindicated in patients with specific comorbidities.",
    ],
    "comorbidities": [
        "Management of comorbid conditions such as diabetes, CKD, or atrial fibrillation.",
    ],
    "renal dysfunction": [
        "Therapy adjustments when eGFR declines or chronic kidney disease is present.",
    ],
    "hyperkalemia": [
        "Serum potassium thresholds and hyperkalemia risk with RAAS inhibitors or MRA.",
    ],
    "atrial fibrillation": [
        "Anticoagulation and rate control in heart failure with atrial fibrillation.",
    ],
    "diabetes": [
        "Glycemic management and SGLT2 inhibitor use in patients with diabetes.",
    ],
    "hypertension": [
        "Blood pressure targets and antihypertensive therapy in heart failure.",
    ],
}
