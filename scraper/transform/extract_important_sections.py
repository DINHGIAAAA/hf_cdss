from scraper.io.jsonl import read_jsonl, write_jsonl
import argparse
import json
import logging
import re
from pathlib import Path

from scraper.transform.text_normalization import normalize_inline_text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

DRUG_SECTION_ALIASES = {
    "INDICATIONS AND USAGE": {
        "INDICATIONS AND USAGE", "INDICATIONS & USAGE", "INDICATIONS",
        "THERAPEUTIC INDICATIONS", "INDICATIONS AND CLINICAL USE",
    },
    "DOSAGE AND ADMINISTRATION": {
        "DOSAGE AND ADMINISTRATION", "DOSAGE & ADMINISTRATION",
        "DOSAGE", "ADMINISTRATION", "DOSE AND FREQUENCY",
    },
    "CONTRAINDICATIONS": {"CONTRAINDICATIONS", "CONTRAINDICATION"},
    "WARNINGS AND PRECAUTIONS": {
        "WARNINGS AND PRECAUTIONS", "WARNINGS", "PRECAUTIONS",
        "BOXED WARNING", "ADVERSE WARNINGS",
    },
    "ADVERSE REACTIONS": {
        "ADVERSE REACTIONS", "ADVERSE EVENTS", "SIDE EFFECTS",
        "UNToward EVENTS", "TOXICITY",
    },
    "DRUG INTERACTIONS": {
        "DRUG INTERACTIONS", "DRUG INTERACTION", "DRUG-DRUG INTERACTIONS",
        "DRUG-FOOD INTERACTIONS", "INTERACTIONS",
    },
    "USE IN SPECIFIC POPULATIONS": {
        "USE IN SPECIFIC POPULATIONS", "SPECIFIC POPULATIONS",
    },
    "RENAL IMPAIRMENT": {
        "RENAL IMPAIRMENT", "RENAL DYSFUNCTION", "KIDNEY IMPAIRMENT",
        "DOSAGE IN RENAL IMPAIRMENT", "DOSE ADJUSTMENT RENAL",
    },
    # NEW SECTIONS
    "CLINICAL PHARMACOLOGY": {
        "CLINICAL PHARMACOLOGY", "PHARMACOLOGY", "PHARMACODYNAMICS",
        "PHARMACOKINETICS", "PK/PD", "MECHANISM OF ACTION",
    },
    "CLINICAL STUDIES": {
        "CLINICAL STUDIES", "CLINICAL TRIALS", "TRIALS",
        "EFFICACY", "EFFECTIVENESS", "STUDY RESULTS",
    },
    "OVERDOSAGE": {
        "OVERDOSAGE", "OVERDOSE", "TOXICITY", "POISONING",
        "MANAGEMENT OF OVERDOSE",
    },
    "DESCRIPTION": {
        "DESCRIPTION", "PRODUCT DESCRIPTION", "CHEMICAL DESCRIPTION",
        "ACTIVE INGREDIENT", "FORMULATION",
    },
    "BLACK BOX WARNING": {
        "BLACK BOX WARNING", "BOXED WARNING", "SERIOUS WARNINGS",
    },
    "PATIENT COUNSELING": {
        "PATIENT COUNSELING", "PATIENT INFORMATION", "PATIENT EDUCATION",
    },
    "HOW SUPPLIED": {
        "HOW SUPPLIED", "DOSAGE FORMS", "AVAILABILITY",
        "PACKAGING", "STORAGE",
    },
    "GERIATRIC USE": {
        "GERIATRIC USE", "ELDERLY", "OLDER ADULTS",
    },
    "PEDIATRIC USE": {
        "PEDIATRIC USE", "CHILDREN", "PEDIATRICS", "ADOLESCENTS",
    },
    "PREGNANCY": {
        "PREGNANCY", "PREGNANCY CATEGORY", "TERATOGENICITY",
    },
    "NURSING MOTHERS": {
        "NURSING MOTHERS", "LACTATION", "BREASTFEEDING",
    },
    "TOXICOLOGY": {
        "TOXICOLOGY", "CARCINOGENESIS", "MUTAGENESIS",
        "IMPAIRMENT OF FERTILITY",
    },
}

GUIDELINE_TOPICS = {
    "recommendations": ("recommendation", "recommendations", "cor loe", "class of recommendation"),
    "drug therapy": ("drug therapy", "pharmacologic", "pharmacological", "medication", "treatment with"),
    "dosing": (
        "dosing",
        "dose adjustment",
        "dose titration",
        "titration",
        "starting dose",
        "target dose",
        "maintenance dose",
    ),
    "monitoring": (
        "monitoring",
        "laboratory monitoring",
        "follow-up",
        "renal function test",
        "lab monitoring",
        "safety monitoring",
    ),
    "drug interactions": (
        "drug interaction",
        "drug-drug",
        "drug–drug",
        "concomitant use",
        "co-administration",
        "coadministration",
    ),
    "warnings": (
        "warning",
        "boxed warning",
        "black box",
        "precaution",
        "serious risk",
    ),
    "contraindications": ("contraindication", "contraindications", "contraindicated"),
    "comorbidities": ("comorbidity", "comorbidities", "coexisting", "concomitant"),
    "renal dysfunction": (
        "renal dysfunction",
        "kidney dysfunction",
        "worsening renal",
        "egfr",
        "ckd",
        "renal impairment",
        "hepatic impairment",
    ),
    "hyperkalemia": ("hyperkalemia", "hyperkalaemia", "serum potassium", "potassium"),
    "atrial fibrillation": ("atrial fibrillation", "afib", "af "),
    "diabetes": ("diabetes", "diabetic", "glycemic", "glycaemic", "hba1c"),
    "hypertension": ("hypertension", "blood pressure", "antihypertensive"),
    # NEW TOPICS
    "heart failure phenotypes": (
        "hfrEF", "hfref", "hfmrEF", "hfPef", "reduced ejection fraction",
        "mid-range ejection fraction", "preserved ejection fraction", "phenotype",
    ),
    "biomarkers": (
        "bnp", "nt-probnp", "ntprobnp", "brain natriuretic", "troponin",
        "galectin-3", "st2", "biomarker", "serum marker",
    ),
    "liver function": (
        "lft", "liver function", "alt", "ast", "bilirubin", "hepatic",
        "transaminases", "liver enzymes", "hepatotoxicity",
    ),
    "electrolyte abnormalities": (
        "hyponatremia", "hypernatremia", "hypokalemia", "hyperkalemia",
        "low sodium", "high sodium", "electrolyte", "magnesium", "phosphate",
    ),
    "volume status": (
        "volume overload", "congestion", "congestive", "fluid overload",
        "edema", "weight gain", "jugular venous", "jvp", "rales",
    ),
    "device therapy": (
        "icd", "crt", "pacemaker", "defibrillator", "cardiac resynchronization",
        "lvad", "mechanical circulatory support",
    ),
    "acute decompensation": (
        "acute decompensated", "adhf", "acute hf", "worsening hf",
        "hf exacerbation", "flash pulmonary edema", "cardiogenic shock",
    ),
    "quality of life": (
        "quality of life", "qol", "symptom burden", "functional status",
        "exercise capacity", "six-minute walk", "dyspnea", "fatigue",
    ),
    "hospitalization": (
        "hospitalization", "hospital admission", "readmission",
        "length of stay", "inpatient", "outpatient",
    ),
    "mortality": (
        "mortality", "death", "survival", "cardiovascular death",
        "sudden cardiac death", "all-cause mortality",
    ),
    "guideline adherence": (
        "guideline-directed", "gdmt", "optimal therapy", "target dose",
        "evidence-based", "protocol", "pathway",
    ),
    "special populations": (
        "elderly", "geriatric", "pediatric", "pregnant", "renal failure",
        "hepatic impairment", "frail", "overweight", "obese",
    ),
    "medication adherence": (
        "adherence", "compliance", "persistence", "non-adherence",
        "medication possession", "refill", "discontinuation",
    ),
    "race and ethnicity": (
        "african american", "black", "hispanic", "asian", "race",
        "ethnicity", "cultural", "socioeconomic", "disparities",
    ),
    "clinical_numbers": (
        "egfr <", "egfr >", "egfr ≤", "egfr ≥",
        "crcl <", "crcl >", "crcl ≤", "crcl ≥",
        "k+ >", "k+ <", "potassium >", "potassium <",
        "bnp >", "nt-probnp >", "ntprobnp >",
        "lvef <", "lvEF ≤", "lvEF >", "lvEF ≥",
        "nyha class", "nyha i", "nyha ii", "nyha iii", "nyha iv",
        "systolic bp <", "sbp <", "dbp <",
        "heart rate <", "hr <",
        "hba1c >", "hba1c <",
        "qtc >", "qtc <",
        "hb <", "hemoglobin <",
        "alt >", "ast >", "bilirubin >",
        "sodium <", "hyponatremia <",
    ),
}

def normalize(value: str) -> str:
    return normalize_inline_text(value).upper()

def drug_matches(record: dict) -> list[str]:
    section = normalize(record.get("section", ""))
    text = normalize(record.get("text", ""))
    matches = []

    for canonical, aliases in DRUG_SECTION_ALIASES.items():
        # Exact title or hierarchical SPL path ("DOSAGE AND ADMINISTRATION / HEART FAILURE").
        if section in aliases or any(alias in section for alias in aliases):
            matches.append(canonical)
            continue
        if canonical == "RENAL IMPAIRMENT" and "RENAL IMPAIRMENT" in text:
            matches.append(canonical)

    return matches

def guideline_matches(record: dict) -> list[str]:
    haystack = f"{record.get('section', '')} {record.get('text', '')}".lower()
    return [
        topic
        for topic, terms in GUIDELINE_TOPICS.items()
        if any(term in haystack for term in terms)
    ]

from dataclasses import dataclass, field

from scraper.kg.identifiers import section_id_for_record


@dataclass
class SectionHierarchy:
    """Track hierarchical relationships between document sections."""
    root: str
    parent: str | None = None
    depth: int = 0
    path: list[str] = field(default_factory=list)

    @property
    def full_path(self) -> str:
        return " > ".join(self.path) if self.path else self.root


def parse_section_hierarchy(section_title: str) -> SectionHierarchy:
    """Parse section title into hierarchical components.

    Examples:
    - "DOSAGE AND ADMINISTRATION" -> root="DOSAGE AND ADMINISTRATION"
    - "WARNINGS AND PRECAUTIONS / HYPERKALEMIA" -> root="WARNINGS", parent="HYPERKALEMIA"
    """
    parts = [p.strip() for p in section_title.split("/")]

    if len(parts) == 1:
        return SectionHierarchy(root=parts[0])

    return SectionHierarchy(
        root=parts[0],
        parent=parts[1] if len(parts) > 1 else None,
        depth=len(parts) - 1,
        path=parts
    )


def mark_record(record: dict, matched_topics: list[str]) -> dict:
    output = dict(record)
    metadata = dict(output.get("metadata") or {})
    metadata["matched_important_topics"] = matched_topics

    # Add section hierarchy
    section_title = record.get("section", "")
    hierarchy = parse_section_hierarchy(section_title)
    metadata["section_hierarchy"] = {
        "root": hierarchy.root,
        "parent": hierarchy.parent,
        "depth": hierarchy.depth,
        "full_path": hierarchy.full_path,
        "is_nested": hierarchy.depth > 0,
    }

    section_id_value = section_id_for_record(output)
    metadata["section_id"] = section_id_value
    output["section_id"] = section_id_value
    output["metadata"] = metadata
    return output

def dedupe_sections(records: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    unique: list[dict] = []
    for record in records:
        key = (
            record.get("document_id"),
            record.get("section"),
            (record.get("text") or "")[:500],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique

def collect_section_files(sections_dir: Path) -> list[Path]:
    candidates = [
        sections_dir / "guideline_sections.jsonl",
        sections_dir / "guideline_html_sections.jsonl",
        sections_dir / "drug_label_sections.jsonl",
    ]
    return [path for path in candidates if path.exists()]

def main() -> None:
    parser = argparse.ArgumentParser(description="Filter important clinical sections from parsed guideline and label sections.")
    parser.add_argument("--sections-dir", default="processed/sections", type=Path)
    parser.add_argument("--output", default="processed/sections/important_sections.jsonl", type=Path)
    args = parser.parse_args()

    records: list[dict] = []
    for path in collect_section_files(args.sections_dir):
        loaded = read_jsonl(path)
        records.extend(loaded)
        logger.info("Loaded %s sections from %s", len(loaded), path.name)
    records = dedupe_sections(records)
    logger.info("Total %s unique sections to filter", len(records))

    from scraper.semantic.section_filter import filter_important_sections

    important = filter_important_sections(records)
    write_jsonl(important, args.output)
    print(f"Wrote {len(important)} important sections to {args.output}")

if __name__ == "__main__":
    main()
