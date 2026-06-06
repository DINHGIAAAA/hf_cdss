from typing import Any

from fastapi import APIRouter

from app.modules.constraint_builder.service import load_constraint_rules


router = APIRouter()


@router.get("/rules")
def rules() -> list[dict[str, Any]]:
    return load_constraint_rules()
