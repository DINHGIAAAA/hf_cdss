"""Admin API routes."""
from app.api.routes.admin.audit import router as audit_router
from app.api.routes.admin.constraint_rules import router as constraint_rules_router
from app.api.routes.admin.dose_rules import router as dose_rules_router
from app.api.routes.admin.evidence import router as evidence_router
from app.api.routes.admin.interaction_rules import router as interaction_rules_router
from app.api.routes.admin.users import router as users_router

__all__ = [
    "audit_router",
    "constraint_rules_router",
    "dose_rules_router",
    "evidence_router",
    "interaction_rules_router",
    "users_router",
]
