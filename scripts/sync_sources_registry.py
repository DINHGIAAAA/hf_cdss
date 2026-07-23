#!/usr/bin/env python3
"""Sync sources.example.json guidelines (+ drug_label_xml) with files on disk."""

from __future__ import annotations

import json
from pathlib import Path

from scraper.scripts.sources_registry import (
    REGISTRY_PATH,
    normalize_registry,
    validate_registry,
    write_registry,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "heart_failure"
ALIASES = DATA / "config" / "drug_aliases.json"

# Known metadata for on-disk guideline files (relative to raw/guidelines/).
GUIDELINE_META: dict[str, dict] = {
    # heart_failure
    "heart_failure/2022 AHA_ACC_HFSA Guideline for the Management of Heart Failure.html": {
        "source_id": "aha_acc_hfsa_2022_hf_guideline",
        "title": "2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure",
        "publisher": "ACC/AHA/HFSA",
        "topic": "heart_failure",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9238257/",
    },
    "heart_failure/2021 ESC guidelines HF.pdf": {
        "source_id": "esc_2021_hf_guideline",
        "title": "2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure",
        "publisher": "ESC",
        "topic": "heart_failure",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8490362/",
    },
    "heart_failure/2023 Focused Update of the ESC Guidelines.pdf": {
        "source_id": "esc_2023_hf_focused_update",
        "title": "2023 Focused Update of the 2021 ESC Guidelines for the diagnosis and treatment of acute and chronic heart failure",
        "publisher": "ESC",
        "topic": "heart_failure",
        "url": "https://academic.oup.com/eurheartj/article/44/37/3627/7246598",
    },
    # atrial_fibrillation
    "atrial_fibrillation/2023 ACC AHA ACCP HRS Atrial Fibrillation Guideline.html": {
        "source_id": "acc_aha_2023_af_guideline",
        "title": "2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation",
        "publisher": "ACC/AHA/ACCP/HRS",
        "topic": "atrial_fibrillation",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11104284/",
    },
    "atrial_fibrillation/2024 ESC Atrial Fibrillation Guidelines.pdf": {
        "source_id": "esc_2024_af_guideline",
        "title": "2024 ESC Guidelines for the Management of Atrial Fibrillation",
        "publisher": "ESC",
        "topic": "atrial_fibrillation",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11379312/",
    },
    # ckd
    "ckd/KDIGO-2024-CKD-Guideline.pdf": {
        "source_id": "kdigo_2024_ckd_guideline",
        "title": "2024 KDIGO Clinical Practice Guideline for the Evaluation and Management of Chronic Kidney Disease",
        "publisher": "KDIGO",
        "topic": "ckd",
        "url": "https://kdigo.org/guidelines/ckd-evaluation-and-management/",
    },
    "ckd/ADA-KDIGO-2022-Diabetes-CKD-Consensus.pdf": {
        "source_id": "ada_kdigo_2022_diabetes_ckd_consensus",
        "title": "Diabetes Management in Chronic Kidney Disease: A Consensus Report by the ADA and KDIGO",
        "publisher": "ADA/KDIGO",
        "topic": "ckd",
        "url": "https://kdigo.org/guidelines/diabetes-ckd/",
    },
    # hypertension
    "hypertension/2017 ACC AHA Hypertension Guideline.pdf": {
        "source_id": "acc_aha_2017_bp_guideline",
        "title": "2017 ACC/AHA Guideline for the Prevention, Detection, Evaluation, and Management of High Blood Pressure in Adults",
        "publisher": "ACC/AHA",
        "topic": "hypertension",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6676913/",
    },
    # dyslipidemia
    "dyslipidemia/2018 ACC AHA Cholesterol Guideline.html": {
        "source_id": "acc_aha_2018_cholesterol_guideline",
        "title": "2018 ACC/AHA Guideline on the Management of Blood Cholesterol",
        "publisher": "ACC/AHA",
        "topic": "dyslipidemia",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7403606/",
    },
    # ascvd prevention
    "ascvd_prevention/2019 ACC AHA Primary Prevention Guideline.html": {
        "source_id": "acc_aha_2019_primary_prevention_guideline",
        "title": "2019 ACC/AHA Guideline on the Primary Prevention of Cardiovascular Disease",
        "publisher": "ACC/AHA",
        "topic": "ascvd_prevention",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7734661/",
    },
    "ascvd_prevention/2021 ESC CVD Prevention Guidelines.pdf": {
        "source_id": "esc_2021_cvd_prevention_guideline",
        "title": "2021 ESC Guidelines on cardiovascular disease prevention in clinical practice",
        "publisher": "ESC",
        "topic": "ascvd_prevention",
        "url": "https://academic.oup.com/eurheartj/article/42/34/3227/6358713",
    },
    # cardiomyopathy / valvular / PAD
    "cardiomyopathy/2020 ACC AHA Hypertrophic Cardiomyopathy Guideline.pdf": {
        "source_id": "acc_aha_2020_hcm_guideline",
        "title": "2020 ACC/AHA Guideline for the Diagnosis and Treatment of Patients With Hypertrophic Cardiomyopathy",
        "publisher": "ACC/AHA",
        "topic": "cardiomyopathy",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000937",
    },
    "valvular_heart_disease/2020 ACC AHA Valvular Heart Disease Guideline.pdf": {
        "source_id": "acc_aha_2020_valvular_guideline",
        "title": "2020 ACC/AHA Guideline for the Management of Patients With Valvular Heart Disease",
        "publisher": "ACC/AHA",
        "topic": "valvular_heart_disease",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000923",
    },
    "peripheral_artery_disease/2024 ACC AHA PAD Guideline.html": {
        "source_id": "acc_aha_2024_pad_guideline",
        "title": "2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease",
        "publisher": "ACC/AHA",
        "topic": "peripheral_artery_disease",
        "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001251",
    },
    # comorbidities
    "copd/GOLD 2024 COPD Report.pdf": {
        "source_id": "gold_2024_copd_report",
        "title": "Global Strategy for Prevention, Diagnosis and Management of COPD 2024 Report",
        "publisher": "GOLD",
        "topic": "copd",
        "url": "https://goldcopd.org/2024-gold-report/",
    },
    "sleep_apnea/AASM 2017 OSA Diagnostic Guideline.html": {
        "source_id": "aasm_2017_osa_diagnostic_guideline",
        "title": "Clinical Practice Guideline for Diagnostic Testing for Adult Obstructive Sleep Apnea (AASM)",
        "publisher": "AASM",
        "topic": "sleep_apnea",
        "url": "https://aasm.org/clinical-resources/practice-standards/practice-guidelines/",
    },
}

# ADA 2024 chapter pages already on disk
ADA_2024_CHAPTERS: dict[str, str] = {
    "ada_2024_population_health": "Improving Care and Promoting Health in Populations",
    "ada_2024_diagnosis_classification": "Diagnosis and Classification of Diabetes",
    "ada_2024_prevention_delay": "Prevention or Delay of Diabetes and Associated Comorbidities",
    "ada_2024_comprehensive_medical_evaluation": "Comprehensive Medical Evaluation and Assessment of Comorbidities",
    "ada_2024_health_behaviors": "Facilitating Positive Health Behaviors and Well-being",
    "ada_2024_glycemic_goals": "Glycemic Goals and Hypoglycemia",
    "ada_2024_diabetes_technology": "Diabetes Technology",
    "ada_2024_obesity_management": "Obesity and Weight Management",
    "ada_2024_pharmacologic_treatment": "Pharmacologic Approaches to Glycemic Treatment",
    "ada_2024_cv_risk_management": "Cardiovascular Disease and Risk Management",
    "ada_2024_ckd_risk_management": "Chronic Kidney Disease and Risk Management",
    "ada_2024_retinopathy_neuropathy": "Retinopathy, Neuropathy, and Foot Care",
    "ada_2024_older_adults": "Older Adults",
    "ada_2024_children_adolescents": "Children and Adolescents",
    "ada_2024_pregnancy": "Management of Diabetes in Pregnancy",
    "ada_2024_hospital_care": "Diabetes Care in the Hospital",
    "ada_2024_diabetes_advocacy": "Diabetes Advocacy",
}

# PMC mirrors for ADA Standards of Care 2024 (bot-reachable).
ADA_2024_PMC: dict[str, str] = {
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


def _guideline_entry(rel: str, meta: dict) -> dict:
    suffix = Path(rel).suffix.lower()
    source_type = "guideline_pdf" if suffix == ".pdf" else "guideline_html"
    artifact_kind = "pdf" if suffix == ".pdf" else "html"
    return {
        "source_id": meta["source_id"],
        "title": meta["title"],
        "source_type": source_type,
        "download_strategy": "direct_url",
        "publisher": meta["publisher"],
        "topic": meta["topic"],
        "artifact_kind": artifact_kind,
        "url": meta["url"],
        "target_path": f"raw/guidelines/{rel}".replace("\\", "/"),
        "license_note": "Official publisher material. Verify terms before redistribution.",
    }


def _ada_entries() -> list[dict]:
    out = []
    for source_id, chapter in ADA_2024_CHAPTERS.items():
        fname = f"{source_id}.html"
        path = DATA / "raw" / "guidelines" / "diabetes" / fname
        if not path.is_file():
            continue
        out.append(
            {
                "source_id": source_id,
                "title": f"Standards of Care in Diabetes—2024: {chapter}",
                "source_type": "guideline_html",
                "download_strategy": "direct_url",
                "publisher": "ADA",
                "topic": "diabetes",
                "artifact_kind": "html",
                "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{ADA_2024_PMC[source_id]}/",
                "target_path": f"raw/guidelines/diabetes/{fname}",
                "license_note": "Official publisher material. Verify terms before redistribution.",
            }
        )
    return out


def _drug_label_xml_entries() -> list[dict]:
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    label_root = DATA / "raw" / "drug_labels"
    entries = []
    for pipeline_id, entry in sorted(aliases.items()):
        # Prefer exact folder; hydralazine covered by hydralazine_hydrochloride
        folder = pipeline_id
        xml = label_root / folder / f"{folder}_label.xml"
        if not xml.is_file() and pipeline_id == "hydralazine":
            folder = "hydralazine_hydrochloride"
            xml = label_root / folder / f"{folder}_label.xml"
        if not xml.is_file():
            continue
        display = entry.get("display_name") or pipeline_id.replace("_", " ")
        query = str(display)
        entries.append(
            {
                "source_id": f"{pipeline_id}_label",
                "title": f"{display.title()} - FDA Label",
                "source_type": "drug_label_xml",
                "download_strategy": "dailymed_spl",
                "publisher": "FDA DailyMed",
                "topic": "drug_label",
                "slug": pipeline_id,
                "query": query,
                "required_terms": [query.upper()],
                "target_path": f"raw/drug_labels/{folder}/{folder}_label.xml",
                "license_note": "Public domain FDA label. Safe for ingestion.",
            }
        )
    return entries


def main() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))

    # Keep non-guideline / non-drug-label sources if any; drop old guideline_* and drug_label_*
    kept = [
        s
        for s in registry.get("sources", [])
        if not str(s.get("source_type", "")).startswith("guideline_")
        and not str(s.get("source_type", "")).startswith("drug_label_")
    ]

    guidelines: list[dict] = []
    for rel, meta in GUIDELINE_META.items():
        path = DATA / "raw" / "guidelines" / rel
        if not path.is_file():
            print(f"WARN missing on disk, still registering: {rel}")
        guidelines.append(_guideline_entry(rel, meta))
    guidelines.extend(_ada_entries())

    # Retain a few high-value HF adjuncts that were in old registry but may lack local files
    for optional in (
        {
            "source_id": "arn_treatment_hf_guideline",
            "title": "ARNi in Heart Failure - Clinical Guidance",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "PMC/Open access clinical guidance",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6834856/",
            "target_path": "raw/guidelines/heart_failure/ARNi Heart Failure Clinical Guidance.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "gdmt_implementation_hfsa",
            "title": "GDMT Implementation in Heart Failure - HFSA Best Practices",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "HFSA",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7587252/",
            "target_path": "raw/guidelines/heart_failure/GDMT Implementation HFSA.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "iron_deficiency_hf_guideline",
            "title": "Iron Deficiency in Heart Failure - ESC Clinical Guidance",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "ESC",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7398003/",
            "target_path": "raw/guidelines/heart_failure/Iron Deficiency HF ESC.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "acc_expert_consensus_hfpef_2023",
            "title": "2023 ACC Expert Consensus Decision Pathway on Management of Heart Failure With Preserved Ejection Fraction",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "ACC",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://www.jacc.org/doi/10.1016/j.jacc.2023.03.393",
            "target_path": "raw/guidelines/heart_failure/2023 ACC ECDP HFpEF.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "acc_expert_consensus_hf_optimization_2021",
            "title": "2021 Update to the 2017 ACC Expert Consensus Decision Pathway for Optimization of Heart Failure Treatment",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "ACC",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://www.jacc.org/doi/10.1016/j.jacc.2020.11.022",
            "target_path": "raw/guidelines/heart_failure/2021 ACC ECDP HF Optimization.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "aha_scientific_statement_sglt2i_2020",
            "title": "Cardiorenal Protection With the Newer Antidiabetic Agents in Patients With Diabetes and CKD / HF (AHA Scientific Statement context for SGLT2i)",
            "source_type": "guideline_html",
            "download_strategy": "direct_url",
            "publisher": "AHA",
            "topic": "heart_failure",
            "artifact_kind": "html",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000000920",
            "target_path": "raw/guidelines/heart_failure/AHA SGLT2i Cardiorenal Statement.html",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "esc_2019_chronic_coronary_syndromes",
            "title": "2019 ESC Guidelines for the diagnosis and management of chronic coronary syndromes",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "ESC",
            "topic": "coronary_disease",
            "artifact_kind": "pdf",
            "url": "https://academic.oup.com/eurheartj/article/41/3/407/5556137",
            "target_path": "raw/guidelines/coronary_disease/2019 ESC Chronic Coronary Syndromes.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "acc_aha_2021_coronary_revascularization",
            "title": "2021 ACC/AHA/SCAI Guideline for Coronary Artery Revascularization",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "ACC/AHA/SCAI",
            "topic": "coronary_disease",
            "artifact_kind": "pdf",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001038",
            "target_path": "raw/guidelines/coronary_disease/2021 ACC AHA SCAI Coronary Revascularization.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "esc_2022_cardio_oncology",
            "title": "2022 ESC Guidelines on cardio-oncology",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "ESC",
            "topic": "cardio_oncology",
            "artifact_kind": "pdf",
            "url": "https://academic.oup.com/eurheartj/article/43/41/4229/6675670",
            "target_path": "raw/guidelines/cardio_oncology/2022 ESC Cardio-Oncology Guidelines.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "acc_aha_2022_chest_pain_guideline",
            "title": "2021 AHA/ACC/ASE/CHEST/SAEM/SCCT/SCMR Guideline for the Evaluation and Diagnosis of Chest Pain",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "AHA/ACC",
            "topic": "chest_pain",
            "artifact_kind": "pdf",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001029",
            "target_path": "raw/guidelines/chest_pain/2021 AHA ACC Chest Pain Guideline.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "esc_2021_valvular_heart_disease",
            "title": "2021 ESC/EACTS Guidelines for the management of valvular heart disease",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "ESC/EACTS",
            "topic": "valvular_heart_disease",
            "artifact_kind": "pdf",
            "url": "https://academic.oup.com/eurheartj/article/43/7/561/6358470",
            "target_path": "raw/guidelines/valvular_heart_disease/2021 ESC EACTS Valvular Heart Disease.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
        {
            "source_id": "aha_acc_2023_chronic_cad_guideline",
            "title": "2023 AHA/ACC/ACCP/ASPC/NLA/PCNA Guideline for the Management of Patients With Chronic Coronary Disease",
            "source_type": "guideline_pdf",
            "download_strategy": "direct_url",
            "publisher": "AHA/ACC",
            "topic": "coronary_disease",
            "artifact_kind": "pdf",
            "url": "https://www.ahajournals.org/doi/10.1161/CIR.0000000000001168",
            "target_path": "raw/guidelines/coronary_disease/2023 AHA ACC Chronic Coronary Disease.pdf",
            "license_note": "Official publisher material. Verify terms before redistribution.",
        },
    ):
        if optional["source_id"] not in {g["source_id"] for g in guidelines}:
            guidelines.append(optional)

    drugs = _drug_label_xml_entries()

    registry["version"] = 6
    registry["notes"] = (
        "Curated HF CDSS sources: cardiology/comorbidity guidelines synced to on-disk "
        "raw/guidelines files, plus FDA DailyMed drug_label_xml entries for dose extraction."
    )
    registry["sources"] = kept + guidelines + drugs
    registry = normalize_registry(registry)

    errors = validate_registry(registry)
    if errors:
        for err in errors:
            print(err)
        raise SystemExit(1)

    write_registry(registry, REGISTRY_PATH)
    summary = registry["source_summary"]
    print(f"Wrote {REGISTRY_PATH}")
    print(
        f"total={summary['total']} guidelines={summary['guideline_count']} "
        f"drug_labels={summary['drug_label_count']}"
    )
    print("by_type:", summary["by_type"])
    print("by_topic:", summary["by_topic"])


if __name__ == "__main__":
    main()
