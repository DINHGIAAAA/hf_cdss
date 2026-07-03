from app.modules.dose_calculator.calculators import (
    calculate_dual_criteria_reduction,
    calculate_fixed_titration,
    calculate_weight_adjusted_target,
    estimate_crcl,
)
from app.modules.dose_calculator.doac_dose import (
    calculate_crcl_threshold_dose,
    calculate_criteria_reduction,
    calculate_dabigatran_dose,
)
from app.modules.dose_calculator.raasi_titration import calculate_step_titration
from app.modules.dose_calculator.warfarin_inr import calculate_warfarin_inr
from app.modules.dose_calculator.registry import rules_for_drug
from app.modules.dose_calculator.service import build_dose_plans, build_patient_dosing_context
from app.modules.missing_fields.service import check_missing_fields
from app.modules.reasoning.service import build_recommendation
from app.schemas.patient import (
    CareContext,
    ClinicalValue,
    Demographics,
    HeartFailureProfile,
    Labs,
    MedicationStatement,
    PatientIdentity,
    PatientProfile,
    Vitals,
)
from app.schemas.recommendation import RecommendationRequest


def _patient() -> PatientProfile:
    return PatientProfile(
        patient_identity=PatientIdentity(case_id="DOSE_CASE"),
        demographics=Demographics(age=68, sex="male"),
        heart_failure_profile=HeartFailureProfile(lvef=ClinicalValue(value=30, unit="%")),
        labs=Labs(
            egfr=ClinicalValue(value=55, unit="mL/min/1.73m2"),
            potassium=ClinicalValue(value=4.4, unit="mmol/L"),
            creatinine=ClinicalValue(value=1.1, unit="mg/dL"),
        ),
        vitals=Vitals(
            systolic_bp=ClinicalValue(value=110, unit="mmHg"),
            heart_rate=ClinicalValue(value=68, unit="bpm"),
            weight_kg=ClinicalValue(value=72, unit="kg"),
        ),
        medications=[
            MedicationStatement(
                name="bisoprolol fumarate",
                drug_class="beta_blocker",
                dose_value=2.5,
                dose_unit="mg",
                frequency="once daily",
                status="active",
            )
        ],
    )


def test_estimate_crcl_female() -> None:
    crcl = estimate_crcl(age=80, sex="female", weight_kg=60, creatinine=1.4)
    assert crcl is not None
    assert 20 < crcl < 40


def test_bisoprolol_uptitration_plan() -> None:
    patient = _patient()
    rule = rules_for_drug("bisoprolol fumarate")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_fixed_titration(rule=rule, ctx=ctx, patient=patient, drug_name="bisoprolol fumarate")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 5.0
    assert plan.target_dose is not None
    assert plan.target_dose.value == 10.0


def test_carvedilol_target_uses_weight_threshold() -> None:
    heavy = _patient()
    heavy.vitals.weight_kg = ClinicalValue(value=90, unit="kg")
    heavy.medications = [
        MedicationStatement(name="carvedilol", drug_class="beta_blocker", dose_value=6.25, dose_unit="mg", frequency="twice daily")
    ]
    rule = rules_for_drug("carvedilol")[0]
    ctx = build_patient_dosing_context(heavy, {"intent": "dose_adjustment"})
    plan = calculate_weight_adjusted_target(rule=rule, ctx=ctx, patient=heavy, drug_name="carvedilol")

    assert plan.target_dose is not None
    assert plan.target_dose.value == 50


def test_apixaban_reduced_dose_when_two_criteria_met() -> None:
    patient = _patient()
    patient.demographics.age = 82
    patient.vitals.weight_kg = ClinicalValue(value=58, unit="kg")
    patient.labs.creatinine = ClinicalValue(value=1.6, unit="mg/dL")
    patient.medications = [
        MedicationStatement(name="apixaban", drug_class="anticoagulant", dose_value=5, dose_unit="mg", frequency="twice daily")
    ]
    rule = rules_for_drug("apixaban")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_dual_criteria_reduction(rule=rule, ctx=ctx, patient=patient, drug_name="apixaban")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 2.5


def test_build_dose_plans_from_current_medications() -> None:
    plans = build_dose_plans(_patient(), clinical_state={"intent": "dose_adjustment"})
    assert any("bisoprolol" in plan.drug_name.replace("_", " ") for plan in plans)


def test_recommendation_includes_dose_plans() -> None:
    response = build_recommendation(
        RecommendationRequest(
            patient=_patient(),
            clinical_state={"intent": "dose_adjustment", "focus_medication_classes": ["beta_blocker"]},
        )
    )
    assert response.dose_plans
    assert response.dose_plans[0].calculation_steps


def test_dose_intent_requires_personalization_fields() -> None:
    patient = _patient()
    patient.vitals.weight_kg = None
    patient.demographics.sex = None
    patient.demographics.age = None
    patient.labs.creatinine = None
    check = check_missing_fields(patient, clinical_intent="dose_adjustment")
    missing = {item.field for item in check.missing_fields}
    assert {"weight_kg", "sex", "age", "creatinine"} <= missing


def _warfarin_patient(*, inr: float | None, dose_mg: float = 5.0) -> PatientProfile:
    patient = _patient()
    patient.labs.inr = ClinicalValue(value=inr, unit="") if inr is not None else None
    patient.medications = [
        MedicationStatement(
            name="warfarin",
            drug_class="anticoagulant",
            dose_value=dose_mg,
            dose_unit="mg",
            frequency="once daily",
            status="active",
        )
    ]
    return patient


def test_enalapril_uptitration_doubles_current_dose() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(
            name="enalapril",
            drug_class="ACEi",
            dose_value=2.5,
            dose_unit="mg",
            frequency="twice daily",
            status="active",
        )
    ]
    rule = rules_for_drug("enalapril")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_fixed_titration(rule=rule, ctx=ctx, patient=patient, drug_name="enalapril")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 5.0
    assert plan.target_dose is not None
    assert plan.target_dose.value == 10.0


def test_sacubitril_advances_to_next_labelled_step() -> None:
    from app.schemas.dosing import DoseAmount

    patient = _patient()
    patient.medications = [
        MedicationStatement(
            name="sacubitril/valsartan",
            drug_class="ARNI",
            dose_value=24,
            dose_unit="mg",
            frequency="twice daily",
            status="active",
        )
    ]
    rule = rules_for_drug("sacubitril/valsartan")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_step_titration(
        rule=rule,
        ctx=ctx,
        patient=patient,
        drug_name="sacubitril/valsartan",
        current=DoseAmount(value=24, unit="mg", frequency="twice daily", label="24/26 mg"),
        hold=[],
    )

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 49
    assert plan.recommended_dose.label == "49/51 mg"


def test_sacubitril_holds_when_acei_washout_incomplete() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(
            name="enalapril",
            drug_class="ACEi",
            dose_value=10,
            dose_unit="mg",
            frequency="twice daily",
            status="active",
        )
    ]
    patient.care_context = CareContext(acei_last_dose_hours_ago=12)
    rule = rules_for_drug("sacubitril/valsartan")[0]
    ctx = build_patient_dosing_context(
        patient,
        {"intent": "start_medication", "mentioned_medications": [{"name": "sacubitril/valsartan"}]},
    )
    plan = calculate_step_titration(
        rule=rule,
        ctx=ctx,
        patient=patient,
        drug_name="sacubitril/valsartan",
        current=None,
        hold=[],
    )

    assert plan.status == "hold"
    assert plan.hold_criteria
    assert "washout" in plan.hold_criteria[0].lower()


def test_sacubitril_needs_acei_timing_when_transitioning_from_acei() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(name="enalapril", drug_class="ACEi", dose_value=5, dose_unit="mg", status="active")
    ]
    rule = rules_for_drug("sacubitril/valsartan")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "start_medication"})
    plan = calculate_step_titration(
        rule=rule,
        ctx=ctx,
        patient=patient,
        drug_name="sacubitril/valsartan",
        current=None,
        hold=[],
    )

    assert plan.status == "needs_data"
    assert "acei_last_dose_hours_ago" in plan.missing_inputs


def test_warfarin_inr_below_target_increases_dose() -> None:
    patient = _warfarin_patient(inr=1.8, dose_mg=5)
    rule = rules_for_drug("warfarin")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_warfarin_inr(rule=rule, ctx=ctx, patient=patient, drug_name="warfarin")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 5.5
    assert plan.status == "recommended"


def test_warfarin_inr_above_target_decreases_dose() -> None:
    patient = _warfarin_patient(inr=3.6, dose_mg=5)
    rule = rules_for_drug("warfarin")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_warfarin_inr(rule=rule, ctx=ctx, patient=patient, drug_name="warfarin")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 4.5
    assert plan.status == "recommended"


def test_warfarin_inr_supratherapeutic_holds_dose() -> None:
    patient = _warfarin_patient(inr=4.6, dose_mg=5)
    rule = rules_for_drug("warfarin")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_warfarin_inr(rule=rule, ctx=ctx, patient=patient, drug_name="warfarin")

    assert plan.status == "hold"
    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 4.0


def test_warfarin_without_inr_requests_lab() -> None:
    patient = _warfarin_patient(inr=None)
    rule = rules_for_drug("warfarin")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_warfarin_inr(rule=rule, ctx=ctx, patient=patient, drug_name="warfarin")

    assert plan.status == "needs_data"
    assert "inr" in plan.missing_inputs


def test_warfarin_dose_intent_requires_inr() -> None:
    patient = _warfarin_patient(inr=None)
    check = check_missing_fields(patient, clinical_intent="dose_adjustment")
    missing = {item.field for item in check.missing_fields}
    assert "inr" in missing


def test_rivaroxaban_standard_dose_when_crcl_above_threshold() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(name="rivaroxaban", drug_class="anticoagulant", dose_value=15, dose_unit="mg", status="active")
    ]
    rule = rules_for_drug("rivaroxaban")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_crcl_threshold_dose(rule=rule, ctx=ctx, patient=patient, drug_name="rivaroxaban")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 20


def test_rivaroxaban_reduced_dose_when_crcl_15_to_49() -> None:
    patient = _patient()
    patient.demographics.age = 78
    patient.vitals.weight_kg = ClinicalValue(value=60, unit="kg")
    patient.labs.creatinine = ClinicalValue(value=1.8, unit="mg/dL")
    patient.medications = [MedicationStatement(name="rivaroxaban", drug_class="anticoagulant", status="active")]
    rule = rules_for_drug("rivaroxaban")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_crcl_threshold_dose(rule=rule, ctx=ctx, patient=patient, drug_name="rivaroxaban")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 15


def test_edoxaban_reduced_dose_for_low_weight_without_crcl() -> None:
    patient = _patient()
    patient.vitals.weight_kg = ClinicalValue(value=58, unit="kg")
    patient.labs.creatinine = None
    patient.medications = [MedicationStatement(name="edoxaban", drug_class="anticoagulant", status="active")]
    rule = rules_for_drug("edoxaban")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_criteria_reduction(rule=rule, ctx=ctx, patient=patient, drug_name="edoxaban")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 30


def test_edoxaban_not_recommended_when_crcl_above_95() -> None:
    patient = _patient()
    patient.labs.creatinine = None
    patient.labs.egfr = ClinicalValue(value=100, unit="mL/min/1.73m2")
    patient.medications = [MedicationStatement(name="edoxaban", drug_class="anticoagulant", status="active")]
    rule = rules_for_drug("edoxaban")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_criteria_reduction(rule=rule, ctx=ctx, patient=patient, drug_name="edoxaban")

    assert plan.status == "not_recommended"


def test_dabigatran_reduced_dose_for_age_80_or_older() -> None:
    patient = _patient()
    patient.demographics.age = 82
    patient.medications = [MedicationStatement(name="dabigatran", drug_class="anticoagulant", status="active")]
    rule = rules_for_drug("dabigatran")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_dabigatran_dose(rule=rule, ctx=ctx, patient=patient, drug_name="dabigatran")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 110


def test_dabigatran_renal_reduced_dose_when_crcl_15_to_30() -> None:
    patient = _patient()
    patient.demographics.age = 72
    patient.labs.creatinine = ClinicalValue(value=2.5, unit="mg/dL")
    patient.medications = [MedicationStatement(name="dabigatran", drug_class="anticoagulant", status="active")]
    rule = rules_for_drug("dabigatran")[0]
    ctx = build_patient_dosing_context(patient, {"intent": "dose_adjustment"})
    plan = calculate_dabigatran_dose(rule=rule, ctx=ctx, patient=patient, drug_name="dabigatran")

    assert plan.recommended_dose is not None
    assert plan.recommended_dose.value == 75


def test_build_dose_plans_includes_doac_medications() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(name="rivaroxaban", drug_class="anticoagulant", dose_value=20, dose_unit="mg", status="active")
    ]
    plans = build_dose_plans(patient, clinical_state={"intent": "dose_adjustment"})
    assert any("rivaroxaban" in plan.drug_name for plan in plans)


def test_build_dose_plans_skips_concurrent_acei_when_on_arni_only() -> None:
    patient = _patient()
    patient.medications = [
        MedicationStatement(
            name="sacubitril/valsartan",
            drug_class="ARNI",
            dose_value=49,
            dose_unit="mg",
            frequency="twice daily",
            status="active",
        )
    ]
    plans = build_dose_plans(patient, clinical_state={"intent": "dose_adjustment"})
    drug_names = " ".join(plan.drug_name.lower() for plan in plans)
    assert "enalapril" not in drug_names
    assert "lisinopril" not in drug_names
