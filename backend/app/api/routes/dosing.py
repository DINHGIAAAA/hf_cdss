"""Dosing API routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.dosing import SuggestedDosePlan
from app.schemas.patient import PatientProfile
from app.modules.dose_calculation import (
    calculate_single_dose,
    calculate_multiple_doses,
    get_available_drugs,
    get_drug_info,
)

router = APIRouter(prefix="/dosing", tags=["dosing"])


class DoseCalculationRequest(BaseModel):
    """Request for dose calculation."""
    patient: PatientProfile
    drug_key: str | None = None
    intent: str = "recommendation"


class DoseCalculationResponse(BaseModel):
    """Response for dose calculation."""
    plans: list[SuggestedDosePlan]
    available_drugs: list[dict]


@router.get("/drugs", response_model=list[dict])
async def list_drugs():
    """List all available drugs with dose tables."""
    return get_available_drugs()


@router.get("/drugs/{drug_key}")
async def get_drug(drug_key: str):
    """Get detailed information for a specific drug."""
    drug = get_drug_info(drug_key)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug {drug_key} not found")
    return drug


@router.post("/calculate", response_model=DoseCalculationResponse)
async def calculate_doses(request: DoseCalculationRequest):
    """
    Calculate doses for one or more drugs based on patient parameters.

    If drug_key is provided, calculates for that specific drug.
    Otherwise, calculates for all available drugs.
    """
    if request.drug_key:
        plan = calculate_single_dose(
            patient=request.patient,
            drug_key=request.drug_key,
            intent=request.intent,
        )
        if not plan:
            raise HTTPException(
                status_code=404,
                detail=f"Drug {request.drug_key} not found in dose tables"
            )
        return DoseCalculationResponse(
            plans=[plan],
            available_drugs=get_available_drugs()
        )
    else:
        plans = calculate_multiple_doses(patient=request.patient)
        return DoseCalculationResponse(
            plans=plans,
            available_drugs=get_available_drugs()
        )


@router.post("/calculate/{drug_key}", response_model=SuggestedDosePlan)
async def calculate_single(
    drug_key: str,
    patient: PatientProfile,
    intent: str = "recommendation",
):
    """Calculate dose for a specific drug."""
    plan = calculate_single_dose(
        patient=patient,
        drug_key=drug_key,
        intent=intent,
    )
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Drug {drug_key} not found in dose tables"
        )
    return plan
