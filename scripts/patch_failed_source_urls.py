#!/usr/bin/env python3
"""Patch sources.example.json: PMC/open URLs + DailyMed combo queries."""

from __future__ import annotations

import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "heart_failure" / "sources" / "sources.example.json"

# Verified PMC / open HTML endpoints (bot-reachable).
GUIDELINE_URL_FIXES: dict[str, dict] = {
    "acc_aha_2019_primary_prevention_guideline": {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7734661/",
        "source_type": "guideline_html",
        "artifact_kind": "html",
        "target_path": "raw/guidelines/ascvd_prevention/2019 ACC AHA Primary Prevention Guideline.html",
    },
    "acc_aha_2018_cholesterol_guideline": {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7403606/",
        "source_type": "guideline_html",
        "artifact_kind": "html",
        "target_path": "raw/guidelines/dyslipidemia/2018 ACC AHA Cholesterol Guideline.html",
    },
    "acc_aha_2024_pad_guideline": {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12782132/",
        "source_type": "guideline_html",
        "artifact_kind": "html",
    },
    "esc_2021_valvular_heart_disease": {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9725093/",
        "source_type": "guideline_html",
        "artifact_kind": "html",
        "target_path": "raw/guidelines/valvular_heart_disease/2021 ESC EACTS Valvular Heart Disease.html",
    },
}

ADA_PMC: dict[str, str] = {
    "ada_2024_population_health": "PMC10725798",
    "ada_2024_diagnosis_classification": "PMC10725812",
    "ada_2024_prevention_delay": "PMC10725807",
    "ada_2024_comprehensive_medical_evaluation": "PMC10725809",
    "ada_2024_health_behaviors": "PMC10725816",
    "ada_2024_glycemic_goals": "PMC10725808",
    "ada_2024_diabetes_technology": "PMC10725813",
    "ada_2024_obesity_management": "PMC10725806",
    "ada_2024_pharmacologic_treatment": "PMC10725810",
    "ada_2024_cv_risk_management": "PMC10725811",
    "ada_2024_ckd_risk_management": "PMC10725805",
    "ada_2024_retinopathy_neuropathy": "PMC10725803",
    "ada_2024_older_adults": "PMC10725804",
    "ada_2024_children_adolescents": "PMC10725814",
    "ada_2024_pregnancy": "PMC10725801",
    "ada_2024_hospital_care": "PMC10725815",
    "ada_2024_diabetes_advocacy": "PMC10725796",
}

# Still publisher-gated (no reliable PMC). Keep publisher URL but add html_url fallback
# to Europe PMC abstract page for provenance; acquire may still fail until manual S3 upload.
PUBLISHER_GATED_FALLBACK: dict[str, dict] = {
    "esc_2021_cvd_prevention_guideline": {"pmid": "34458905"},
    "esc_2022_cardio_oncology": {"pmid": "36017568"},
    "acc_aha_2020_hcm_guideline": {"pmid": "33215931"},
    "acc_aha_2022_chest_pain_guideline": {"pmid": "34709879"},
    "acc_aha_2021_coronary_revascularization": {"pmid": "34882435"},
    "aha_acc_2023_chronic_cad_guideline": {"pmid": "37471501"},
    "esc_2019_chronic_coronary_syndromes": {"pmid": "31504439"},
    "acc_expert_consensus_hf_optimization_2021": {"pmid": "33446410"},
    "acc_expert_consensus_hfpef_2023": {"pmid": "37137593"},
    "aha_scientific_statement_sglt2i_2020": {"pmid": "32981345"},
    "esc_2023_hf_focused_update": {"pmid": "37622666"},
    "acc_aha_2020_valvular_guideline": {"pmid": "33332150"},
}

DRUG_QUERY_FIXES: dict[str, dict] = {
    "sacubitril_and_valsartan_label": {
        "query": "sacubitril and valsartan",
        "required_terms": ["SACUBITRIL", "VALSARTAN"],
    },
    "hydralazine_and_isosorbide_dinitrate_label": {
        "query": "hydralazine isosorbide",
        "required_terms": ["HYDRALAZINE", "ISOSORBIDE"],
    },
    "spironolactone_and_hydrochlorothiazide_label": {
        "query": "spironolactone and hydrochlorothiazide",
        "required_terms": ["SPIRONOLACTONE", "HYDROCHLOROTHIAZIDE"],
    },
}


def main() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    updated = 0
    for source in registry.get("sources", []):
        sid = source.get("source_id")
        if sid in GUIDELINE_URL_FIXES:
            source.update(GUIDELINE_URL_FIXES[sid])
            updated += 1
        if sid in ADA_PMC:
            pmc = ADA_PMC[sid]
            source["url"] = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/"
            source["source_type"] = "guideline_html"
            source["artifact_kind"] = "html"
            tp = str(source.get("target_path") or "")
            if tp.endswith(".pdf"):
                source["target_path"] = tp[:-4] + ".html"
            updated += 1
        if sid in PUBLISHER_GATED_FALLBACK:
            pmid = PUBLISHER_GATED_FALLBACK[sid]["pmid"]
            # Prefer Europe PMC HTML article page as secondary attempt.
            source["html_url"] = f"https://europepmc.org/article/MED/{pmid}"
            source["notes"] = (
                "Publisher blocks automated download (HTTP 403). "
                "Upload the official PDF manually to the raw S3 key if acquire fails."
            )
            updated += 1
        if sid in DRUG_QUERY_FIXES:
            source.update(DRUG_QUERY_FIXES[sid])
            updated += 1

    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {updated} source fields in {REGISTRY_PATH}")


if __name__ == "__main__":
    main()
