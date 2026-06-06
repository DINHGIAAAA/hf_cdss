from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _patient(overrides: dict) -> dict:
    base = {
        "case_id": "CASE_SAFETY",
        "lvef": 28,
        "egfr": 24,
        "potassium": 5.6,
        "systolic_bp": 98,
        "heart_rate": 54,
        "comorbidities": ["CKD"],
        "current_medications": [],
        "allergies": [],
    }
    base.update(overrides)
    return base


def test_dose_check_flags_digoxin_and_mra_risk() -> None:
    response = client.post(
        "/dose/check",
        json={
            "patient": _patient(
                {
                    "current_medications": ["digoxin", "spironolactone", "furosemide"],
                }
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    warning_ids = {warning["warning_id"] for warning in payload["warnings"]}
    assert "dose_digoxin_renal_review" in warning_ids
    assert "dose_mra_renal_potassium_review" in warning_ids
    assert "dose_loop_diuretic_lab_monitoring" in warning_ids
    assert any(warning["severity"] == "critical" for warning in payload["warnings"])


def test_interaction_check_flags_raas_and_bleeding_risks() -> None:
    response = client.post(
        "/interaction/check",
        json={
            "patient": _patient(
                {
                    "current_medications": [
                        "lisinopril",
                        "losartan",
                        "spironolactone",
                        "apixaban",
                        "aspirin",
                    ],
                }
            )
        },
    )

    assert response.status_code == 200
    warning_ids = {warning["warning_id"] for warning in response.json()["warnings"]}
    assert "interaction_acei_arb_combination" in warning_ids
    assert "interaction_raasi_mra_hyperkalemia_monitoring" in warning_ids
    assert "interaction_anticoagulant_antiplatelet_bleeding" in warning_ids


def test_recommendation_includes_week7_safety_warnings() -> None:
    response = client.post(
        "/recommend",
        json={
            "patient": _patient(
                {
                    "current_medications": ["lisinopril", "spironolactone", "digoxin"],
                }
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    dose_warning_ids = {warning["warning_id"] for warning in payload["dose_warnings"]}
    interaction_warning_ids = {warning["warning_id"] for warning in payload["interaction_warnings"]}
    assert "dose_digoxin_renal_review" in dose_warning_ids
    assert "dose_mra_renal_potassium_review" in dose_warning_ids
    assert "interaction_raasi_mra_hyperkalemia_monitoring" in interaction_warning_ids

    recommendations = {item["drug_class"]: item for item in payload["recommendations"]}
    mra = recommendations["Mineralocorticoid receptor antagonist"]
    assert "dose_mra_renal_potassium_review" in mra["safety_warning_ids"]
    assert mra["warnings"]
