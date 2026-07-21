"""Extract drug-drug interaction claims from FDA SPL XML labels.

Mirrors the dose_calculation XML approach: parse Drug Interactions sections
(title and/or LOINC displayName), then derive structured claims from tables
and subsection prose. Partner tokens are normalized via aliases/classes;
optional LLM normalize is applied by the scraper CLI when enabled.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.modules.dose_calculation.xml_dose_extractor import (
    _direct_text_block,
    _iter_sections,
    _load_selector,
    _normalize_ws,
    _parse_tables,
    _section_code_name,
    _section_title,
)
from app.modules.interaction_checking.partner_normalize import (
    infer_action_severity_monitoring,
    resolve_partner_token,
    split_partner_mentions,
)

DRUG_LABELS_DIR = Path("data/heart_failure/raw/drug_labels")

_INTERACTION_CODE_HINTS = (
    "DRUG INTERACTIONS",
    "DRUG INTERACTION",
)

_SKIP_ROW_MARKERS = (
    "pharmacodynamic interactions",
    "pharmacokinetic interactions",
    "concomitant drug class",
    "clinical comment",
    "clinical impact",
    "intervention",
    "examples",
    "na = not available",
    "digoxin concentrations increased",
    "digoxin concentrations decreased",
    "recommendations",
)


def _claim_id(pipeline_id: str, partner: str, evidence: str, index: int) -> str:
    raw = f"{pipeline_id}|{partner}|{index}|{evidence[:120]}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"ix_fda_{digest}"


def _is_drug_interactions_section(title: str, code_name: str) -> bool:
    blob = f"{title} {code_name}".upper()
    if "LABORATORY" in blob and "INTERACTION" in blob:
        return False
    return any(hint in blob for hint in _INTERACTION_CODE_HINTS)


def _row_is_header_or_spacer(cells: list[str]) -> bool:
    joined = " ".join(cells).strip().lower()
    if not joined or len(joined) < 3:
        return True
    if any(marker in joined for marker in _SKIP_ROW_MARKERS) and len(cells) <= 2:
        return True
    # Warfarin-style Impact / Intervention label rows
    if joined.rstrip(":") in {"clinical impact", "intervention"}:
        return True
    # Single-cell category banners
    if len([c for c in cells if c.strip()]) == 1 and len(joined) < 80:
        if "interaction" in joined or joined.endswith("interactions"):
            return True
    return False


def _extract_interaction_sections(sel) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for section in _iter_sections(sel):
        title = _section_title(section)
        code_name = _section_code_name(section)
        if not _is_drug_interactions_section(title, code_name):
            continue
        if not title:
            title = code_name or "DRUG INTERACTIONS"

        subsections: list[dict[str, Any]] = []
        for subsec in section.xpath("./component/section"):
            sub_title = _section_title(subsec)
            content = _direct_text_block(subsec)
            tables = _parse_tables(subsec)
            nested = subsec.xpath("./component/section")
            if nested:
                for child in nested:
                    child_title = _section_title(child)
                    child_content = _direct_text_block(child)
                    child_tables = _parse_tables(child)
                    if child_title or len(child_content) > 40 or child_tables:
                        subsections.append(
                            {
                                "title": child_title or sub_title,
                                "content": child_content,
                                "tables": child_tables,
                            }
                        )
            subsections.append(
                {
                    "title": sub_title,
                    "content": content,
                    "tables": tables,
                }
            )

        sections.append(
            {
                "title": title,
                "content": _direct_text_block(section),
                "tables": _parse_tables(section),
                "subsections": subsections,
            }
        )
    return sections


def _make_claim(
    *,
    pipeline_id: str,
    partner_raw: str,
    evidence: str,
    section_title: str,
    source_xml: str,
    index: int,
    partner_hint: str | None = None,
) -> dict[str, Any] | None:
    evidence = _normalize_ws(evidence)
    if len(evidence) < 20:
        return None

    token, meta = resolve_partner_token(partner_hint or partner_raw)
    if not token:
        return None
    if token == pipeline_id or token == f"class:{pipeline_id}":
        return None

    action, severity, monitoring = infer_action_severity_monitoring(evidence)
    claim_id = _claim_id(pipeline_id, token, evidence, index)
    return {
        "claim_type": "structured_interaction_rule",
        "claim_id": claim_id,
        "document_id": pipeline_id,
        "source_type": "drug_label",
        "source_section": section_title,
        "drug_set_a": [pipeline_id],
        "drug_set_b": [token],
        "severity": severity,
        "action": action,
        "message": evidence[:500],
        "monitoring": monitoring,
        "evidence": evidence[:800],
        "confidence": 0.92 if meta.get("matched") else 0.72,
        "evidence_ref": f"fda_label:{pipeline_id}:drug_interactions",
        "metadata": {
            "extraction_method": "fda_xml_drug_interactions",
            "partner_raw": partner_raw,
            "partner_resolve": meta,
            "source_xml": source_xml,
            "pipeline_id": pipeline_id,
        },
    }


def _claims_from_table_row(
    *,
    pipeline_id: str,
    cells: list[str],
    section_title: str,
    source_xml: str,
    index_start: int,
) -> list[dict[str, Any]]:
    cells = [_normalize_ws(c) for c in cells if _normalize_ws(c)]
    if _row_is_header_or_spacer(cells):
        return []
    if len(cells) < 2:
        return []

    partner_cell = cells[0]
    examples_cell = cells[1] if len(cells) >= 3 else ""
    comment_cell = cells[-1] if len(cells) >= 2 else ""

    # Digoxin-style: [Partner, %, %, Recommendations]
    if len(cells) >= 4 and re.search(r"\d+\s*%", cells[1] or ""):
        examples_cell = ""
        comment_cell = cells[-1]

    evidence = comment_cell or " ".join(cells[1:])
    if len(evidence) < 15:
        return []

    partners = split_partner_mentions(examples_cell) if examples_cell else []
    if not partners:
        partners = split_partner_mentions(partner_cell)
    if not partners:
        partners = [partner_cell]

    claims: list[dict[str, Any]] = []
    for offset, partner in enumerate(partners):
        claim = _make_claim(
            pipeline_id=pipeline_id,
            partner_raw=partner,
            evidence=evidence,
            section_title=section_title,
            source_xml=source_xml,
            index=index_start + offset,
            partner_hint=partner,
        )
        if claim:
            # Prefer class token from the row header when examples expand to many drugs
            class_token, class_meta = resolve_partner_token(partner_cell)
            if (
                class_token.startswith("class:")
                and class_meta.get("matched")
                and claim["drug_set_b"][0] != class_token
                and len(partners) > 3
            ):
                # Also emit a class-level claim once (handled by caller dedupe)
                class_claim = _make_claim(
                    pipeline_id=pipeline_id,
                    partner_raw=partner_cell,
                    evidence=evidence,
                    section_title=section_title,
                    source_xml=source_xml,
                    index=index_start + offset + 1000,
                    partner_hint=partner_cell,
                )
                if class_claim:
                    claims.append(class_claim)
            claims.append(claim)
    return claims


def _claims_from_prose(
    *,
    pipeline_id: str,
    text: str,
    section_title: str,
    source_xml: str,
    index_start: int,
) -> list[dict[str, Any]]:
    text = _normalize_ws(text)
    if len(text) < 40:
        return []

    patterns = (
        r"(?:concomitant(?:ly)?\s+(?:use\s+)?(?:with|of)|combined with|co-?administration with|"
        r"avoid(?:\s+concomitant)?\s+use\s+with|interaction(?:s)?\s+with)\s+"
        r"([A-Za-z][A-Za-z0-9 \-/\+]{2,60})",
        r"\b([A-Z][a-z]+(?:\s+[a-z]+)?)\s+(?:may|can|will)?\s*(?:increase|decrease|potentiate|"
        r"reduce|elevate)[^.!?]{0,80}(?:digoxin|warfarin|amiodarone|exposure|level|concentration)",
    )
    claims: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            partner_raw = match.group(1).strip(" .;,:")
            if len(partner_raw) < 3:
                continue
            # Skip generic phrases
            if partner_raw.lower() in {
                "drugs",
                "other drugs",
                "these drugs",
                "strong inhibitors",
                "pgp",
                "cyp3a4",
            }:
                continue
            start = max(0, match.start() - 40)
            end = min(len(text), match.end() + 180)
            evidence = text[start:end]
            key = partner_raw.lower()
            if key in seen:
                continue
            seen.add(key)
            claim = _make_claim(
                pipeline_id=pipeline_id,
                partner_raw=partner_raw,
                evidence=evidence,
                section_title=section_title,
                source_xml=source_xml,
                index=index_start + len(claims),
            )
            if claim:
                claims.append(claim)
            if len(claims) >= 12:
                return claims
    return claims


def extract_interaction_claims_from_label(xml_path: Path | str) -> list[dict[str, Any]]:
    """Parse one FDA label XML and return structured interaction claims."""
    path = Path(xml_path)
    pipeline_id = path.parent.name
    source_xml = str(path).replace("\\", "/")
    sel = _load_selector(path)
    sections = _extract_interaction_sections(sel)
    claims: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def _add(claim: dict[str, Any] | None) -> None:
        if not claim:
            return
        key = (
            claim["drug_set_a"][0],
            claim["drug_set_b"][0],
            (claim.get("message") or "")[:120],
        )
        if key in seen_keys:
            return
        seen_keys.add(key)
        claims.append(claim)

    for section in sections:
        section_title = section.get("title") or "DRUG INTERACTIONS"
        for table in section.get("tables") or []:
            for row in table.get("rows") or []:
                for claim in _claims_from_table_row(
                    pipeline_id=pipeline_id,
                    cells=list(row),
                    section_title=section_title,
                    source_xml=source_xml,
                    index_start=len(claims),
                ):
                    _add(claim)

        for sub in section.get("subsections") or []:
            sub_title = sub.get("title") or section_title
            for table in sub.get("tables") or []:
                for row in table.get("rows") or []:
                    for claim in _claims_from_table_row(
                        pipeline_id=pipeline_id,
                        cells=list(row),
                        section_title=sub_title,
                        source_xml=source_xml,
                        index_start=len(claims),
                    ):
                        _add(claim)
            # Named drug in subsection title (e.g. "Warfarin")
            title = sub.get("title") or ""
            title_partners = split_partner_mentions(re.sub(r"^\d+(\.\d+)*\s*", "", title))
            content = sub.get("content") or ""
            if title_partners and len(content) >= 20:
                for partner in title_partners[:3]:
                    _add(
                        _make_claim(
                            pipeline_id=pipeline_id,
                            partner_raw=partner,
                            evidence=content[:500],
                            section_title=sub_title,
                            source_xml=source_xml,
                            index=len(claims),
                        )
                    )
            for claim in _claims_from_prose(
                pipeline_id=pipeline_id,
                text=content,
                section_title=sub_title,
                source_xml=source_xml,
                index_start=len(claims),
            ):
                _add(claim)

        for claim in _claims_from_prose(
            pipeline_id=pipeline_id,
            text=section.get("content") or "",
            section_title=section_title,
            source_xml=source_xml,
            index_start=len(claims),
        ):
            _add(claim)

    return claims


def extract_all_interaction_claims(
    drug_labels_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Extract interaction claims from all `*_label.xml` files under the labels root."""
    root = Path(drug_labels_dir or DRUG_LABELS_DIR)
    xml_files = sorted(root.rglob("*_label.xml"))
    all_claims: list[dict[str, Any]] = []
    for xml_path in xml_files:
        try:
            all_claims.extend(extract_interaction_claims_from_label(xml_path))
        except Exception as exc:  # noqa: BLE001 — continue batch on bad labels
            all_claims.append(
                {
                    "claim_type": "extraction_error",
                    "document_id": xml_path.parent.name,
                    "evidence": str(exc),
                    "metadata": {"extraction_method": "fda_xml_drug_interactions", "source_xml": str(xml_path)},
                }
            )
    return [c for c in all_claims if c.get("claim_type") == "structured_interaction_rule"]
