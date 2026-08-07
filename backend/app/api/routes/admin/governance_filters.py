"""Shared governance catalog filter facets."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.routes.admin.deps import AdminUser, require_admin_reader
from app.modules.governance.catalog_filter_facets import list_catalog_filter_facets

router = APIRouter(prefix="/governance", tags=["admin", "governance"])


@router.get("/filter-options")
def catalog_filter_options(
    catalog: str = Query(..., description="Catalog id, e.g. dose-rules"),
    status: str | None = Query(default=None),
    drug_class: str | None = Query(default=None),
    calculation_type: str | None = Query(default=None),
    drug_class_key: str | None = Query(default=None),
    safety_tier: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    target: str | None = Query(default=None),
    default_severity: str | None = Query(default=None),
    target_drug_class: str | None = Query(default=None),
    action: str | None = Query(default=None),
    needs_condition: str | None = Query(default=None),
    extraction_method: str | None = Query(default=None),
    q: str | None = Query(default=None),
    _: AdminUser = Depends(require_admin_reader),
) -> dict[str, Any]:
    filters = {
        k: v
        for k, v in {
            "status": status,
            "drug_class": drug_class,
            "calculation_type": calculation_type,
            "drug_class_key": drug_class_key,
            "safety_tier": safety_tier,
            "severity": severity,
            "target": target,
            "default_severity": default_severity,
            "target_drug_class": target_drug_class,
            "action": action,
            "needs_condition": needs_condition,
            "extraction_method": extraction_method,
            "q": q,
        }.items()
        if v not in (None, "")
    }
    fields = list_catalog_filter_facets(catalog, filters)
    return {"catalog": catalog, "fields": fields}
