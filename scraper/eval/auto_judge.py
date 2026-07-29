"""Heuristic + optional LLM auto-evaluation of extracted claims (no manual labels)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from scraper.prompts.claim_auto_judge import CLAIM_AUTO_JUDGE_SYSTEM_PROMPT
from scraper.semantic.llm_client import call_llm_json, llm_available


NOISE_PATTERNS = (
    r"\bkeywords?\b",
    r"\bpermissions?\b",
    r"\btable of contents\b",
    r"\bcopyright\b",
    r"\ball rights reserved\b",
    r"\bmd,\s*macc\b",
    r"\bfaha\b.*\bfacc\b",
    r"\bet\s+al\.?\b",
    r"\bsupplemental (material|appendix)\b",
    r"\bdisclosure[s]?\b",
    r"\bconflict of interest\b",
)

# Weak spans that match type keywords but are not actionable rules.
WEAK_SPAN_PATTERNS = (
    r"^see (contraindications|warnings|precautions|drug interactions)\b",
    r"\bsee (contraindications|warnings|precautions)\b\.?\s*$",
    r"\bmean baseline (egfr|creatinine|egfr was)\b",
    r"\bwere not included in clinical\b",
    r"\bpackaging is open or damaged\b",
    r"\bprefilled syringe\b",
)

TYPE_CUES: dict[str, tuple[str, ...]] = {
    "contraindication": ("contraindicat", "must not", "do not administer", "do not use", "should not be used"),
    "renal_constraint": ("egfr", "creatinine clearance", "crcl", "renal impairment", "dialysis", "kidney"),
    "hyperkalemia_risk": ("hyperkalemia", "hyperkalaemia", "serum potassium", "potassium >"),
    "dose_recommendation": ("mg", "dose", "twice daily", "once daily", "titrate", "starting dose"),
    "drug_interaction": ("concomitant", "coadministrat", "drug interaction", "withhold", "avoid with"),
    "adverse_reaction": ("adverse", "reaction", "ketoacidosis", "hypotension", "bleeding"),
    "population_constraint": ("pregnancy", "pregnant", "lactation", "pediatric", "geriatric"),
    "usage_constraint": ("not recommended", "avoid use", "limitations of use", "should not"),
    "guideline_recommendation": ("recommend", "should", "is indicated", "is useful", "class of recommendation"),
    "general_monitoring": ("monitor", "check serum", "follow-up", "reassess"),
}

HARD_TYPES = {
    "contraindication",
    "renal_constraint",
    "hyperkalemia_risk",
    "drug_interaction",
    "population_constraint",
}


def heuristic_noise_score(evidence: str) -> float:
    """Return 0..1 likelihood the span is non-clinical noise."""
    text = (evidence or "").lower()
    if len(text) < 25:
        return 0.9
    hits = sum(1 for pattern in NOISE_PATTERNS if re.search(pattern, text, flags=re.I))
    # Dense author-like comma/credential patterns
    if text.count(",") >= 6 and re.search(r"\b(md|phd|facc|faha)\b", text, flags=re.I):
        hits += 2
    if text.count(";") >= 5 and "guideline" in text:
        hits += 1
    return min(1.0, hits / 3.0)


def _has_type_cues(evidence: str, claim_type: str | None) -> bool:
    if not claim_type:
        return False
    text = (evidence or "").lower()
    return any(cue in text for cue in TYPE_CUES.get(str(claim_type), ()))


def _is_weak_span(evidence: str) -> bool:
    text = (evidence or "").strip().lower()
    return any(re.search(pattern, text, flags=re.I) for pattern in WEAK_SPAN_PATTERNS)


def heuristic_verdict(claim: dict[str, Any]) -> dict[str, Any]:
    evidence = str(claim.get("evidence") or claim.get("claim") or "")
    noise = heuristic_noise_score(evidence)
    claim_type = claim.get("claim_type")
    drug = claim.get("drug")

    reasons: list[str] = []
    if noise >= 0.66:
        reasons.append("heuristic_noise")
    if _is_weak_span(evidence):
        reasons.append("weak_span")
    if claim_type in HARD_TYPES and not drug and claim.get("source_type") == "drug_label":
        reasons.append("missing_drug_on_label_claim")
    if claim_type and not _has_type_cues(evidence, str(claim_type)) and noise < 0.66:
        # Soft signal only — used later; do not auto-reject solely on missing cues.
        pass
    if claim_type == "population_constraint" and noise >= 0.33:
        reasons.append("weak_population_span")

    reject = bool(reasons)
    return {
        "verdict": "reject" if reject else "accept",
        "reasons": reasons or ["heuristic_ok"],
        "suggested_claim_type": claim_type,
        "grounded": noise < 0.5,
        "safety_relevant": claim_type in HARD_TYPES and noise < 0.5,
        "confidence": round(1.0 - noise, 3) if not reject else round(noise, 3),
        "judge": "heuristic",
        "noise_score": round(noise, 3),
    }


def _normalize_llm_result(
    result: dict[str, Any],
    claim: dict[str, Any],
    *,
    strong_model: bool = False,
) -> dict[str, Any]:
    """Repair junk outputs from small models; trust stronger models more."""
    evidence = str(claim.get("evidence") or claim.get("claim") or "")
    claim_type = str(claim.get("claim_type") or "")
    verdict = str(result.get("verdict") or "").lower()
    reason = result.get("reason")
    reasons = result.get("reasons")
    if isinstance(reason, str) and reason.strip():
        reason_list = [reason.strip()]
    elif isinstance(reasons, list):
        reason_list = [str(item) for item in reasons]
    else:
        reason_list = []

    junk_reasons = {claim_type, str(claim.get("drug") or ""), "contraindication", "ok"}
    only_junk = bool(reason_list) and all(
        (item.lower().strip() in {j.lower() for j in junk_reasons if j}) or len(item) < 3 for item in reason_list
    )

    # Strong models: only override empty/junk reject reasons.
    if strong_model:
        if verdict == "reject" and only_junk and _has_type_cues(evidence, claim_type) and not _is_weak_span(evidence):
            result = {
                **result,
                "verdict": "accept",
                "reasons": ["llm_reason_junk_overridden"],
                "judge": "llm_corrected",
                "grounded": True,
            }
        else:
            result["reasons"] = reason_list or (["ok"] if verdict == "accept" else ["llm_reject"])
        result["verdict"] = str(result.get("verdict") or "reject").lower()
        return result

    if verdict == "reject" and only_junk and _has_type_cues(evidence, claim_type) and not _is_weak_span(evidence):
        result = {
            **result,
            "verdict": "accept",
            "reasons": ["llm_reason_junk_overridden"],
            "judge": "llm_corrected",
            "grounded": True,
        }
    elif verdict == "reject" and _has_type_cues(evidence, claim_type) and not _is_weak_span(evidence):
        explicit = {"noise", "type_mismatch", "not_clinical", "weak_span", "heuristic_noise"}
        if not any(str(item).lower() in explicit for item in reason_list):
            joined = " ".join(reason_list).lower()
            if "not a clinical" in joined or "does not clearly" in joined or "type_mismatch" in joined:
                result["reasons"] = reason_list or ["llm_reject"]
            else:
                result = {
                    **result,
                    "verdict": "accept",
                    "reasons": ["llm_over_reject_corrected"],
                    "judge": "llm_corrected",
                    "grounded": True,
                }
        else:
            result["reasons"] = reason_list or ["llm_reject"]
    else:
        result["reasons"] = reason_list or (["ok"] if verdict == "accept" else ["llm_reject"])

    result["verdict"] = str(result.get("verdict") or "reject").lower()
    return result


def _is_strong_judge_model(model: str) -> bool:
    name = (model or "").lower()
    # Treat 7b+ instruct models as strong enough to trust explicit rejects.
    for marker in ("7b", "14b", "32b", "72b"):
        if marker in name:
            return True
    return False


def llm_verdict(
    claim: dict[str, Any],
    *,
    model: str = "qwen2.5:7b",
    timeout_seconds: float = 120.0,
) -> dict[str, Any] | None:
    payload = {
        "task": "accept_or_reject_claim_for_hf_cdss_knowledge_graph",
        "claim_type": claim.get("claim_type"),
        "drug": claim.get("drug"),
        "source_type": claim.get("source_type"),
        "evidence": str(claim.get("evidence") or claim.get("claim") or "")[:600],
    }
    strong = _is_strong_judge_model(model)
    result = call_llm_json(
        CLAIM_AUTO_JUDGE_SYSTEM_PROMPT,
        json.dumps(payload, ensure_ascii=False),
        max_tokens=64,
        model=model,
        timeout_seconds=timeout_seconds,
        num_ctx=1536 if strong else 1024,
    )
    if not isinstance(result, dict):
        return None
    verdict = str(result.get("verdict") or "").lower()
    if verdict not in {"accept", "reject"}:
        return None
    result["model"] = model
    result = _normalize_llm_result(result, claim, strong_model=strong)
    if "judge" not in result:
        result["judge"] = "llm"
    return result


def judge_claim(
    claim: dict[str, Any],
    *,
    use_llm: bool,
    model: str = "qwen2.5:7b",
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    base = heuristic_verdict(claim)
    # Always reject clear noise / weak spans without spending LLM tokens.
    if base["noise_score"] >= 0.66 or "weak_span" in base["reasons"]:
        return base
    if not use_llm or not llm_available():
        return base
    judged = llm_verdict(claim, model=model, timeout_seconds=timeout_seconds)
    if judged is None:
        base["judge"] = "heuristic_llm_unavailable"
        return base
    # Soft heuristic rejects: allow confident LLM accept to override.
    if base["verdict"] == "reject" and judged.get("verdict") == "accept":
        conf = float(judged.get("confidence") or 0)
        strong = _is_strong_judge_model(model)
        if conf < (0.6 if strong else 0.8) and judged.get("judge") != "llm_corrected":
            judged["verdict"] = "reject"
            judged["reasons"] = list(judged.get("reasons") or []) + ["deferred_to_heuristic"]
    judged["noise_score"] = base["noise_score"]
    return judged


def aggregate_auto_metrics(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(judgments)
    accept = sum(1 for row in judgments if row.get("verdict") == "accept")
    reject = total - accept
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"accept": 0, "reject": 0})
    hard = {"accept": 0, "reject": 0}
    noise_rejects = 0
    for row in judgments:
        ctype = str(row.get("claim_type") or "null")
        verdict = str(row.get("verdict") or "reject")
        by_type[ctype][verdict] += 1
        if row.get("claim_type") in HARD_TYPES:
            hard[verdict] += 1
        if "heuristic_noise" in (row.get("reasons") or []):
            noise_rejects += 1

    def rate(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    return {
        "n": total,
        "accept": accept,
        "reject": reject,
        "estimated_precision": rate(accept, total),
        "hard_types": {
            "n": hard["accept"] + hard["reject"],
            "estimated_precision": rate(hard["accept"], hard["accept"] + hard["reject"]),
            "accept": hard["accept"],
            "reject": hard["reject"],
        },
        "noise_reject_rate": rate(noise_rejects, total),
        "per_claim_type": {
            ctype: {
                "n": vals["accept"] + vals["reject"],
                "estimated_precision": rate(vals["accept"], vals["accept"] + vals["reject"]),
                "accept": vals["accept"],
                "reject": vals["reject"],
            }
            for ctype, vals in sorted(by_type.items())
        },
    }
