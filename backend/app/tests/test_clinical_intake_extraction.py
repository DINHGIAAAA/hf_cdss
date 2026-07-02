from app.core.config import settings
from app.modules.clinical_intake_extraction import service
from app.modules.clinical_intake_extraction.service import extract_patient_from_message


def test_extracts_vietnamese_vitals_labs_medications_and_allergy() -> None:
    patient = extract_patient_from_message(
        (
            "Benh nhan nam 64 tuoi suy tim EF con 32%, muc loc cau than 78, "
            "kali mau 4.4, huyet ap 118/74 va mach 74 lan/phut. "
            "Tang huyet ap, dang dung metoprolol 25 mg bid va dapagliflozin 10mg daily. "
            "Di ung voi lisinopril gay ho. Khong co dau hieu cap cuu."
        ),
        "INTAKE_VI",
    )

    assert patient.case_id == "INTAKE_VI"
    assert patient.lvef == 32
    assert patient.egfr == 78
    assert patient.potassium == 4.4
    assert patient.systolic_bp == 118
    assert patient.heart_rate == 74
    assert "Hypertension" in patient.comorbidities
    assert {"metoprolol succinate", "dapagliflozin"} <= set(patient.current_medications)
    metoprolol = next(item for item in patient.medications if item.name == "metoprolol succinate")
    assert metoprolol.dose_value == 25
    assert metoprolol.dose_unit == "mg"
    assert metoprolol.frequency == "bid"
    assert patient.allergies == ["lisinopril gay ho"]
    assert patient.red_flags[0].status == "absent"
    assert patient.heart_failure_profile.lvef.source.confidence == 0.9


def test_negation_prevents_false_positive_conditions_and_medications() -> None:
    patient = extract_patient_from_message(
        "EF 35, eGFR 55, K 4.8, BP 110/70, HR 68. No CKD, no diabetes, not on spironolactone. NKDA. Stable.",
        "INTAKE_NEGATION",
    )

    assert patient.comorbidities == []
    assert "spironolactone" not in patient.current_medications
    assert patient.allergies == ["no known drug allergies"]
    assert any(flag.status == "absent" for flag in patient.red_flags)


def test_extracts_brands_and_acute_red_flags() -> None:
    patient = extract_patient_from_message(
        "HFrEF EF 25 eGFR 30 K 5.5 SBP 90 HR 58. Taking Entresto and Farxiga. Active bleeding today.",
        "INTAKE_BRANDS",
    )

    assert {"sacubitril/valsartan", "dapagliflozin"} <= set(patient.current_medications)
    assert any(flag.name == "active_bleeding" and flag.status == "present" for flag in patient.red_flags)


def test_llm_extractor_enriches_patient_identity_and_structured_fields(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_llm_enabled", True)
    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"full_name":"Nguyen Van A","age":72,"sex":"male","weight_kg":70,'
                                '"systolic_bp":104,"heart_rate":66,"lvef":29,"egfr":24,'
                                '"potassium":5.7,"conditions":["HFrEF","CKD"],'
                                '"medications":[{"name":"spironolactone","dose_value":25,'
                                '"dose_unit":"mg","frequency":"daily"}],"allergies":["NKDA"],'
                                '"red_flags":[{"name":"hyperkalemia","status":"present"}],'
                                '"chief_complaint":"medication safety review"}'
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(service.httpx, "Client", FakeClient)

    patient = extract_patient_from_message("Can danh gia an toan MRA.", "LLM_INTAKE")

    assert patient.patient_identity.full_name == "Nguyen Van A"
    assert patient.age == 72
    assert patient.sex == "male"
    assert patient.vitals.weight_kg.value == 70
    assert patient.lvef == 29
    assert patient.egfr == 24
    assert patient.potassium == 5.7
    assert "spironolactone" in patient.current_medications
    assert patient.medications[0].dose_value == 25
    assert any(flag.name == "hyperkalemia" for flag in patient.red_flags)
