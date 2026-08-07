from app.core.governance_audit_labels import (
    LEGACY_AUTO_RETIRE_PREFIX,
    supersede_history_actor,
    supersede_history_reason,
    supersede_retired_by,
)


def test_supersede_labels_are_human_readable() -> None:
    assert supersede_retired_by("dr_lead") == "system:superseded-by-dr_lead"
    assert "dr_lead" in supersede_history_actor("dr_lead")
    assert "Automatic" in supersede_history_actor("dr_lead")
    reason = supersede_history_reason(252, "dr_lead")
    assert "252" in reason
    assert "dr_lead" in reason
    assert LEGACY_AUTO_RETIRE_PREFIX == "system_auto_retire_by_"
