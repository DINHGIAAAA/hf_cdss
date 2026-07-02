from app.modules.evidence_text import normalize_evidence_text


def test_normalize_evidence_text_repairs_ada_pdf_glue_and_callouts() -> None:
    raw = (
        "Abnormal kidney function results in alteration in pharma- Practice Point 4.1.2: "
        "Monitor eGFR, electrolytes, and ther- cokineticsandpharmacodynamics,andforpeoplewithCKD, "
        "apeutic medication levels, when indicated, in people with asthe GFR worsens,sodoes"
    )

    normalized = normalize_evidence_text(raw)

    assert "pharma- Practice Point" not in normalized
    assert "Practice Point" not in normalized
    assert "pharmacokinetics and pharmacodynamics" in normalized
    assert "for people with CKD" in normalized.lower() or "for people with CKD" in normalized
    assert "therapeutic medication" in normalized
    assert "as the GFR worsens" in normalized
    assert "cokineticsand" not in normalized
    assert "andfor" not in normalized
