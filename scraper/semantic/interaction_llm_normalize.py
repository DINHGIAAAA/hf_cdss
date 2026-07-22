"""LLM-assisted partner token normalize for unmatched FDA interaction partners."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM = """You map free-text drug or drug-class mentions from FDA labels to canonical tokens.
Return JSON only: {"token": "<pipeline_id or class:name or null>", "confidence": 0.0-1.0}
Use class:* only for clear pharmacologic classes (class:beta_blocker, class:nsaid, class:statin,
class:anticoagulant, class:antiplatelet, class:qt_prolonging, class:insulin, class:mra, class:acei,
class:arb, class:sglt2i, class:non_dhp_ccb). Prefer a pipeline_id from the provided allowlist.
If unsure, return {"token": null, "confidence": 0.0}."""


def llm_normalize_partner(
    raw: str,
    *,
    allowlist: list[str],
    subject_drug: str | None = None,
) -> tuple[str | None, float]:
    """Ask LLM to map unmatched partner text. Returns (token, confidence) or (None, 0)."""
    try:
        from scraper.semantic.llm_client import call_llm_json, llm_available
    except ImportError:
        return None, 0.0

    if not llm_available():
        return None, 0.0

    sample = ", ".join(allowlist[:80])
    user = (
        f"Subject label drug: {subject_drug or 'unknown'}\n"
        f"Partner mention: {raw}\n"
        f"Allowed pipeline_ids (sample): {sample}\n"
        "Map the partner mention."
    )
    try:
        payload = call_llm_json(_SYSTEM, user, max_tokens=120)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM partner normalize failed for %r: %s", raw, exc)
        return None, 0.0

    if not isinstance(payload, dict):
        return None, 0.0
    token = payload.get("token")
    if not token or not isinstance(token, str):
        return None, 0.0
    token = token.strip().lower().replace(" ", "_")
    conf = float(payload.get("confidence") or 0.0)
    if token.startswith("class:"):
        return token, conf
    if token in set(allowlist):
        return token, conf
    return None, 0.0


def _max_llm_partners() -> int:
    raw = os.environ.get("HF_CDSS_INTERACTION_LLM_NORMALIZE_MAX", "80")
    try:
        return max(0, int(raw))
    except ValueError:
        return 80


def apply_llm_normalize_to_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite unmatched drug_set_b tokens when LLM returns a confident mapping.

    Unique partner strings are normalized once and reused (avoids N× LLM calls on
    repeated table junk / shared partners across labels).
    """
    try:
        from app.modules.drug_normalization.service import load_drug_catalog
    except ImportError:
        return claims

    catalog = load_drug_catalog()
    allowlist = sorted(
        {
            *(catalog.keys()),
            *(str(e.get("pipeline_id") or "") for e in catalog.values() if e.get("pipeline_id")),
        }
    )
    allowlist = [x for x in allowlist if x]

    cache: dict[str, tuple[str | None, float]] = {}
    pending_raws: list[str] = []
    for claim in claims:
        meta = claim.get("metadata") or {}
        resolve = meta.get("partner_resolve") or {}
        if resolve.get("matched") or not resolve.get("needs_llm"):
            continue
        raw = str(meta.get("partner_raw") or resolve.get("raw") or "").strip()
        if not raw:
            continue
        key = raw.lower()
        if key not in cache:
            cache[key] = (None, 0.0)  # placeholder so we collect unique order
            pending_raws.append(raw)

    cap = _max_llm_partners()
    if len(pending_raws) > cap:
        logger.warning(
            "LLM partner normalize: %s unique unmatched partners, capping at %s "
            "(set HF_CDSS_INTERACTION_LLM_NORMALIZE_MAX to raise)",
            len(pending_raws),
            cap,
        )
        pending_raws = pending_raws[:cap]

    for index, raw in enumerate(pending_raws, start=1):
        if index == 1 or index % 10 == 0 or index == len(pending_raws):
            logger.info("LLM partner normalize %s/%s: %r", index, len(pending_raws), raw[:60])
        cache[raw.lower()] = llm_normalize_partner(raw, allowlist=allowlist)

    updated: list[dict[str, Any]] = []
    for claim in claims:
        meta = dict(claim.get("metadata") or {})
        resolve = dict(meta.get("partner_resolve") or {})
        if resolve.get("matched") or not resolve.get("needs_llm"):
            updated.append(claim)
            continue

        raw = str(meta.get("partner_raw") or resolve.get("raw") or "")
        token, conf = cache.get(raw.lower(), (None, 0.0))
        if not token or conf < 0.6:
            updated.append(claim)
            continue

        new_claim = dict(claim)
        new_claim["drug_set_b"] = [token]
        new_meta = dict(meta)
        new_meta["partner_resolve"] = {
            **resolve,
            "matched": True,
            "method": "llm_normalize",
            "llm_confidence": conf,
            "llm_token": token,
        }
        new_meta["extraction_method"] = "fda_xml_drug_interactions+llm_normalize"
        new_claim["metadata"] = new_meta
        new_claim["confidence"] = max(float(claim.get("confidence") or 0.7), min(0.9, conf))
        updated.append(new_claim)
    return updated
