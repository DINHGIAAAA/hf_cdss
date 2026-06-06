import math

from app.modules.datastores.common import hashing_embedding


def test_hashing_embedding_is_stable_and_normalized() -> None:
    first = hashing_embedding("heart failure renal potassium")
    second = hashing_embedding("heart failure renal potassium")

    assert first == second
    assert len(first) == 384
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_hashing_embedding_changes_with_clinical_context() -> None:
    renal = hashing_embedding("heart failure renal potassium")
    rhythm = hashing_embedding("heart failure atrial fibrillation")

    assert renal != rhythm

