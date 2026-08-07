from app.modules.gdmt_policy.guidance_normalize import (
    ensure_str_list,
    normalize_gdmt_status,
    normalize_guidance,
    normalize_policy_body,
)


def test_ensure_str_list_from_prose() -> None:
    assert ensure_str_list("no dose adjustment needed") == ["no dose adjustment needed"]


def test_ensure_str_list_does_not_split_characters() -> None:
    assert ensure_str_list(["a", "b"]) == ["a", "b"]
    assert len(ensure_str_list("abc")) == 1


def test_normalize_gdmt_status_rejects_pipe_schema() -> None:
    assert normalize_gdmt_status("review|consider|avoid", default="consider") == "review"


def test_normalize_guidance_string_actions() -> None:
    g = normalize_guidance({"actions": "Check renal function", "monitoring": "eGFR"})
    assert g["actions"] == ["Check renal function"]
    assert g["monitoring"] == ["eGFR"]


def test_normalize_guidance_list_of_strings() -> None:
    g = normalize_guidance(["Reason one", "Reason two"])
    assert g["reasoning_base"] == ["Reason one", "Reason two"]


def test_normalize_policy_body_guidance_list_does_not_break() -> None:
    body = normalize_policy_body(
        {
            "guidance": [{"actions": "Check K+", "monitoring": "K+"}],
            "hfref_default_status": "consider",
        }
    )
    assert isinstance(body["guidance"], dict)
    assert body["guidance"]["actions"] == ["Check K+"]

    body = normalize_policy_body(
        {
            "hfref_default_status": "consider|recommend|review|avoid",
            "non_hfref_status": "review|consider|avoid",
            "guidance": {"actions": "One action line"},
        }
    )
    assert body["hfref_default_status"] == "consider"
    assert body["non_hfref_status"] == "review"
    assert body["guidance"]["actions"] == ["One action line"]
