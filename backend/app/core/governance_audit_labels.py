"""Human-readable governance audit labels (history + retired_by)."""

from __future__ import annotations

# Legacy prefix stored before friendlier copy was introduced.
LEGACY_AUTO_RETIRE_PREFIX = "system_auto_retire_by_"


def supersede_retired_by(approver_user_id: str) -> str:
    """Database retired_by when an older approved row is replaced on approve."""
    return f"system:superseded-by-{approver_user_id}"


def supersede_history_actor(approver_user_id: str) -> str:
    """history.changed_by — shown in admin governance history."""
    return f"Automatic (newer version approved by {approver_user_id})"


def supersede_history_reason(new_record_id: int, approver_user_id: str) -> str:
    """history.reason — explains why the old approved copy was retired."""
    return (
        f"This approved copy was retired when {approver_user_id} approved a newer draft "
        f"(record #{new_record_id}). Only one approved version is active per rule."
    )
