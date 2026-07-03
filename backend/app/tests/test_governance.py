from app.modules.governance.diff import CONSTRAINT_DIFF_FIELDS, diff_field_map


def test_diff_field_map_detects_changes() -> None:
    before = {"action": "avoid", "reason": "hyperkalemia", "target_drug_class": "MRA"}
    after = {"action": "avoid", "reason": "severe hyperkalemia", "target_drug_class": "MRA"}
    changes = diff_field_map(before, after, CONSTRAINT_DIFF_FIELDS)
    assert len(changes) == 1
    assert changes[0]["path"] == "reason"
    assert changes[0]["change_type"] == "modified"


def test_diff_field_map_ignores_unchanged() -> None:
    payload = {"action": "monitor", "reason": "renal function"}
    assert diff_field_map(payload, payload, CONSTRAINT_DIFF_FIELDS) == []
