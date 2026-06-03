import json
from pathlib import Path


PATIENT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Heart Failure Medication Recommendation Patient Context",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "hf_type",
        "ef",
        "egfr",
        "potassium",
        "sbp",
        "heart_rate",
        "diabetes",
        "ckd_stage",
        "af",
        "pregnancy",
        "current_drugs",
    ],
    "properties": {
        "hf_type": {"type": "string", "enum": ["HFrEF", "HFmrEF", "HFpEF", "unknown"]},
        "ef": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
        "egfr": {"type": ["number", "null"], "minimum": 0, "maximum": 150},
        "potassium": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "sbp": {"type": ["number", "null"], "minimum": 40, "maximum": 260},
        "heart_rate": {"type": ["number", "null"], "minimum": 20, "maximum": 250},
        "diabetes": {"type": "boolean"},
        "ckd_stage": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        "af": {"type": "boolean"},
        "pregnancy": {"type": "boolean"},
        "lactation": {"type": "boolean", "default": False},
        "hypersensitivities": {"type": "array", "items": {"type": "string"}, "default": []},
        "bleeding_risk": {"type": "string", "enum": ["low", "moderate", "high", "active_bleeding", "unknown"], "default": "unknown"},
        "current_drugs": {"type": "array", "items": {"type": "string"}},
        "indication": {
            "type": ["string", "null"],
            "enum": [
                "heart_failure",
                "glycemic_control",
                "hypertension",
                "atrial_fibrillation",
                "chronic_kidney_disease",
                None,
            ],
        },
    },
}


HARD_SAFETY_RULES = [
    {
        "rule_id": "mra_potassium_high_avoid",
        "drug_class": "MRA",
        "applies_to_drugs": ["spironolactone", "eplerenone", "finerenone"],
        "condition": {"potassium": ">=5.5"},
        "action": "avoid",
        "severity": "high",
        "reason": "High potassium increases hyperkalemia risk with mineralocorticoid receptor antagonists.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "mra_potassium_borderline_monitor",
        "drug_class": "MRA",
        "applies_to_drugs": ["spironolactone", "eplerenone", "finerenone"],
        "condition": {"potassium": "5.0-5.4"},
        "action": "monitor",
        "severity": "moderate",
        "reason": "Borderline potassium requires close monitoring with MRA therapy.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "mra_egfr_low_avoid",
        "drug_class": "MRA",
        "applies_to_drugs": ["spironolactone", "eplerenone", "finerenone"],
        "condition": {"egfr": "<30"},
        "action": "avoid",
        "severity": "high",
        "reason": "Low eGFR increases hyperkalemia and renal adverse event risk with MRA therapy.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "raasi_potassium_high_warning",
        "drug_class": "RAASi",
        "applies_to_drugs": ["enalapril maleate", "valsartan", "losartan potassium", "candesartan cilexetil", "sacubitril and valsartan"],
        "condition": {"potassium": ">=5.5"},
        "action": "warning",
        "severity": "high",
        "reason": "Hyperkalemia requires reassessment and monitoring before RAAS inhibitor intensification.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "raasi_pregnancy_contraindicated",
        "drug_class": "RAASi",
        "applies_to_drugs": ["enalapril maleate", "valsartan", "losartan potassium", "candesartan cilexetil", "sacubitril and valsartan"],
        "condition": {"pregnancy": True},
        "action": "contraindicated",
        "severity": "critical",
        "reason": "RAAS inhibitors are contraindicated in pregnancy due to fetal toxicity risk.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "sglt2i_glycemic_control_egfr_less_45_not_recommended",
        "drug_class": "SGLT2i",
        "applies_to_drugs": ["dapagliflozin"],
        "condition": {"egfr": "<45", "indication": "glycemic_control"},
        "action": "not_recommended",
        "severity": "moderate",
        "reason": "Likely ineffective for glycemic control when eGFR <45.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "sglt2i_egfr_very_low_warning",
        "drug_class": "SGLT2i",
        "applies_to_drugs": ["dapagliflozin", "empagliflozin"],
        "condition": {"egfr": "<20"},
        "action": "warning",
        "severity": "high",
        "reason": "Very low eGFR requires indication-specific review before SGLT2 inhibitor use.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "ivabradine_heart_rate_low_avoid",
        "drug_class": "If current inhibitor",
        "applies_to_drugs": ["ivabradine"],
        "condition": {"heart_rate": "<60"},
        "action": "avoid",
        "severity": "high",
        "reason": "Ivabradine is not appropriate when resting heart rate is already low.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "ivabradine_af_avoid",
        "drug_class": "If current inhibitor",
        "applies_to_drugs": ["ivabradine"],
        "condition": {"af": True},
        "action": "avoid",
        "severity": "high",
        "reason": "Ivabradine requires sinus rhythm; atrial fibrillation should trigger avoidance/review.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "beta_blocker_sbp_low_warning",
        "drug_class": "Beta blocker",
        "applies_to_drugs": ["carvedilol", "bisoprolol fumarate", "metoprolol succinate"],
        "condition": {"sbp": "<90"},
        "action": "warning",
        "severity": "high",
        "reason": "Low systolic blood pressure increases intolerance risk with beta blocker initiation or titration.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "beta_blocker_heart_rate_low_warning",
        "drug_class": "Beta blocker",
        "applies_to_drugs": ["carvedilol", "bisoprolol fumarate", "metoprolol succinate"],
        "condition": {"heart_rate": "<55"},
        "action": "warning",
        "severity": "high",
        "reason": "Low heart rate increases bradycardia risk with beta blockers.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "anticoagulant_active_bleeding_contraindicated",
        "drug_class": "Anticoagulant",
        "applies_to_drugs": ["apixaban", "warfarin sodium"],
        "condition": {"bleeding_risk": "active_bleeding"},
        "action": "contraindicated",
        "severity": "critical",
        "reason": "Active pathological bleeding is a contraindication to anticoagulant therapy.",
        "recommendation_use": "hard_rule",
    },
    {
        "rule_id": "anticoagulant_high_bleeding_risk_warning",
        "drug_class": "Anticoagulant",
        "applies_to_drugs": ["apixaban", "warfarin sodium"],
        "condition": {"bleeding_risk": "high"},
        "action": "warning",
        "severity": "high",
        "reason": "High bleeding risk requires individualized risk-benefit review before anticoagulation.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "loop_diuretic_sbp_low_warning",
        "drug_class": "Loop diuretic",
        "applies_to_drugs": ["furosemide", "bumetanide", "torsemide"],
        "condition": {"sbp": "<90"},
        "action": "warning",
        "severity": "moderate",
        "reason": "Hypotension should prompt volume status and dosing review before loop diuretic intensification.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "digoxin_egfr_low_monitor",
        "drug_class": "Cardiac glycoside",
        "applies_to_drugs": ["digoxin"],
        "condition": {"egfr": "<30"},
        "action": "monitor",
        "severity": "high",
        "reason": "Reduced kidney function increases digoxin toxicity risk and requires close monitoring.",
        "recommendation_use": "warning",
    },
    {
        "rule_id": "patiromer_lokelma_hypokalemia_monitor",
        "drug_class": "Potassium binder",
        "applies_to_drugs": ["patiromer", "sodium zirconium cyclosilicate"],
        "condition": {"potassium": "<3.5"},
        "action": "avoid",
        "severity": "high",
        "reason": "Potassium binders are inappropriate when potassium is already low.",
        "recommendation_use": "hard_rule",
    },
]


def case(case_id, patient, expected_recommend, expected_avoid, expected_warning, evidence_source):
    return {
        "case_id": case_id,
        "patient": patient,
        "expected_recommend": expected_recommend,
        "expected_avoid": expected_avoid,
        "expected_warning": expected_warning,
        "evidence_source": evidence_source,
    }


BASE_PATIENT = {
    "hf_type": "HFrEF",
    "ef": 30,
    "egfr": 60,
    "potassium": 4.4,
    "sbp": 120,
    "heart_rate": 75,
    "diabetes": False,
    "ckd_stage": 2,
    "af": False,
    "pregnancy": False,
    "lactation": False,
    "hypersensitivities": [],
    "bleeding_risk": "low",
    "current_drugs": [],
    "indication": "heart_failure",
}


def patient(**updates):
    output = dict(BASE_PATIENT)
    output.update(updates)
    return output


GOLDEN_CASES = [
    case("golden_001_hfref_egfr25_k58", patient(egfr=25, potassium=5.8, ckd_stage=4), ["SGLT2i_review"], ["MRA"], ["RAASi", "digoxin"], ["mra_potassium_high_avoid", "mra_egfr_low_avoid", "raasi_potassium_high_warning"]),
    case("golden_002_hfref_hr55", patient(heart_rate=55), ["RAASi", "SGLT2i"], ["ivabradine"], ["Beta blocker"], ["ivabradine_heart_rate_low_avoid"]),
    case("golden_003_hf_af_high_bleeding", patient(af=True, bleeding_risk="high"), ["rate_control_review"], ["ivabradine"], ["Anticoagulant"], ["ivabradine_af_avoid", "anticoagulant_high_bleeding_risk_warning"]),
    case("golden_004_hf_pregnancy", patient(pregnancy=True), ["non_RAASi_review"], ["RAASi"], ["MRA", "SGLT2i"], ["raasi_pregnancy_contraindicated"]),
    case("golden_005_loop_diuretic_hypotension", patient(sbp=85, current_drugs=["furosemide"]), ["volume_status_review"], [], ["Loop diuretic", "Beta blocker"], ["loop_diuretic_sbp_low_warning", "beta_blocker_sbp_low_warning"]),
]

for idx, egfr in enumerate([15, 20, 28, 35, 44], start=6):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_dapagliflozin_glycemic_egfr_{egfr}",
            patient(egfr=egfr, diabetes=True, ckd_stage=4 if egfr < 30 else 3, indication="glycemic_control"),
            ["heart_failure_indication_review"],
            ["dapagliflozin_for_glycemic_control"],
            ["SGLT2i"],
            ["sglt2i_glycemic_control_egfr_less_45_not_recommended"],
        )
    )

for idx, potassium in enumerate([5.0, 5.2, 5.4, 5.5, 5.8, 6.1], start=11):
    avoid = ["MRA"] if potassium >= 5.5 else []
    warning = ["MRA"] if potassium < 5.5 else ["RAASi"]
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_potassium_{str(potassium).replace('.', '_')}",
            patient(potassium=potassium),
            ["SGLT2i"],
            avoid,
            warning,
            ["mra_potassium_borderline_monitor" if potassium < 5.5 else "mra_potassium_high_avoid"],
        )
    )

for idx, sbp in enumerate([80, 85, 89, 90, 95], start=17):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_sbp_{sbp}",
            patient(sbp=sbp),
            [],
            [],
            ["Beta blocker", "Loop diuretic"] if sbp < 90 else ["hypotension_review"],
            ["beta_blocker_sbp_low_warning", "loop_diuretic_sbp_low_warning"],
        )
    )

for idx, hr in enumerate([45, 50, 54, 59, 60, 70], start=22):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_heart_rate_{hr}",
            patient(heart_rate=hr),
            ["RAASi", "SGLT2i"],
            ["ivabradine"] if hr < 60 else [],
            ["Beta blocker"] if hr < 55 else [],
            ["ivabradine_heart_rate_low_avoid", "beta_blocker_heart_rate_low_warning"],
        )
    )

for idx, bleeding in enumerate(["active_bleeding", "high", "moderate", "low"], start=28):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_bleeding_{bleeding}",
            patient(af=True, bleeding_risk=bleeding),
            ["anticoagulation_review"] if bleeding in {"low", "moderate"} else [],
            ["Anticoagulant"] if bleeding == "active_bleeding" else [],
            ["Anticoagulant"] if bleeding == "high" else [],
            ["anticoagulant_active_bleeding_contraindicated", "anticoagulant_high_bleeding_risk_warning"],
        )
    )

for idx, drug in enumerate(["spironolactone", "eplerenone", "finerenone", "enalapril maleate", "valsartan", "apixaban", "warfarin sodium", "digoxin"], start=32):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_current_drug_{drug.replace(' ', '_')}",
            patient(current_drugs=[drug], egfr=28 if drug == "digoxin" else 60, potassium=5.6 if drug in {"spironolactone", "eplerenone", "finerenone", "valsartan"} else 4.4),
            [],
            ["MRA"] if drug in {"spironolactone", "eplerenone", "finerenone"} else [],
            ["current_medication_interaction_review", "digoxin"] if drug == "digoxin" else ["current_medication_interaction_review"],
            ["digoxin_egfr_low_monitor" if drug == "digoxin" else "current_medication_interaction_review"],
        )
    )

for idx, scenario in enumerate(
    [
        {"hf_type": "HFpEF", "ef": 55, "diabetes": True, "egfr": 42, "indication": "glycemic_control"},
        {"hf_type": "HFmrEF", "ef": 45, "potassium": 5.5},
        {"hf_type": "HFrEF", "ef": 25, "af": True, "heart_rate": 58},
        {"hf_type": "HFrEF", "ef": 20, "pregnancy": True, "potassium": 5.2},
        {"hf_type": "HFrEF", "ef": 35, "egfr": 18, "potassium": 4.8},
        {"hf_type": "HFrEF", "ef": 30, "egfr": 28, "potassium": 3.2},
        {"hf_type": "HFrEF", "ef": 30, "sbp": 88, "heart_rate": 52},
        {"hf_type": "HFrEF", "ef": 30, "af": True, "bleeding_risk": "active_bleeding"},
        {"hf_type": "HFrEF", "ef": 30, "ckd_stage": 4, "egfr": 24, "potassium": 5.4},
        {"hf_type": "HFrEF", "ef": 30, "diabetes": True, "ckd_stage": 3, "egfr": 46, "indication": "glycemic_control"},
        {"hf_type": "HFrEF", "ef": 30, "lactation": True},
    ],
    start=40,
):
    GOLDEN_CASES.append(
        case(
            f"golden_{idx:03d}_combined_safety",
            patient(**scenario),
            ["evidence_review"],
            [],
            ["safety_verifier_required"],
            ["combined_guardrail_review"],
        )
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    write_json(Path("schemas/patient_schema.json"), PATIENT_SCHEMA)
    write_jsonl(Path("artifacts/rules/hard_safety_rules.jsonl"), HARD_SAFETY_RULES)
    write_jsonl(Path("evaluation/clinical_cases/golden_cases.jsonl"), GOLDEN_CASES)
    print(f"Wrote patient schema, {len(HARD_SAFETY_RULES)} hard safety rules, and {len(GOLDEN_CASES)} golden cases")


if __name__ == "__main__":
    main()
