from fastapi import APIRouter

from app.modules.dose_checking.service import check_dose_safety
from app.modules.interaction_checking.service import check_interactions
from app.schemas.medication_safety import MedicationSafetyRequest, MedicationSafetyResponse


router = APIRouter()


@router.post("/dose/check", response_model=MedicationSafetyResponse)
def dose_check(payload: MedicationSafetyRequest) -> MedicationSafetyResponse:
    return MedicationSafetyResponse(
        case_id=payload.patient.case_id,
        warnings=check_dose_safety(payload.patient),
    )


@router.post("/interaction/check", response_model=MedicationSafetyResponse)
def interaction_check(payload: MedicationSafetyRequest) -> MedicationSafetyResponse:
    return MedicationSafetyResponse(
        case_id=payload.patient.case_id,
        warnings=check_interactions(payload.patient),
    )
