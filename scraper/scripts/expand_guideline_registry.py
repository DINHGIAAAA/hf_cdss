"""Add HF-related comorbidity guidelines to sources.example.json."""
from __future__ import annotations

import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "data" / "heart_failure" / "sources" / "sources.example.json"

PMC = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

NEW_GUIDELINES: list[dict] = [
    # ADA 2024 — remaining supplement sections
    {
        "source_id": "ada_2024_population_health",
        "title": "ADA Standards of Care in Diabetes 2024: Improving Care and Promoting Health in Populations",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725798"),
        "target_path": "raw/guidelines/diabetes/ada_2024_population_health.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_diagnosis_classification",
        "title": "ADA Standards of Care in Diabetes 2024: Diagnosis and Classification of Diabetes",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725812"),
        "target_path": "raw/guidelines/diabetes/ada_2024_diagnosis_classification.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_prevention_delay",
        "title": "ADA Standards of Care in Diabetes 2024: Prevention or Delay of Diabetes and Associated Comorbidities",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725807"),
        "target_path": "raw/guidelines/diabetes/ada_2024_prevention_delay.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_health_behaviors",
        "title": "ADA Standards of Care in Diabetes 2024: Facilitating Positive Health Behaviors and Well-being",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725816"),
        "target_path": "raw/guidelines/diabetes/ada_2024_health_behaviors.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_diabetes_technology",
        "title": "ADA Standards of Care in Diabetes 2024: Diabetes Technology",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725813"),
        "target_path": "raw/guidelines/diabetes/ada_2024_diabetes_technology.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_retinopathy_neuropathy",
        "title": "ADA Standards of Care in Diabetes 2024: Retinopathy, Neuropathy, and Foot Care",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725803"),
        "target_path": "raw/guidelines/diabetes/ada_2024_retinopathy_neuropathy.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_pregnancy",
        "title": "ADA Standards of Care in Diabetes 2024: Management of Diabetes in Pregnancy",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725801"),
        "target_path": "raw/guidelines/diabetes/ada_2024_pregnancy.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "ada_2024_hospital_care",
        "title": "ADA Standards of Care in Diabetes 2024: Diabetes Care in the Hospital",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Diabetes Association",
        "topic": "diabetes",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC10725815"),
        "target_path": "raw/guidelines/diabetes/ada_2024_hospital_care.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    # ASCVD / lipids
    {
        "source_id": "acc_aha_2018_cholesterol_guideline",
        "title": "2018 AHA/ACC Guideline on the Management of Blood Cholesterol",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "ACC/AHA",
        "topic": "dyslipidemia",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC7403606"),
        "target_path": "raw/guidelines/dyslipidemia/2018 ACC AHA Cholesterol Guideline.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "acc_aha_2019_primary_prevention_guideline",
        "title": "2019 ACC/AHA Guideline on the Primary Prevention of Cardiovascular Disease",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "ACC/AHA",
        "topic": "ascvd_prevention",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC7685565"),
        "target_path": "raw/guidelines/ascvd_prevention/2019 ACC AHA Primary Prevention Guideline.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    # Structural / cardiomyopathy
    {
        "source_id": "acc_aha_2020_valvular_heart_disease_guideline",
        "title": "2020 ACC/AHA Guideline for the Management of Patients With Valvular Heart Disease",
        "source_type": "guideline_pdf",
        "download_strategy": "direct_url",
        "publisher": "ACC/AHA",
        "topic": "valvular_heart_disease",
        "url": "https://sochicar.cl/wp-content/uploads/2022/12/j.jacc_.2020.11.018.pdf",
        "target_path": "raw/guidelines/valvular_heart_disease/2020 ACC AHA Valvular Heart Disease Guideline.pdf",
        "license_note": "Official publisher material hosted on a public mirror. Verify terms before redistribution.",
    },
    {
        "source_id": "acc_aha_2020_hcm_guideline",
        "title": "2020 AHA/ACC Guideline for the Diagnosis and Treatment of Patients With Hypertrophic Cardiomyopathy",
        "source_type": "guideline_pdf",
        "download_strategy": "direct_url",
        "publisher": "ACC/AHA",
        "topic": "cardiomyopathy",
        "url": "https://sochicar.cl/wp-content/uploads/2022/12/j.jacc_.2020.08.045.pdf",
        "target_path": "raw/guidelines/cardiomyopathy/2020 ACC AHA Hypertrophic Cardiomyopathy Guideline.pdf",
        "license_note": "Official publisher material hosted on a public mirror. Verify terms before redistribution.",
    },
    # ESC prevention / PH
    {
        "source_id": "esc_2021_cvd_prevention_guideline",
        "title": "2021 ESC Guidelines on Cardiovascular Disease Prevention in Clinical Practice",
        "source_type": "guideline_pdf",
        "download_strategy": "direct_url",
        "publisher": "European Society of Cardiology",
        "topic": "ascvd_prevention",
        "url": "https://eas-society.org/wp-content/uploads/2022/05/2021-Prevention-Guidelines.pdf",
        "target_path": "raw/guidelines/ascvd_prevention/2021 ESC CVD Prevention Guidelines.pdf",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "esc_2022_pulmonary_hypertension_guideline",
        "title": "2022 ESC/ERS Guidelines for the Diagnosis and Treatment of Pulmonary Hypertension",
        "source_type": "guideline_pdf",
        "download_strategy": "direct_url",
        "publisher": "ESC/ERS",
        "topic": "pulmonary_hypertension",
        "url": "https://pure.rug.nl/ws/files/258895003/ehac237.pdf",
        "target_path": "raw/guidelines/pulmonary_hypertension/2022 ESC ERS Pulmonary Hypertension Guidelines.pdf",
        "license_note": "Official publisher material hosted on an institutional repository. Verify terms before redistribution.",
    },
    # Respiratory / sleep
    {
        "source_id": "gold_2024_copd_guideline",
        "title": "GOLD 2024 Global Strategy for Prevention, Diagnosis and Management of COPD",
        "source_type": "guideline_pdf",
        "download_strategy": "direct_url",
        "publisher": "GOLD",
        "topic": "copd",
        "url": "https://goldcopd.org/wp-content/uploads/2024/02/GOLD-2024_v1.2-11Jan24_WMV.pdf",
        "target_path": "raw/guidelines/copd/GOLD 2024 COPD Report.pdf",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    {
        "source_id": "aasm_2017_osa_diagnostic_guideline",
        "title": "AASM Clinical Practice Guideline for Diagnostic Testing for Adult Obstructive Sleep Apnea",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "American Academy of Sleep Medicine",
        "topic": "sleep_apnea",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC5337595"),
        "target_path": "raw/guidelines/sleep_apnea/AASM 2017 OSA Diagnostic Guideline.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
    # Vascular disease
    {
        "source_id": "acc_aha_2024_pad_guideline",
        "title": "2024 ACC/AHA Guideline for the Management of Lower Extremity Peripheral Artery Disease",
        "source_type": "guideline_html",
        "download_strategy": "direct_url",
        "publisher": "ACC/AHA",
        "topic": "peripheral_artery_disease",
        "artifact_kind": "html",
        "url": PMC.format(pmcid="PMC12782132"),
        "target_path": "raw/guidelines/peripheral_artery_disease/2024 ACC AHA PAD Guideline.html",
        "license_note": "Official publisher material. Verify terms before redistribution.",
    },
]


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    existing_ids = {row["source_id"] for row in registry.get("sources", [])}
    added = 0
    for entry in NEW_GUIDELINES:
        if entry["source_id"] in existing_ids:
            continue
        registry["sources"].append(entry)
        existing_ids.add(entry["source_id"])
        added += 1

    guideline_count = sum(
        1
        for row in registry["sources"]
        if str(row.get("source_type", "")).startswith("guideline_")
    )
    registry["version"] = 3
    registry["notes"] = (
        "Curated official sources for Heart Failure CDSS ingestion, including HF core guidelines "
        "and comorbidity guidelines that affect GDMT, safety checks, and evidence retrieval."
    )
    REGISTRY.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Added {added} guideline sources ({guideline_count} guideline entries total).")


if __name__ == "__main__":
    main()
