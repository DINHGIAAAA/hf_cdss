from app.modules.interaction_checking.drug_set_tokens import is_plausible_drug_set_token


def test_rejects_prose_slug_in_drug_set_b() -> None:
    assert not is_plausible_drug_set_token("torsemide_may_increase_risk_of_hypokalem")


def test_accepts_drug_and_class_tokens() -> None:
    assert is_plausible_drug_set_token("torsemide")
    assert is_plausible_drug_set_token("class:loop_diuretic")
