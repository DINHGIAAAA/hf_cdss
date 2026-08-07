"""Test dose calculation module."""
import json
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.schemas.patient import PatientProfile
from app.modules.dose_calculation import calculate_single_dose, calculate_multiple_doses, get_available_drugs


def test_enalapril_with_normal_egfr():
    """Test enalapril calculation with normal eGFR."""
    patient = PatientProfile(
        case_id="test_001",
        age=65,
        sex="male",
        lvef=35,
        egfr=75,
        potassium=4.5,
        systolic_bp=125,
        heart_rate=72,
        nyha_class="II",
        current_medications=[],
        comorbidities=[],
        allergies=[],
    )

    result = calculate_single_dose(patient, "enalapril")

    print("=== Test: Enalapril with eGFR 75 ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print()

    return result


def test_enalapril_with_reduced_egfr():
    """Test enalapril calculation with reduced eGFR."""
    patient = PatientProfile(
        case_id="test_002",
        age=70,
        sex="female",
        lvef=30,
        egfr=25,
        potassium=5.2,
        systolic_bp=95,
        heart_rate=65,
        nyha_class="III",
        current_medications=["lisinopril 10mg daily"],
        comorbidities=["CKD"],
        allergies=[],
    )

    result = calculate_single_dose(patient, "enalapril")

    print("=== Test: Enalapril with eGFR 25, K+ 5.2 ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print()

    return result


def test_mra_with_hyperkalemia():
    """Test MRA calculation with hyperkalemia."""
    patient = PatientProfile(
        case_id="test_003",
        age=68,
        sex="male",
        lvef=28,
        egfr=35,
        potassium=5.8,
        systolic_bp=110,
        heart_rate=68,
        nyha_class="II",
        current_medications=["spironolactone 25mg daily"],
        comorbidities=["CKD", "Diabetes"],
        allergies=[],
    )

    result = calculate_single_dose(patient, "spironolactone")

    print("=== Test: Spironolactone with eGFR 35, K+ 5.8 ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print(f"Hold criteria: {result.hold_criteria}")
    print(f"Monitoring: {result.monitoring}")
    print()

    return result


def test_beta_blocker_with_bradycardia():
    """Test beta blocker with bradycardia."""
    patient = PatientProfile(
        case_id="test_004",
        age=72,
        sex="female",
        lvef=32,
        egfr=60,
        potassium=4.2,
        systolic_bp=105,
        heart_rate=52,
        nyha_class="II",
        current_medications=[],
        comorbidities=["Atrial Fibrillation"],
        allergies=[],
    )

    result = calculate_single_dose(patient, "metoprolol_succinate")

    print("=== Test: Metoprolol with HR 52 bpm ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print()

    return result


def test_digoxin_with_severe_renal():
    """Test digoxin with severe renal impairment."""
    patient = PatientProfile(
        case_id="test_005",
        age=75,
        sex="male",
        lvef=25,
        egfr=18,
        potassium=4.0,
        systolic_bp=100,
        heart_rate=80,
        nyha_class="III",
        weight_kg=70,
        current_medications=[],
        comorbidities=["CKD Stage 4"],
        allergies=[],
    )

    result = calculate_single_dose(patient, "digoxin")

    print("=== Test: Digoxin with eGFR 18 ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print(f"Hold criteria: {result.hold_criteria}")
    print()

    return result


def test_sglt2i_normal():
    """Test SGLT2i with normal renal function."""
    patient = PatientProfile(
        case_id="test_006",
        age=60,
        sex="female",
        lvef=35,
        egfr=80,
        potassium=4.5,
        systolic_bp=130,
        heart_rate=70,
        nyha_class="II",
        current_medications=[],
        comorbidities=["Type 2 Diabetes"],
        allergies=[],
    )

    result = calculate_single_dose(patient, "dapagliflozin")

    print("=== Test: Dapagliflozin with eGFR 80 ===")
    print(f"Drug: {result.drug_name}")
    print(f"Status: {result.status}")
    print(f"Recommended dose: {result.recommended_dose}")
    print(f"Target dose: {result.target_dose}")
    print(f"Rationale: {result.rationale}")
    print(f"Titration plan: {result.titration_plan}")
    print()

    return result


def test_apixaban_abc_criteria():
    """Test apixaban NVAF multi-factor (age/weight/creatinine) dose reduction."""
    # Standard 5 mg: no ABC criteria
    standard = calculate_single_dose(
        PatientProfile(
            case_id="test_apix_std",
            age=65,
            sex="male",
            lvef=40,
            egfr=80,
            creatinine=1.0,
            weight_kg=70,
            potassium=4.2,
            systolic_bp=120,
            heart_rate=70,
            nyha_class="II",
        ),
        "apixaban",
    )
    # Reduced 2.5 mg: age≥80 and weight≤60
    reduced = calculate_single_dose(
        PatientProfile(
            case_id="test_apix_abc",
            age=82,
            sex="female",
            lvef=40,
            egfr=50,
            creatinine=1.0,
            weight_kg=55,
            potassium=4.2,
            systolic_bp=120,
            heart_rate=70,
            nyha_class="II",
        ),
        "apixaban",
    )

    print("=== Test: Apixaban ABC criteria ===")
    print(f"Standard: {standard.status} {standard.recommended_dose}")
    print(f"Reduced:  {reduced.status} {reduced.recommended_dose}")
    print(f"Reduced rationale: {reduced.rationale}")
    print()

    assert standard.recommended_dose and standard.recommended_dose.value == 5.0
    assert reduced.recommended_dose and reduced.recommended_dose.value == 2.5
    return standard, reduced


def test_eplerenone_hf_post_mi():
    """Test eplerenone HF post-MI dosing from Inspra SPL (25→50 mg, K+/CrCl)."""
    normal = calculate_single_dose(
        PatientProfile(
            case_id="test_epler_ok",
            age=65,
            sex="male",
            lvef=35,
            egfr=55,
            potassium=4.2,
            systolic_bp=110,
            heart_rate=70,
            nyha_class="II",
        ),
        "eplerenone",
    )
    hyperk = calculate_single_dose(
        PatientProfile(
            case_id="test_epler_k",
            age=65,
            sex="male",
            lvef=35,
            egfr=55,
            potassium=5.7,
            systolic_bp=110,
            heart_rate=70,
            nyha_class="II",
        ),
        "eplerenone",
    )
    renal = calculate_single_dose(
        PatientProfile(
            case_id="test_epler_renal",
            age=65,
            sex="male",
            lvef=35,
            egfr=25,
            potassium=4.2,
            systolic_bp=110,
            heart_rate=70,
            nyha_class="II",
        ),
        "eplerenone",
    )

    print("=== Test: Eplerenone HF post-MI ===")
    print(f"Normal: {normal.status} {normal.recommended_dose} target={normal.target_dose}")
    print(f"K+5.7:  {hyperk.status} {(hyperk.rationale or '')[:100]}")
    print(f"eGFR25: {renal.status} {(renal.rationale or '')[:100]}")
    print()

    assert normal is not None and normal.recommended_dose and normal.recommended_dose.value == 25.0
    assert normal.target_dose and normal.target_dose.value == 50.0
    assert hyperk.status == "avoid"
    assert renal.status == "avoid"
    return normal, hyperk, renal


def test_list_available_drugs():
    """List all available drugs."""
    drugs = get_available_drugs()

    print("=== Available Drugs with Dose Tables ===")
    print(f"Total: {len(drugs)} drugs")
    for drug in drugs:
        print(f"  - {drug['drug_key']}: {drug['generic_name']} ({drug['drug_class']})")
    print()

    return drugs


def main():
    """Run all tests."""
    print("=" * 60)
    print("DOSE CALCULATION TESTS")
    print("=" * 60)
    print()

    test_list_available_drugs()
    test_enalapril_with_normal_egfr()
    test_enalapril_with_reduced_egfr()
    test_mra_with_hyperkalemia()
    test_beta_blocker_with_bradycardia()
    test_digoxin_with_severe_renal()
    test_sglt2i_normal()
    test_apixaban_abc_criteria()
    test_eplerenone_hf_post_mi()

    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
