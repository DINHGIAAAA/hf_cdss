"""Validation module for evidence-claim alignment checking."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# GDMT / HF class tokens (metadata or guideline extract) → cues allowed in evidence spans.
CLASS_DRUG_EVIDENCE_CUES: dict[str, tuple[str, ...]] = {
    "ace_inhibitor": ("ace inhibitor", "ace-i", "ace i", "acei", "angiotensin-converting enzyme"),
    "arb": ("angiotensin receptor", "arb ", "angiotensin ii receptor"),
    "sglt2i": ("sglt2", "sglt-2", "sodium-glucose", "sodium glucose"),
    "mra": ("mineralocorticoid", "aldosterone antagonist", "mra", "spironolactone", "eplerenone"),
    "loop_diuretic": ("loop diuretic", "furosemide", "bumetanide", "torsemide"),
    "beta_blocker": ("beta blocker", "beta-blocker", "β-blocker"),
    "sacubitril_valsartan": ("sacubitril", "valsartan", "entresto", "arni"),
}

# Mapping từ specific drug names → drug class (for cross-reference checking)
DRUG_TO_CLASS: dict[str, str] = {
    # ACE Inhibitors
    "lisinopril": "ace_inhibitor",
    "enalapril": "ace_inhibitor",
    "ramipril": "ace_inhibitor",
    "captopril": "ace_inhibitor",
    "benazepril": "ace_inhibitor",
    "fosinopril": "ace_inhibitor",
    "moexipril": "ace_inhibitor",
    "perindopril": "ace_inhibitor",
    "quinapril": "ace_inhibitor",
    "trandolapril": "ace_inhibitor",
    # ARBs
    "valsartan": "arb",
    "losartan": "arb",
    "candesartan": "arb",
    "olmesartan": "arb",
    "telmisartan": "arb",
    "irbesartan": "arb",
    "azilsartan": "arb",
    "eprosartan": "arb",
    # MRA
    "spironolactone": "mra",
    "eplerenone": "mra",
    # Beta Blockers
    "metoprolol": "beta_blocker",
    "carvedilol": "beta_blocker",
    "bisoprolol": "beta_blocker",
    "atenolol": "beta_blocker",
    "propranolol": "beta_blocker",
    "nebivolol": "beta_blocker",
    # SGLT2i
    "dapagliflozin": "sglt2i",
    "empagliflozin": "sglt2i",
    "sotagliflozin": "sglt2i",
    "canagliflozin": "sglt2i",
    "ertugliflozin": "sglt2i",
    # Loop Diuretics
    "furosemide": "loop_diuretic",
    "bumetanide": "loop_diuretic",
    "torsemide": "loop_diuretic",
    "ethacrynic": "loop_diuretic",
    # ARNI
    "sacubitril/valsartan": "sacubitril_valsartan",
    "sacubitril": "sacubitril_valsartan",
}


def _drug_mentioned_in_evidence(drug: str, evidence_lower: str) -> bool:
    """Check if drug is mentioned in evidence text, allowing class-level mentions.

    Examples:
    - drug="lisinopril", evidence="patient on ACE inhibitor" → True (via DRUG_TO_CLASS)
    - drug="lisinopril", evidence="lisinopril 10mg daily" → True (direct match)
    - drug="metoprolol", evidence="beta blocker therapy" → True (via DRUG_TO_CLASS)
    """
    drug_normalized = str(drug).strip().lower().replace("_", " ")

    # 1. Direct exact match
    if (
        drug_normalized in evidence_lower
        or drug.replace("_", " ").lower() in evidence_lower
        or drug.replace("_", "-").lower() in evidence_lower
    ):
        return True

    # 2. Brand name variations
    variations = {
        "lisinopril": ("lisinopril", "prinivil", "zestril"),
        "carvedilol": ("carvedilol", "coreg"),
        "metoprolol": ("metoprolol", "lopressor", "toprol"),
        "spironolactone": ("spironolactone", "aldactone"),
        "furosemide": ("furosemide", "lasix"),
        "dapagliflozin": ("dapagliflozin", "forxiga"),
        "empagliflozin": ("empagliflozin", "jardiance"),
        "valsartan": ("valsartan", "diovan"),
        "losartan": ("losartan", "cozaar"),
        "candesartan": ("candesartan", "atacand"),
        "ramipril": ("ramipril", "altace"),
        "bisoprolol": ("bisoprolol", "zebeta"),
    }
    for canonical, aliases in variations.items():
        if drug_normalized == canonical or drug_normalized in aliases:
            if any(alias in evidence_lower for alias in aliases):
                return True

    # 3. Check if drug belongs to a class mentioned in evidence
    # e.g., drug="lisinopril" → class="ace_inhibitor" → check if "ace inhibitor" in evidence
    drug_class = DRUG_TO_CLASS.get(drug_normalized)
    if drug_class:
        class_cues = CLASS_DRUG_EVIDENCE_CUES.get(drug_class, ())
        if any(cue in evidence_lower for cue in class_cues):
            return True

    # 4. Also check if drug is already a class name
    class_key = str(drug).strip().lower()
    cues = CLASS_DRUG_EVIDENCE_CUES.get(class_key)
    if cues and any(cue in evidence_lower for cue in cues):
        return True

    return False


def validate_claim_evidence_alignment(
    claim: dict[str, Any],
    source_chunk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify claim is entailed by evidence text.

    This function checks that:
    1. The drug in the claim appears in the evidence
    2. Numeric thresholds in conditions appear in the evidence
    3. The claim type matches the evidence content

    Args:
        claim: The claim dictionary with evidence, drug, conditions, etc.
        source_chunk: Optional source chunk for additional validation

    Returns:
        Dict with aligned (bool), issues (list), and confidence_adjustment (float)
    """
    evidence = claim.get("evidence", "")
    conditions = claim.get("conditions", {})
    drug = claim.get("drug")
    claim_type = claim.get("claim_type", "")

    issues = []
    warnings = []
    confidence_adjustment = 0.0

    if not evidence:
        issues.append("No evidence text provided")
        return {
            "aligned": False,
            "issues": issues,
            "warnings": warnings,
            "confidence_adjustment": -0.2,
        }

    evidence_lower = evidence.lower()

    # Check 1: Drug appears in evidence (if drug is specified)
    # For drug_label: metadata drug is authoritative — SPL sentences often say "this product"
    # For guideline_recommendation: drug field may be a class name, not verbatim in span
    # For LLM-extracted claims: drug field may be set from metadata, not in evidence
    source_type = claim.get("source_type", "")
    extraction_method = (claim.get("metadata") or {}).get("extraction_method", "regex")
    skip_drug_in_evidence = (
        claim_type == "guideline_recommendation"
        or source_type == "drug_label"
        or str(claim.get("document_id") or "").endswith("_label")
        or extraction_method == "llm"  # LLM extraction sets drug from metadata
    )
    if drug and drug.strip() and not skip_drug_in_evidence:
        if not _drug_mentioned_in_evidence(str(drug), evidence_lower):
            # Only warn, don't fail — regex may extract drug from patterns
            # even if not verbatim in the specific evidence sentence
            warnings.append(
                f"Drug '{drug}' not explicitly found in evidence — may be class-level reference"
            )
            # Accumulate penalty (more negative is worse)
            confidence_adjustment = min(confidence_adjustment, -0.05)

    # Check 2: Numeric thresholds appear in evidence (warn only, don't fail)
    for key, value in conditions.items():
        if isinstance(value, dict) and "value" in value:
            threshold = str(value["value"])
            op = value.get("op", "")

            # Check for threshold in various formats
            threshold_patterns = [
                threshold,
                f"{op}{threshold}",
                f"{op} {threshold}",
            ]

            threshold_found = any(
                pattern in evidence for pattern in threshold_patterns
            )

            if not threshold_found:
                # Try to find approximate match (e.g., "30" vs "30 mL/min")
                number_match = re.search(rf"\b{threshold}(?:\s*[a-zA-Z/]*)?\b", evidence)
                if not number_match:
                    # Warn but don't fail — LLM may extract conditions from context
                    warnings.append(
                        f"Threshold '{threshold}' for condition '{key}' not found verbatim in evidence"
                    )
                    # Accumulate penalty (use more negative value)
                    confidence_adjustment = min(confidence_adjustment, -0.03)

    # Check 3: Claim type matches evidence content
    claim_type_evidence_map = {
        "contraindication": ["contraindicated", "contraindication", "must not", "should not be used"],
        "renal_constraint": ["egfr", "creatinine", "renal", "kidney", "crcl"],
        "hyperkalemia_risk": ["hyperkalemia", "hyperkalaemia", "potassium"],
        "dose_recommendation": ["dose", "dosage", "starting dose", "target dose", "mg", "administer"],
        "drug_interaction": ["interaction", "concomitant", "coadministration", "avoid"],
        "population_constraint": ["pregnancy", "lactation", "pediatric", "geriatric", "elderly"],
        "guideline_recommendation": ["recommend", "suggest", "should", "guideline"],
        "general_monitoring": ["monitor", "check", "measure", "follow-up", "assess"],
    }

    if claim_type in claim_type_evidence_map:
        keywords = claim_type_evidence_map[claim_type]
        if not any(keyword in evidence_lower for keyword in keywords):
            warnings.append(
                f"Claim type '{claim_type}' may not match evidence content"
            )
            confidence_adjustment = min(confidence_adjustment, -0.05)

    # Determine alignment status
    aligned = len(issues) == 0

    # Adjust confidence based on findings (accumulate from previous checks)
    # Issues are serious - cap at -0.15
    if issues:
        confidence_adjustment = min(confidence_adjustment, -0.15)

    return {
        "aligned": aligned,
        "issues": issues,
        "warnings": warnings,
        "confidence_adjustment": confidence_adjustment,
    }


def validate_claims_batch(
    claims: list[dict[str, Any]],
    source_chunks: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Validate a batch of claims for evidence alignment.

    Args:
        claims: List of claim dictionaries
        source_chunks: Optional dict mapping document_id to source chunks

    Returns:
        List of validation results with adjusted confidence
    """
    results = []

    for claim in claims:
        doc_id = claim.get("document_id", "")
        source_chunk = None

        if source_chunks and doc_id in source_chunks:
            source_chunk = source_chunks[doc_id]

        validation = validate_claim_evidence_alignment(claim, source_chunk)

        # Apply confidence adjustment
        original_confidence = claim.get("confidence", 0.8)
        adjusted_confidence = max(
            0.5,
            min(1.0, original_confidence + validation["confidence_adjustment"])
        )

        results.append({
            "claim_id": claim.get("claim_id"),
            "original_confidence": original_confidence,
            "adjusted_confidence": adjusted_confidence,
            "validation": validation,
        })

    return results


def compute_extraction_agreement(
    regex_claims: list[dict[str, Any]],
    llm_claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare claims from regex and LLM extraction methods.

    Args:
        regex_claims: Claims extracted via regex/pattern matching
        llm_claims: Claims extracted via LLM

    Returns:
        Dict with agreement metrics
    """
    if not regex_claims and not llm_claims:
        return {
            "regex_count": 0,
            "llm_count": 0,
            "concordant": 0,
            "regex_only": 0,
            "llm_only": 0,
            "agreement_rate": 0.0,
        }

    # Normalize evidence for comparison
    def normalize_evidence(text: str) -> str:
        return text.lower().strip()

    regex_evidence_set = {
        normalize_evidence(c.get("evidence", ""))
        for c in regex_claims
        if c.get("evidence")
    }
    llm_evidence_set = {
        normalize_evidence(c.get("evidence", ""))
        for c in llm_claims
        if c.get("evidence")
    }

    concordant = regex_evidence_set & llm_evidence_set
    regex_only = regex_evidence_set - llm_evidence_set
    llm_only = llm_evidence_set - regex_evidence_set

    total = len(regex_evidence_set | llm_evidence_set)
    agreement_rate = len(concordant) / max(1, total)

    return {
        "regex_count": len(regex_claims),
        "llm_count": len(llm_claims),
        "concordant": len(concordant),
        "regex_only": len(regex_only),
        "llm_only": len(llm_only),
        "agreement_rate": agreement_rate,
    }


def ensemble_confidence(
    regex_conf: float,
    llm_conf: float,
    concordant: bool,
) -> float:
    """Combine extraction confidences with agreement bonus.

    Args:
        regex_conf: Confidence from regex extraction (0-1)
        llm_conf: Confidence from LLM extraction (0-1)
        concordant: Whether both methods agree on the claim

    Returns:
        Ensemble confidence score
    """
    base = max(regex_conf, llm_conf)

    if concordant:
        # Agreement bonus - can be more confident
        return min(1.0, base + 0.05)
    else:
        # Disagreement - be more conservative
        return (regex_conf + llm_conf) / 2 * 0.9


# Confidence calibration tracking

CALIBRATION_BUCKETS = {
    "claims": {
        "buckets": [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)],
    }
}

# In-memory calibration data (would be persisted in production)
_calibration_data: dict[str, dict[int, dict[str, int]]] = {}


def record_confidence_outcome(
    claim_type: str,
    confidence: float,
    outcome: bool,
) -> None:
    """Track predicted confidence vs actual correctness.

    This function logs the predicted confidence and the actual outcome
    (e.g., from validation) to build calibration data over time.

    Args:
        claim_type: Type of claim (e.g., "contraindication", "dose_recommendation")
        confidence: Predicted confidence (0-1)
        outcome: Whether the prediction was correct (True/False)
    """
    if claim_type not in _calibration_data:
        _calibration_data[claim_type] = {}

    # Find the bucket
    buckets = CALIBRATION_BUCKETS.get("claims", {}).get("buckets", [])
    bucket_idx = None
    for idx, (low, high) in enumerate(buckets):
        if low <= confidence < high:
            bucket_idx = idx
            break
    if bucket_idx is None:
        bucket_idx = len(buckets) - 1  # Last bucket for >= 0.9

    if bucket_idx not in _calibration_data[claim_type]:
        _calibration_data[claim_type][bucket_idx] = {"correct": 0, "total": 0}

    _calibration_data[claim_type][bucket_idx]["total"] += 1
    if outcome:
        _calibration_data[claim_type][bucket_idx]["correct"] += 1


def compute_calibration_curve(claim_type: str) -> list[dict]:
    """Return expected vs observed accuracy per bucket for reliability diagrams.

    Args:
        claim_type: Type of claim to get calibration data for

    Returns:
        List of dicts with bucket range, expected (mean confidence), and observed accuracy
    """
    buckets = CALIBRATION_BUCKETS.get("claims", {}).get("buckets", [])
    result = []

    if claim_type not in _calibration_data:
        return result

    for idx, (low, high) in enumerate(buckets):
        if idx not in _calibration_data[claim_type]:
            continue

        data = _calibration_data[claim_type][idx]
        expected = (low + high) / 2
        observed = data["correct"] / data["total"] if data["total"] > 0 else 0

        result.append({
            "bucket": f"{low}-{high}",
            "expected": expected,
            "observed": observed,
            "correct": data["correct"],
            "total": data["total"],
            "count": data["total"],
        })

    return result


def get_calibration_summary() -> dict:
    """Get summary of calibration data for all claim types.

    Returns:
        Dict with calibration metrics
    """
    summary = {}

    for claim_type, buckets_data in _calibration_data.items():
        total_correct = 0
        total_count = 0

        for bucket_data in buckets_data.values():
            total_correct += bucket_data["correct"]
            total_count += bucket_data["total"]

        overall_accuracy = total_correct / total_count if total_count > 0 else 0
        summary[claim_type] = {
            "total_evaluated": total_count,
            "overall_accuracy": overall_accuracy,
            "calibration_samples": total_count,
        }

    return summary
