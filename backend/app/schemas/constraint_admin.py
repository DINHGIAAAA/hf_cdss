"""Admin schemas for constraint approval workflow."""
from typing import Any

from pydantic import BaseModel, Field


class ConstraintDefinition(BaseModel):
    """Extracted constraint candidate pending approval."""
    
    constraint_id: str = Field(..., description="Unique constraint identifier")
    target_drug_class: str = Field(..., description="Drug class this constraint applies to")
    action: str = Field(..., description="Action: avoid, caution, monitor, dose")
    constraint_type: str = Field(..., description="Type: hard, soft, monitoring, dose")
    reason: str = Field(..., description="Clinical rationale")
    risk_names: list[str] = Field(default_factory=list, description="Risk factors that trigger this constraint")
    severity_any: list[str] = Field(default_factory=list, description="Risk severity levels that apply")
    evidence_ref: str | None = Field(None, description="Reference to evidence/source")
    clinical_sources: list[dict[str, Any]] = Field(default_factory=list, description="Clinical evidence sources")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConstraintApprovalStatus(BaseModel):
    """Constraint with approval status."""
    
    constraint_id: str
    target_drug_class: str
    action: str
    constraint_type: str
    reason: str
    risk_names: list[str]
    severity_any: list[str]
    evidence_ref: str | None
    clinical_sources: list[dict[str, Any]]
    status: str = Field(..., description="pending, approved, rejected")
    status_updated_at: str | None = None
    status_updated_by: str | None = None
    rejection_reason: str | None = None
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConstraintApprovalRequest(BaseModel):
    """Request to approve or reject a constraint."""
    
    approved: bool = Field(..., description="True to approve, False to reject")
    reason: str | None = Field(None, description="Reason for approval/rejection")
    admin_user_id: str = Field(..., description="ID of admin performing action")


class ConstraintApprovalResponse(BaseModel):
    """Response to approval/rejection request."""
    
    constraint_id: str
    status: str
    updated_at: str
    updated_by: str


class ConstraintApprovalListResponse(BaseModel):
    """List of constraints with approval status."""
    
    total: int
    items: list[ConstraintApprovalStatus]
    pending_count: int
    approved_count: int
    rejected_count: int


class ConstraintExtractionRequest(BaseModel):
    """Request to extract constraint candidates from evidence."""
    
    source_type: str | None = Field(None, description="Filter by source type (guideline, drug_label, etc.)")
    drug_class_filter: list[str] | None = Field(None, description="Only extract constraints for these drug classes")


class ConstraintExtractionResult(BaseModel):
    """Result of constraint extraction."""
    
    extracted_count: int
    new_count: int
    skipped_count: int
    errors: list[str] = Field(default_factory=list)


class ConstraintSourceMapping(BaseModel):
    """Maps constraint to evidence sources."""
    
    constraint_id: str
    source_id: str
    source_type: str
    title: str
    url: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
