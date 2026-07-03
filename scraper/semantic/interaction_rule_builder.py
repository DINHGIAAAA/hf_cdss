"""Build executable interaction rules from structured interaction claims."""

from __future__ import annotations

import hashlib
import re
from typing import Any

KNOWN_CLASS_PREFIX = "class:"

REQUIRED_FIELDS = ("drug_set_a", "drug_set_b", "message", "severity")


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return value or "unknown"


def interaction_rule_id(parts: list[str]) -> str:
    base = "_".join(slug(part) for part in parts if part)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"ix_{base[:68]}_{digest}"


def _normalize_token(value: str) -> str:
    token = str(value or "").strip().lower()
    if token.startswith(KNOWN_CLASS_PREFIX):
        return token.replace(" ", "_")
    return token.replace(" ", "_")


def _normalize_set(values: list[Any] | None) -> list[str]:
    output: list[str] = []
    for item in values or []:
        token = _normalize_token(str(item))
        if token and token not in output:
            output.append(token)
    return output


def _partner_drugs_from_text(text: str) -> list[str]:
    partners: list[str] = []
    patterns = (
        r"concomitant(?:ly)?\s+(?:use\s+)?(?:with|administration\s+with)\s+([a-z0-9 /+-]{3,40})",
        r"combined\s+with\s+([a-z0-9 /+-]{3,40})",
        r"co-?administration\s+with\s+([a-z0-9 /+-]{3,40})",
        r"interaction\s+with\s+([a-z0-9 /+-]{3,40})",
    )
    haystack = text.lower()
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.I):
            candidate = match.group(1).strip(" .;,:")
            if candidate and candidate not in partners:
                partners.append(candidate.replace(" ", "_"))
    return partners[:3]


def _infer_target(set_a: list[str], set_b: list[str]) -> str:
    joined = " ".join(set_a + set_b)
    if "class:acei" in joined and "class:arb" in joined:
        return "RAAS_combination"
    if "class:raasi" in joined and "class:mra" in joined:
        return "RAASi_MRA"
    if "class:raasi" in joined and "class:nsaid" in joined:
        return "RAASi_NSAID"
    if "class:anticoagulant" in joined and "class:antiplatelet" in joined:
        return "bleeding_risk"
    return "general"


def build_interaction_rule_from_structured_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    if claim.get("claim_type") != "structured_interaction_rule":
        return None

    set_a = _normalize_set(claim.get("drug_set_a"))
    set_b = _normalize_set(claim.get("drug_set_b"))
    message = str(claim.get("message") or "").strip()
    severity = str(claim.get("severity") or "moderate").strip().lower()
    if not set_a or not set_b or len(message) < 10:
        return None
    if severity not in {"high", "moderate", "critical", "low"}:
        severity = "moderate"

    rule_id = interaction_rule_id([",".join(sorted(set_a)), ",".join(sorted(set_b)), message[:60]])
    rule_body = {
        "message": message,
        "action": claim.get("action") or "review",
        "target": claim.get("target") or _infer_target(set_a, set_b),
        "escalation": list(claim.get("escalation") or []),
        "monitoring": list(claim.get("monitoring") or []),
    }

    return {
        "rule_id": rule_id,
        "drug_set_a": set_a,
        "drug_set_b": set_b,
        "severity": severity,
        "rule_body": rule_body,
        "source_refs": [
            {
                "claim_id": claim.get("claim_id"),
                "document_id": claim.get("document_id"),
                "source_type": claim.get("source_type"),
                "source_section": claim.get("source_section"),
                "evidence": claim.get("evidence"),
                "confidence": claim.get("confidence"),
                "metadata": claim.get("metadata") or {},
            }
        ],
        "extraction_method": (claim.get("metadata") or {}).get("extraction_method", "llm_structured_interaction"),
        "source_confidence": claim.get("confidence"),
    }


def build_interaction_rule_from_drug_interaction_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    if claim.get("claim_type") != "drug_interaction":
        return None
    drug = _normalize_token(str(claim.get("drug") or ""))
    evidence = str(claim.get("evidence") or claim.get("claim") or "").strip()
    if not drug or len(evidence) < 20:
        return None

    partners = _partner_drugs_from_text(evidence)
    if not partners:
        return None

    severity = "high" if str(claim.get("action") or "") in {"avoid", "contraindicated", "not_recommended"} else "moderate"
    structured = {
        "claim_type": "structured_interaction_rule",
        "claim_id": claim.get("claim_id"),
        "document_id": claim.get("document_id"),
        "source_type": claim.get("source_type"),
        "source_section": claim.get("source_section"),
        "drug_set_a": [drug],
        "drug_set_b": partners,
        "severity": severity,
        "action": claim.get("action") or "review",
        "message": evidence[:500],
        "evidence": evidence,
        "confidence": claim.get("confidence") or 0.75,
        "metadata": {"extraction_method": "regex_drug_interaction_claim", **(claim.get("metadata") or {})},
    }
    return build_interaction_rule_from_structured_claim(structured)


def interaction_rules_from_claims(claims: list[dict]) -> list[dict]:
    rules: list[dict] = []
    seen: set[str] = set()
    for claim in claims:
        rule = build_interaction_rule_from_structured_claim(claim)
        if not rule:
            rule = build_interaction_rule_from_drug_interaction_claim(claim)
        if not rule or rule["rule_id"] in seen:
            continue
        seen.add(rule["rule_id"])
        rules.append(rule)
    return rules
