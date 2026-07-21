"""Extract dose rules from FDA XML drug labels.

Uses Parsel (https://github.com/scrapy/parsel) for XPath-based SPL parsing,
then derives structured dosing and safety thresholds from section text.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from parsel import Selector


# FDA SPL default namespace (stripped via Selector.remove_namespaces())
SPL_NS = "urn:hl7-org:v3"


def parse_drug_label(xml_path: Path) -> dict[str, Any]:
    """Parse a single FDA XML drug label and extract dosing information."""
    sel = _load_selector(xml_path)

    drug_name = _extract_drug_name(sel)
    dosage_info = _extract_dosage_sections(sel)
    renal_adj = _extract_renal_adjustments(sel)
    contraindications = _extract_contraindications(sel)
    warnings = _extract_warnings(sel)

    label_text = _collect_label_text(sel)
    # Prefer thresholds stated in Warnings / Contraindications (actionable),
    # then fill gaps from the full label text.
    priority_blob = _normalize_ws(
        f"{_warnings_blob(warnings)} {' '.join(contraindications)}"
    )
    safety_priority = _extract_safety_adjustments(priority_blob) if priority_blob else {
        "potassium_adjustments": [],
        "heart_rate_adjustments": [],
        "bp_adjustments": [],
        "monitoring": [],
    }
    safety_full = _extract_safety_adjustments(label_text)
    safety = _merge_safety_adjustments(safety_priority, safety_full)

    # Also mine eGFR/CrCl rules from full label + dosage sections
    dosage_blob = " ".join(
        f"{s.get('title','')} {s.get('content','')} {_tables_text(s.get('tables'))}"
        for block in dosage_info
        for s in [block, *(block.get("subsections") or [])]
    )
    renal_blob = " ".join(
        f"{r.get('section_title','')} {r.get('content','')} {_tables_text(r.get('tables'))}"
        for r in renal_adj
    )
    egfr_rules = _extract_egfr_rules_from_text(
        _normalize_ws(f"{label_text} {dosage_blob} {renal_blob}")
    )
    # Digoxin-style CrCl dosing tables live under dosage sections
    for block in dosage_info:
        for s in [block, *(block.get("subsections") or [])]:
            egfr_rules.extend(_extract_egfr_from_crcl_tables(s.get("tables") or []))

    multi_factor = _extract_multi_factor_dose_rules_from_text(
        _normalize_ws(f"{dosage_blob} {label_text}")
    )
    # Apixaban / ESRD: CrCl <15 note (caution — label still allows dialysis dosing via PK)
    egfr_rules.extend(_extract_apixaban_crcl_notes(label_text))

    return {
        "drug_name": drug_name,
        "pipeline_id": Path(xml_path).parent.name,
        "source_xml": str(xml_path),
        "dosage_information": dosage_info,
        "renal_adjustments": renal_adj,
        "contraindications": contraindications,
        "warnings": warnings,
        "egfr_adjustments": _dedupe_egfr_rules(egfr_rules),
        "multi_factor_adjustments": multi_factor,
        "potassium_adjustments": safety["potassium_adjustments"],
        "heart_rate_adjustments": safety["heart_rate_adjustments"],
        "bp_adjustments": safety["bp_adjustments"],
        "monitoring": safety["monitoring"],
    }


def _tables_text(tables: list[dict] | None) -> str:
    if not tables:
        return ""
    parts = []
    for table in tables:
        for row in table.get("rows") or []:
            parts.append(" | ".join(row))
    return " ".join(parts)


def _load_selector(xml_path: Path) -> Selector:
    """Load FDA SPL XML into a Parsel Selector with namespaces removed."""
    xml_text = Path(xml_path).read_text(encoding="utf-8")
    sel = Selector(text=xml_text, type="xml")
    # SPL uses urn:hl7-org:v3 everywhere; stripping makes XPath readable.
    sel.remove_namespaces()
    return sel


def _normalize_ws(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _node_text(node: Selector) -> str:
    """Join all descendant text nodes under a selector."""
    return _normalize_ws(" ".join(node.xpath(".//text()").getall()))


def _direct_text_block(section: Selector) -> str:
    """Text content belonging to a section (excluding nested component/sections)."""
    texts = section.xpath("./text")
    if texts:
        content = _node_text(texts[0])
        if content:
            return content

    # Some SPLs omit <text> and put dosing prose under other children.
    parts: list[str] = []
    for child in section.xpath(
        "./*[local-name()!='component' and local-name()!='title' "
        "and local-name()!='id' and local-name()!='code' and local-name()!='effectiveTime']"
    ):
        parts.append(_node_text(child))
    content = _normalize_ws(" ".join(p for p in parts if p))
    if content:
        return content

    full = _node_text(section)
    nested = _normalize_ws(
        " ".join(_node_text(n) for n in section.xpath("./component/section"))
    )
    if nested and nested in full:
        full = full.replace(nested, " ")
    return _normalize_ws(full)


def _extract_drug_name(sel: Selector) -> str:
    """Extract the drug name from SPL manufactured product nodes."""
    xpaths = [
        "//manufacturedProduct/manufacturedProduct/name/text()",
        "//manufacturedMaterialKind/name/text()",
        "//manufacturedProduct//name/text()",
        "//document/title//text()",
        "//title/text()",
    ]
    for xp in xpaths:
        values = [_normalize_ws(v) for v in sel.xpath(xp).getall()]
        for value in values:
            if value:
                return value
    return "Unknown"


def _parse_tables(section: Selector) -> list[dict[str, Any]]:
    """Parse tables under a section via XPath."""
    parsed: list[dict[str, Any]] = []
    for table in section.xpath(".//table"):
        rows: list[list[str]] = []
        for tr in table.xpath(".//tr"):
            cells = []
            for cell in tr.xpath("./th|./td"):
                cell_text = _node_text(cell)
                if cell_text:
                    cells.append(cell_text)
            if cells:
                rows.append(cells)
        if rows:
            parsed.append({"rows": rows})
    return parsed


def _iter_sections(sel: Selector) -> list[Selector]:
    return sel.xpath("//section")


def _section_title(section: Selector) -> str:
    title_nodes = section.xpath("./title")
    if title_nodes:
        return _node_text(title_nodes[0])
    return _normalize_ws(section.xpath("./title/text()").get())


def _section_code_name(section: Selector) -> str:
    return _normalize_ws(" ".join(section.xpath("./code/@displayName").getall()))


def _is_dosage_administration_section(title: str, code_name: str) -> bool:
    """Match Dosage & Administration even when SPL omits <title> and only has LOINC code."""
    blob = f"{title} {code_name}".upper()
    if "OVERDOSAGE" in blob:
        return False
    if "DOSAGE FORMS" in blob or "DOSAGE FORM" in blob:
        return False
    if "DOSAGE" in blob and "ADMINISTRATION" in blob:
        return True
    if "DIRECTIONS" in blob:
        return True
    # Some older SPLs title only "DOSAGE"
    if title and re.search(r"^\s*\d*\s*DOSAGE\b", title, re.I) and "FORM" not in title.upper():
        return True
    return False


def _extract_dosage_sections(sel: Selector) -> list[dict[str, Any]]:
    """Extract dosage and administration sections."""
    sections: list[dict[str, Any]] = []

    for section in _iter_sections(sel):
        title = _section_title(section)
        code_name = _section_code_name(section)
        if not _is_dosage_administration_section(title, code_name):
            continue
        if not title:
            title = code_name or "DOSAGE AND ADMINISTRATION"

        subsections: list[dict[str, Any]] = []
        for subsec in section.xpath("./component/section"):
            sub_title = _section_title(subsec)
            nested = subsec.xpath("./component/section")
            content = _direct_text_block(subsec)
            tables = _parse_tables(subsec)
            if nested:
                for child in nested:
                    child_title = _section_title(child)
                    child_content = _direct_text_block(child)
                    child_tables = _parse_tables(child)
                    if child_title or len(child_content) > 40 or child_tables:
                        subsections.append({
                            "title": child_title or sub_title,
                            "content": child_content,
                            "tables": child_tables,
                        })
                if content or tables:
                    subsections.append({
                        "title": sub_title,
                        "content": content,
                        "tables": tables,
                    })
            else:
                subsections.append({
                    "title": sub_title,
                    "content": content,
                    "tables": tables,
                })

        sections.append({
            "title": title,
            "content": _direct_text_block(section),
            "tables": _parse_tables(section),
            "subsections": subsections,
        })

    return sections


def _extract_renal_adjustments(sel: Selector) -> list[dict[str, Any]]:
    """Extract renal impairment / eGFR / CrCl sections (title or content)."""
    search_terms = (
        "renal impairment",
        "renal function",
        "creatinine clearance",
        "dialysis",
        "egfr",
        "dosage adjustment for severe renal",
        "patients with heart failure and renal",
    )
    adjustments: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for section in _iter_sections(sel):
        title = _section_title(section)
        content = _direct_text_block(section)
        title_lower = (title or "").lower()
        content_lower = content.lower()
        titled = any(term in title_lower for term in search_terms)
        content_hit = any(
            term in content_lower
            for term in ("egfr", "creatinine clearance", "crcl", "renal impairment")
        ) and (
            "dose" in content_lower
            or "dosage" in content_lower
            or "initiat" in content_lower
            or "contraindic" in content_lower
            or "not recommended" in content_lower
        )
        if not titled and not content_hit:
            continue
        key = title or content[:40]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        adjustments.append({
            "section_title": title,
            "content": content,
            "extracted_values": _extract_egfr_values(content),
            "tables": _parse_tables(section),
        })

    return adjustments


# Span that tolerates decimals like "1.73 m2" inside FDA renal units (avoids
# stopping at the '.' in mL/min/1.73). Stops at sentence end ". " or end of text.
_EGFR_SPAN = r"(?:(?!\.\s).){0,160}?"


def _extract_egfr_values(text: str) -> list[dict[str, Any]]:
    """Extract eGFR/CrCl values and corresponding dose adjustments from text.

    Prefer conservative matches only — full prose mining lives in
    ``_extract_egfr_rules_from_text``.
    """
    values: list[dict[str, Any]] = []
    span = _EGFR_SPAN
    # Require mL/min (or clear comparator) near the renal number; reject mg/kg noise.
    patterns = [
        (
            rf"(?:creatinine clearance|eGFR|CrCl)\s*"
            rf"(?:less than or equal to|less than|≤|<=|<|>|≥|>=)?\s*"
            rf"(\d+)\s*(?:to|-)?\s*(\d+)?\s*mL/min{span}"
            rf"(?:dose|first dose|recommended|initiat\w*|start){span}"
            rf"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*kg)",
            "range",
        ),
        (
            rf"(?:eGFR|creatinine clearance|CrCl)\s*[<>]=?\s*(\d+)\s*mL/min{span}"
            rf"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*kg)",
            "max",
        ),
    ]

    for pattern, kind in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            g = match.groups()
            try:
                if kind == "range":
                    min_val = int(g[0])
                    max_val = int(g[1]) if g[1] else min_val
                    dose = float(g[2])
                else:
                    min_val = int(g[0])
                    max_val = min_val
                    dose = float(g[1])
                if dose <= 0 or dose > 1000:
                    continue
                if "mg/kg" in match.group(0).lower():
                    continue
                values.append({
                    "egfr_min": min_val,
                    "egfr_max": max_val,
                    "dose_mg": dose,
                })
            except (ValueError, IndexError, TypeError):
                continue

    return values


def _extract_egfr_rules_from_text(text: str) -> list[dict[str, Any]]:
    """Mine structured eGFR/CrCl dose rules from FDA label prose."""
    rules: list[dict[str, Any]] = []
    if not text:
        return rules

    span = _EGFR_SPAN
    patterns: list[tuple[str, str]] = [
        # spironolactone: eGFR between 30 and 50 ... 25 mg every other day
        (
            rf"eGFR\s+between\s+(\d+)\s+and\s+(\d+){span}"
            rf"(?:initiat\w*|consider){span}(\d+(?:\.\d+)?)\s*mg"
            rf"((?:(?!\.\s).){{0,40}}?every other day)?",
            "range_dose",
        ),
        # eGFR >50 ... 25 mg once daily
        (
            rf"eGFR\s*(?:>|≥|greater than)\s*(\d+){span}"
            rf"(?:initiat\w*|start){span}(\d+(?:\.\d+)?)\s*mg"
            rf"((?:(?!\.\s).){{0,40}}?(?:once daily|every other day|twice daily))?",
            "min_dose",
        ),
        # CrCl / eGFR ≤30 ... 2.5 mg / contraindicated
        (
            rf"(?:creatinine clearance|eGFR|CrCl)\s*"
            rf"(?:less than or equal to|≤|<=|less than|<)\s*(\d+){span}"
            rf"(contraindic\w*|not recommended|do not|avoid|"
            rf"(?:dose|first dose|initiat\w*|start){span}(\d+(?:\.\d+)?)\s*mg)",
            "max_action",
        ),
        # CrCl <40 ... initial daily dose should be 2.5 mg
        (
            rf"(?:creatinine clearance|eGFR|CrCl)\s*(?:less than|<|≤|<=)\s*(\d+){span}"
            rf"(?:initial|starting|dose should be|start)\s*(?:daily dose\s*)?"
            rf"(?:should be\s*)?(\d+(?:\.\d+)?)\s*mg",
            "max_dose",
        ),
        # Half starting dose when eGFR < 30 (sacubitril/valsartan)
        (
            rf"(?:half(?:\s+of)?\s+the\s+starting\s+dose|start.{{0,40}}?at half){span}"
            rf"(?:eGFR|estimated glomerular filtration rate){span}"
            rf"(?:less than|<|≤|<=)\s*(\d+)",
            "half_start_max",
        ),
        (
            rf"(?:eGFR|estimated glomerular filtration rate){span}"
            rf"(?:less than|<|≤|<=)\s*(\d+){span}"
            rf"(?:half(?:\s+of)?\s+the\s+(?:usually\s+)?(?:recommended\s+)?starting\s+dose|"
            rf"start.{{0,40}}?at half)",
            "half_start_max",
        ),
        # eGFR ≥25 to <60 ... 10 mg (finerenone bands) — dose must be near the band
        (
            rf"eGFR\s*(?:≥|>=|greater than or equal to)\s*(\d+)\s*to\s*"
            rf"(?:<|less than)\s*(\d+)\s*mL/min[^\d]{{0,50}}?"
            rf"(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*kg)",
            "range_dose_ge_lt",
        ),
        (
            rf"eGFR\s*(?:≥|>=|greater than or equal to)\s*(\d+){span}"
            rf"(?:initiat\w*|start|recommended){span}(\d+(?:\.\d+)?)\s*mg(?!\s*/\s*kg)",
            "min_dose",
        ),
        # No dose adjustment at/above eGFR X (SGLT2i HF)
        (
            rf"eGFR\s*(?:greater than or equal to|≥|>=)\s*(\d+){span}"
            rf"(?:same as the recommended dosage|no dose adjustment)",
            "min_none",
        ),
        (
            rf"no dose adjustment is recommended{span}"
            rf"eGFR\s*(?:greater than or equal to|≥|>=)\s*(\d+)",
            "min_none",
        ),
        # Reverse order: "not recommended when eGFR is less than 45"
        (
            rf"(?:not recommended|do not (?:initiate|start)|avoid(?:\s+use)?|"
            rf"discontinue(?:\s+therapy)?(?:\s+for\s+worsening)?)"
            rf".{{0,80}}?eGFR\s*(?:is\s+|to\s+)?(?:less than|<|≤|<=)\s*(\d+)",
            "max_avoid",
        ),
        # "did not enroll / no data ... eGFR less than 25" → avoid initiation
        (
            rf"(?:did not enroll|no data|insufficient data|not studied)"
            rf".{{0,80}}?eGFR\s*(?:less than|<|≤|<=)\s*(\d+)",
            "max_avoid",
        ),
        # eGFR less than 45/30 ... not recommended (SGLT2i glycemic)
        (
            rf"eGFR\s*(?:less than|<|≤|<=)\s*(\d+){span}"
            rf"(not recommended|likely to be ineffective|avoid|do not)",
            "max_avoid",
        ),
        # Heart-failure trial floors: "heart failure (eGFR ≥ 20 ...)"
        (
            rf"heart failure\s*\(\s*eGFR\s*(?:greater than or equal to|≥|>=)\s*(\d+)",
            "min_none",
        ),
        # sacubitril: eGFR less than 30 ... start ... 24/26 mg
        (
            rf"eGFR\s*(?:less than|<|≤|<=)\s*(\d+){span}"
            rf"(?:start|initiat\w*){span}(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*mg",
            "max_dose",
        ),
        # apixaban style CrCl <15
        (
            rf"CrCl\s*(?:less than|<|≤|<=)\s*(\d+){span}"
            rf"(not recommended|avoid|do not|insufficient)",
            "max_avoid",
        ),
        # ivabradine: CrCl 15 to 60 ... no adjustment / no data below 15
        (
            rf"(?:creatinine clearance|CrCl)\s*(?:from\s+)?(\d+)\s*to\s*(\d+)\s*mL/min{span}"
            rf"(?:no(?:\s+dose)?\s+adjustment|minimal effect|not required)",
            "range_none",
        ),
        (
            rf"(?:creatinine clearance|CrCl)\s*(?:below|less than|<)\s*(\d+)\s*mL/min{span}"
            rf"(?:no data|not recommended|avoid|insufficient)",
            "max_avoid",
        ),
        # Eplerenone-style contraindication: Creatinine clearance ≤30 mL/min
        (
            rf"(?:creatinine clearance|CrCl)\s*(?:≤|<=|less than or equal to|<)\s*(\d+)\s*mL/min",
            "max_avoid_crcl_threshold",
        ),
    ]

    for pattern, kind in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            note = _normalize_ws(match.group(0))[:200]
            g = match.groups()
            try:
                if kind == "range_dose":
                    rules.append({
                        "egfr_min": float(g[0]),
                        "egfr_max": float(g[1]),
                        "dose": float(g[2]),
                        "frequency": "every other day" if g[3] and "every other" in g[3].lower() else None,
                        "adjustment": "reduce",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "min_dose":
                    freq = None
                    if len(g) > 2 and g[2]:
                        gl = g[2].lower()
                        if "every other" in gl:
                            freq = "every other day"
                        elif "twice" in gl:
                            freq = "twice daily"
                        elif "once" in gl:
                            freq = "once daily"
                    rules.append({
                        "egfr_min": float(g[0]),
                        "egfr_max": None,
                        "dose": float(g[1]),
                        "frequency": freq,
                        "adjustment": "none",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "max_action":
                    action_blob = g[1].lower()
                    if any(t in action_blob for t in ("contraindic", "not recommended", "do not", "avoid")):
                        rules.append({
                            "egfr_min": None,
                            "egfr_max": float(g[0]),
                            "dose": None,
                            "adjustment": "avoid",
                            "note": note,
                            "source": "fda_xml",
                        })
                    else:
                        dose_m = re.search(r"(\d+(?:\.\d+)?)\s*mg", g[1], re.I)
                        if dose_m:
                            rules.append({
                                "egfr_min": None,
                                "egfr_max": float(g[0]),
                                "dose": float(dose_m.group(1)),
                                "adjustment": "reduce",
                                "note": note,
                                "source": "fda_xml",
                            })
                elif kind == "max_dose":
                    rules.append({
                        "egfr_min": None,
                        "egfr_max": float(g[0]),
                        "dose": float(g[1]),
                        "adjustment": "reduce",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "max_avoid":
                    # Skip drug-interaction / non-dose contexts
                    note_l = note.lower()
                    if any(
                        t in note_l
                        for t in (
                            "aliskiren", "concomitant", "with nsaid", "potassium-sparing",
                            "drug interaction", "coadministrat",
                        )
                    ):
                        continue
                    rules.append({
                        "egfr_min": None,
                        "egfr_max": float(g[0]),
                        "dose": None,
                        "adjustment": "avoid",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "max_avoid_crcl_threshold":
                    # Only keep when nearby text indicates contraindication / do-not-use
                    start, end = match.span()
                    window = text[max(0, start - 160): min(len(text), end + 80)].lower()
                    if not any(
                        t in window
                        for t in ("contraindic", "do not use", "do not initiate", "should not be")
                    ):
                        continue
                    if any(t in window for t in ("aliskiren", "concomitant use with strong")):
                        # Keep eplerenone CrCl CI; skip pure CYP lists without CrCl focus
                        pass
                    rules.append({
                        "egfr_min": None,
                        "egfr_max": float(g[0]),
                        "dose": None,
                        "adjustment": "avoid",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "range_dose_ge_lt":
                    dose = float(g[2])
                    # Guard against capturing unrelated numbers (e.g. 200 from lab tables)
                    if dose <= 0 or dose > 80:
                        continue
                    rules.append({
                        "egfr_min": float(g[0]),
                        "egfr_max": float(g[1]) - 0.01,
                        "dose": dose,
                        "adjustment": "reduce",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "half_start_max":
                    rules.append({
                        "egfr_min": None,
                        "egfr_max": float(g[0]),
                        "dose": None,
                        "adjustment": "reduce_starting",
                        "note": note,
                        "source": "fda_xml",
                        "starting_dose_fraction": 0.5,
                    })
                elif kind == "range_none":
                    rules.append({
                        "egfr_min": float(g[0]),
                        "egfr_max": float(g[1]),
                        "dose": None,
                        "adjustment": "none",
                        "note": note,
                        "source": "fda_xml",
                    })
                elif kind == "min_none":
                    rules.append({
                        "egfr_min": float(g[0]),
                        "egfr_max": None,
                        "dose": None,
                        "adjustment": "none",
                        "note": note,
                        "source": "fda_xml",
                    })
            except (TypeError, ValueError, IndexError):
                continue

    return _refine_egfr_rules(rules)


def _extract_egfr_from_crcl_tables(tables: list[dict]) -> list[dict[str, Any]]:
    """Parse digoxin-style CrCl × weight dosing tables (use ~70 kg column when present)."""
    rules: list[dict[str, Any]] = []
    for table in tables:
        rows = table.get("rows") or []
        if len(rows) < 3:
            continue
        # Find header row with kg weights
        weight_idx = None
        header_row_i = None
        for i, row in enumerate(rows[:4]):
            joined = " ".join(row).lower()
            if "kg" in joined and any(w in row for w in ("70", "60", "80")):
                header_row_i = i
                if "70" in row:
                    weight_idx = row.index("70")
                elif "60" in row:
                    weight_idx = row.index("60")
                break
        if weight_idx is None:
            continue
        for row in rows[header_row_i + 1:]:
            if not row:
                continue
            m = re.match(r"(\d+)\s*mL/min", row[0], re.I)
            if not m:
                continue
            crcl = float(m.group(1))
            if weight_idx >= len(row):
                continue
            dose_cell = row[weight_idx].replace("*", "").strip()
            try:
                dose = float(dose_cell)
            except ValueError:
                continue
            rules.append({
                "egfr_min": crcl,
                "egfr_max": crcl,
                "dose": dose,
                "adjustment": "reduce",
                "note": f"CrCl {crcl} mL/min (~70kg): {dose} mcg",
                "dose_unit": "mcg",
                "source": "fda_xml_table",
            })
    return rules


def _extract_multi_factor_dose_rules_from_text(text: str) -> list[dict[str, Any]]:
    """Extract multi-factor dose reductions (e.g. apixaban NVAF ABC criteria).

    Label pattern: reduce to 2.5 mg BID when ≥2 of {age≥80, weight≤60 kg, Scr≥1.5}.
    Thresholds and dose are parsed from the SPL text (not hardcoded clinically).
    """
    rules: list[dict[str, Any]] = []
    if not text:
        return rules

    # Window around "at least 2/two of the following characteristics"
    anchor = re.compile(
        r"at least\s+(?:two|2)\s+of\s+the\s+following\s+characteristics",
        re.IGNORECASE,
    )
    for m in anchor.finditer(text):
        window = text[m.start(): min(len(text), m.start() + 500)]
        wlow = window.lower()
        # Prefer NVAF / AF adult context; skip pure DVT prophylaxis blocks without age criterion
        age_m = re.search(
            r"age\s+(?:greater than or equal to|≥|>=)\s*(\d+)\s*years?",
            window,
            re.I,
        )
        wt_m = re.search(
            r"(?:body\s+)?weight\s+(?:less than or equal to|≤|<=)\s*(\d+)\s*kg",
            window,
            re.I,
        )
        scr_m = re.search(
            r"serum\s+creatinine\s+(?:greater than or equal to|≥|>=)\s*(\d+(?:\.\d+)?)\s*mg(?:\s*/\s*|\s*)dL",
            window,
            re.I,
        )
        dose_m = re.search(
            r"(?:recommended\s+dose(?:\s+of\s+\w+)?\s+is|the\s+recommended\s+dose\s+is)\s*"
            r"(\d+(?:\.\d+)?)\s*mg",
            window,
            re.I,
        )
        # Dose may appear before the criteria list in some sentences
        if not dose_m:
            pre = text[max(0, m.start() - 120): m.start()]
            dose_m = re.search(
                r"(?:recommended\s+dose(?:\s+of\s+\w+)?\s+is|dose\s+is)\s*"
                r"(\d+(?:\.\d+)?)\s*mg",
                pre,
                re.I,
            )
        if not (age_m and wt_m and scr_m and dose_m):
            continue
        dose = float(dose_m.group(1))
        if dose <= 0 or dose > 10:
            continue
        freq = "twice daily" if "twice daily" in wlow or "twice daily" in text[max(0, m.start()-80): m.start()].lower() else None
        if freq is None and re.search(r"twice\s+daily", text[max(0, m.start()-100): m.end()+80], re.I):
            freq = "twice daily"
        rules.append({
            "rule_type": "min_criteria_count",
            "min_matched": 2,
            "criteria": [
                {
                    "field": "age",
                    "op": ">=",
                    "value": float(age_m.group(1)),
                    "unit": "years",
                },
                {
                    "field": "weight_kg",
                    "op": "<=",
                    "value": float(wt_m.group(1)),
                    "unit": "kg",
                },
                {
                    "field": "creatinine",
                    "op": ">=",
                    "value": float(scr_m.group(1)),
                    "unit": "mg/dL",
                },
            ],
            "dose": dose,
            "dose_unit": "mg",
            "frequency": freq or "twice daily",
            "adjustment": "reduce",
            "note": _normalize_ws(window)[:240],
            "source": "fda_xml",
            "indication_hint": "atrial_fibrillation" if any(
                t in text[max(0, m.start()-200): m.start()+50].lower()
                for t in ("atrial fibrillation", "nvaf", "nonvalvular")
            ) else None,
        })

    # Deduplicate identical criterion sets
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for rule in rules:
        key = (
            rule.get("min_matched"),
            rule.get("dose"),
            tuple(
                (c.get("field"), c.get("op"), c.get("value"))
                for c in rule.get("criteria") or []
            ),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rule)
    return out


def _extract_apixaban_crcl_notes(text: str) -> list[dict[str, Any]]:
    """Capture CrCl <15 / ESRD language for anticoagulants (caution, not hard avoid)."""
    rules: list[dict[str, Any]] = []
    if not text:
        return rules
    # Only when apixaban-style "CrCl <15" appears with ESRD/dialysis dosing discussion
    for m in re.finditer(
        r"CrCl\s*(?:less than|<|≤|<=)\s*(\d+)\s*mL/min.{0,120}?"
        r"(?:ESRD|dialysis|end-stage renal|dosing recommendations)",
        text,
        re.IGNORECASE,
    ):
        rules.append({
            "egfr_min": None,
            "egfr_max": float(m.group(1)),
            "dose": None,
            "adjustment": "caution",
            "note": _normalize_ws(m.group(0))[:200],
            "source": "fda_xml",
        })
    return rules


def _refine_egfr_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop conflicting / indication-mismatched eGFR rules.

    Example: SGLT2i labels say glycemic dosing is not recommended below eGFR 45,
    while HF dosing allows eGFR ≥25 — keep the HF threshold when both appear.
    """
    if not rules:
        return rules

    hf_floor = None
    for rule in rules:
        if rule.get("adjustment") != "none":
            continue
        note = (rule.get("note") or "").lower()
        emin = rule.get("egfr_min")
        if emin is None:
            continue
        if (
            "same as the recommended" in note
            or "no dose adjustment" in note
            or "heart failure" in note
        ):
            hf_floor = emin if hf_floor is None else min(hf_floor, float(emin))

    refined: list[dict[str, Any]] = []
    for rule in rules:
        note = (rule.get("note") or "").lower()
        if rule.get("adjustment") == "avoid":
            if any(
                t in note
                for t in ("aliskiren", "concomitant", "coadministrat", "with nsaid")
            ):
                continue
            emax = rule.get("egfr_max")
            if (
                hf_floor is not None
                and emax is not None
                and float(emax) > float(hf_floor)
            ):
                # Glycemic / non-HF cutoff above HF-allowed floor
                continue
        if rule.get("adjustment") == "reduce" and rule.get("dose") and float(rule["dose"]) > 80:
            unit = (rule.get("dose_unit") or "mg").lower()
            if unit in ("mg",) and "mcg" not in note:
                continue
        refined.append(rule)
    return refined


def _dedupe_egfr_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate eGFR rules by (min, max, dose, adjustment)."""
    rules = _refine_egfr_rules(rules)
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for rule in rules:
        key = (
            rule.get("egfr_min"),
            rule.get("egfr_max"),
            rule.get("dose"),
            rule.get("adjustment"),
            rule.get("frequency"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rule)
    return out


def _extract_contraindications(sel: Selector) -> list[str]:
    """Extract contraindications section text."""
    findings: list[str] = []
    for section in _iter_sections(sel):
        title = _section_title(section)
        if "CONTRAINDICATION" not in title.upper():
            continue
        content = _direct_text_block(section)
        if content:
            findings.append(content)
    return findings


def _extract_warnings(sel: Selector) -> list[dict[str, Any]]:
    """Extract warnings/precautions including nested warning subsections."""
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for section in _iter_sections(sel):
        title = _section_title(section)
        if not title:
            continue
        title_upper = title.upper()
        is_warn_root = "WARNING" in title_upper or "PRECAUTION" in title_upper
        is_safety_topic = any(
            t in title_upper
            for t in (
                "HYPERKALEMIA", "BRADYCARDIA", "HYPOTENSION",
                "CARDIAC FAILURE", "HEART FAILURE", "ELECTROLYTE",
            )
        )
        if not is_warn_root and not is_safety_topic:
            continue

        content = _direct_text_block(section)
        key = f"{title}|{content[:80]}"
        if key not in seen and (content or is_warn_root):
            seen.add(key)
            warnings.append({"title": title, "content": content})

        # Nested warning subsections (e.g. 5.2 Bradycardia)
        for child in section.xpath("./component/section"):
            child_title = _section_title(child)
            child_content = _direct_text_block(child)
            if not child_content and not child_title:
                continue
            ckey = f"{child_title}|{(child_content or '')[:80]}"
            if ckey in seen:
                continue
            seen.add(ckey)
            warnings.append({
                "title": child_title or title,
                "content": child_content,
            })

    return warnings


def _warnings_blob(warnings: list[dict[str, Any]]) -> str:
    return _normalize_ws(
        " ".join(
            f"{w.get('title', '')} {w.get('content', '')}"
            for w in warnings
            if w.get("content") or w.get("title")
        )
    )


def _collect_label_text(sel: Selector) -> str:
    """Collect normalized text from all SPL <text> nodes."""
    parts = [_node_text(node) for node in sel.xpath("//text")]
    return _normalize_ws(" ".join(p for p in parts if p))


_CMP = (
    r"(?:greater than or equal to|greater than|more than|at least|above|"
    r"less than or equal to|less than|below|under|>=|<=|≥|≤|>|<)"
)

_CMP_NORMALIZE = {
    "≥": ">=",
    "≤": "<=",
    "greater than or equal to": ">=",
    "at least": ">=",
    "greater than": ">",
    "more than": ">",
    "above": ">",
    "less than or equal to": "<=",
    "less than": "<",
    "below": "<",
    "under": "<",
    "drops below": "<",
}


def _normalize_cmp(raw: str) -> str:
    key = raw.strip().lower()
    if key in (">=", "<=", ">", "<"):
        return key
    return _CMP_NORMALIZE.get(key, key)


def _context_action(window: str, *, kind: str) -> str | None:
    """Infer clinical action from nearby label language."""
    w = window.lower()

    if kind == "potassium":
        if any(t in w for t in (
            "contraindicated", "do not initiate", "do not start",
            "should not be initiated", "should not be started", "avoid",
        )):
            return "avoid"
        if any(t in w for t in (
            "withhold", "interrupt", "discontinue", "hold",
            "reduce the dose", "reduce dose", "decrease the dose", "dose reduction",
            "adjust",
        )):
            return "reduce_or_hold"
        if any(t in w for t in ("monitor", "caution", "closely", "hyperkalemia")):
            return "caution"
        return "caution"

    if kind == "hr":
        if any(t in w for t in ("contraindicated", "do not", "avoid")):
            return "avoid"
        if any(t in w for t in ("withhold", "hold", "discontinue", "interrupt", "bradycardia")):
            return "hold"
        if any(t in w for t in ("reduce", "decrease", "titrate", "adjust")):
            return "caution"
        return "caution"

    if kind == "bp":
        if any(t in w for t in ("contraindicated", "do not", "avoid")):
            return "avoid"
        if any(t in w for t in ("reduce", "decrease", "hold", "withhold")):
            return "reduce"
        if "hypotension" in w:
            return "caution"
        return "caution"

    return None


def _is_noise_window(window: str) -> bool:
    """Filter non-dosing contexts that look like vital thresholds."""
    w = window.lower()
    noise = (
        "ejection fraction", "lvef", "nyha", "children under",
        "pediatric", "years of age", "placebo", "adverse reaction",
        "incidence", "table ", "mean increase",
        "were excluded", "was excluded", "exclusion", "at screening",
        "randomized", "% of patients", "difference in the",
    )
    return any(n in w for n in noise)


def _extract_potassium_adjustments_from_text(text: str) -> list[dict[str, Any]]:
    """Extract serum potassium action thresholds from FDA label text."""
    pattern = re.compile(
        rf"(?:serum\s+)?potassium(?:\s+concentrations?)?[^\d.]{{0,50}}?"
        rf"(?P<cmp>{_CMP})\s*"
        rf"(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )
    # Also: "serum potassium > 5.5 mEq" with flexible spacing
    pattern_loose = re.compile(
        r"(?:serum\s+)?potassium\s*(?P<cmp>>|≥|greater than|more than)\s*"
        r"(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )
    # "Elevated serum potassium (greater than 5.7 mEq/L)"
    pattern_paren = re.compile(
        r"(?:elevated\s+)?(?:serum\s+)?potassium\s*\(\s*"
        rf"(?P<cmp>{_CMP})\s*(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )
    initiate_cut = re.compile(
        rf"(?:do not (?:initiate|start)|contraindicated|should not be (?:initiated|started))"
        rf"[^\d.]{{0,80}}?(?:serum\s+)?potassium[^\d.]{{0,40}}?"
        rf"(?P<cmp>{_CMP})\s*(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )
    dosing_eligible = re.compile(
        rf"(?:serum\s+)?potassium\s*(?P<cmp><=|≤|less than or equal to)\s*"
        rf"(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )
    # "If hyperkalemia develops ... potassium > 5.5 ... interrupt/reduce"
    hyper_k = re.compile(
        rf"hyperkalemia[^\d.]{{0,80}}?(?:serum\s+)?potassium[^\d.]{{0,40}}?"
        rf"(?P<cmp>{_CMP})\s*(?P<val>\d+(?:\.\d+)?)\s*(?:mEq|mmol)",
        re.IGNORECASE,
    )

    strength = {"avoid": 3, "reduce_or_hold": 2, "caution": 1}
    by_threshold: dict[float, dict[str, Any]] = {}

    def _upsert(thr: float, action: str, note: str) -> None:
        if thr < 4.5 or thr > 7.0:
            return
        prev = by_threshold.get(thr)
        rule = {
            "k_min": thr,
            "k_max": None,
            "adjustment": action,
            "note": note,
            "source": "fda_xml",
        }
        if prev is None or strength.get(action, 0) > strength.get(prev["adjustment"], 0):
            by_threshold[thr] = rule

    for match in initiate_cut.finditer(text):
        cmp_op = _normalize_cmp(match.group("cmp"))
        if cmp_op in (">", ">="):
            _upsert(float(match.group("val")), "avoid", _normalize_ws(match.group(0)))

    for match in dosing_eligible.finditer(text):
        start, end = match.span()
        window = text[max(0, start - 80): min(len(text), end + 120)].lower()
        if _is_noise_window(window):
            continue
        if any(t in window for t in ("initiate", "start treatment", "starting dose", "recommended")):
            # Eligibility ceiling (K ≤ 5.0 to start) → avoid above that threshold
            _upsert(float(match.group("val")), "avoid", _normalize_ws(match.group(0)))

    for match in hyper_k.finditer(text):
        start, end = match.span()
        window = text[max(0, start - 40): min(len(text), end + 120)]
        if _is_noise_window(window):
            continue
        cmp_op = _normalize_cmp(match.group("cmp"))
        if cmp_op not in (">", ">="):
            continue
        action = _context_action(window, kind="potassium") or "reduce_or_hold"
        _upsert(float(match.group("val")), action, _normalize_ws(match.group(0)))

    for pattern_i in (pattern, pattern_loose, pattern_paren):
        for match in pattern_i.finditer(text):
            start, end = match.span()
            window = text[max(0, start - 140): min(len(text), end + 140)]
            wlow = window.lower()
            if any(t in wlow for t in ("increase", "uptitrat", "raise the dose")) and _normalize_cmp(match.group("cmp")) in ("<", "<="):
                continue
            if _is_noise_window(window):
                continue
            cmp_op = _normalize_cmp(match.group("cmp"))
            if cmp_op not in (">", ">="):
                continue
            action = _context_action(window, kind="potassium")
            if action is None:
                continue
            _upsert(float(match.group("val")), action, _normalize_ws(match.group(0)))

    ordered = sorted(by_threshold.items(), key=lambda x: x[0])
    result: list[dict[str, Any]] = []
    for i, (thr, rule) in enumerate(ordered):
        next_thr = ordered[i + 1][0] if i + 1 < len(ordered) else None
        result.append({
            "k_min": thr,
            "k_max": next_thr if next_thr is not None else None,
            "adjustment": rule["adjustment"],
            "note": rule["note"],
            "source": "fda_xml",
        })
    return result


def _extract_hr_adjustments_from_text(text: str) -> list[dict[str, Any]]:
    """Extract heart-rate action thresholds from FDA label text."""
    patterns = [
        re.compile(
            rf"heart\s*rate(?:\s*\([^)]{{0,40}}\)|\s+of)?\s*"
            rf"(?P<cmp>{_CMP})\s*"
            rf"(?P<val>\d+)\s*(?:beats\s*per\s*minute|bpm|beats)?",
            re.IGNORECASE,
        ),
        # Carvedilol-style: "pulse rate drops below 55 beats per minute"
        re.compile(
            rf"(?:pulse|heart)\s*rate\s*(?:drops?\s*)?(?P<cmp>{_CMP}|below|under)\s*"
            rf"(?P<val>\d+)\s*(?:beats\s*per\s*minute|bpm|beats)?",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<cmp>{_CMP})\s*(?P<val>\d+)\s*(?:beats\s*per\s*minute|bpm)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"bradycardia\s*(?:\([^)]{{0,80}}?(?:heart|pulse)\s*rate\s*)?"
            rf"(?P<cmp>{_CMP})\s*(?P<val>\d+)",
            re.IGNORECASE,
        ),
        # "If pulse rate drops below 55, the dosage should be reduced"
        re.compile(
            rf"(?:if|when)\s+(?:the\s+)?(?:pulse|heart)\s*rate\s*"
            rf"(?:drops?\s*)?(?P<cmp>{_CMP}|below|under)\s*(?P<val>\d+)",
            re.IGNORECASE,
        ),
    ]

    candidates: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            window = text[max(0, start - 100): min(len(text), end + 100)]
            wlow = window.lower()
            if _is_noise_window(window):
                continue
            if not any(
                t in wlow
                for t in ("heart", "bradycardia", "pulse", "beats per minute", "bpm")
            ):
                continue

            value = int(match.group("val"))
            if value < 40 or value > 100:
                continue

            cmp_raw = match.group("cmp")
            cmp_op = _normalize_cmp(cmp_raw)
            action = _context_action(window, kind="hr")
            # Dose-reduction language around pulse/HR thresholds
            if action in (None, "caution") and any(
                t in wlow for t in ("dosage should be reduced", "reduce the dose", "dose should be reduced")
            ):
                action = "hold"
            if action is None:
                continue

            if cmp_op in ("<", "<="):
                key = (None, value, action)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "hr_min": None,
                    "hr_max": value,
                    "action": action,
                    "note": _normalize_ws(match.group(0)),
                    "source": "fda_xml",
                })

    strength = {"avoid": 3, "hold": 3, "caution": 1, "continue": 0}
    by_max: dict[int, dict[str, Any]] = {}
    for rule in candidates:
        thr = int(rule["hr_max"])
        prev = by_max.get(thr)
        if prev is None or strength.get(rule["action"], 0) > strength.get(prev["action"], 0):
            by_max[thr] = rule

    return [by_max[k] for k in sorted(by_max.keys())]


def _extract_bp_adjustments_from_text(text: str) -> list[dict[str, Any]]:
    """Extract systolic blood pressure thresholds from FDA label text."""
    patterns = [
        re.compile(
            rf"systolic\s*(?:blood\s*pressure)?(?:\s*\([^)]{{0,40}}\)|\s+of)?\s*"
            rf"(?P<cmp>{_CMP})\s*"
            rf"(?P<val>\d+)\s*(?:mm\s*Hg|mmHg)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"blood\s*pressure\s*\(\s*systolic\s*blood\s*pressure\s*"
            rf"(?P<cmp>{_CMP})\s*(?P<val>\d+)\s*(?:mm\s*Hg|mmHg)",
            re.IGNORECASE,
        ),
        re.compile(
            rf"SBP\s*(?P<cmp>{_CMP})\s*(?P<val>\d+)\s*(?:mm\s*Hg|mmHg)?",
            re.IGNORECASE,
        ),
        # Dose-adjustment language without requiring mmHg immediately
        re.compile(
            rf"(?:if|when|for patients with)\s+systolic\s*(?:blood\s*pressure)?\s*"
            rf"(?P<cmp>{_CMP})\s*(?P<val>\d+)",
            re.IGNORECASE,
        ),
    ]

    candidates: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            window = text[max(0, start - 100): min(len(text), end + 120)]
            wlow = window.lower()
            # Allow dosing-context hits even near trial language if dose verbs present
            dosing_ctx = any(
                t in wlow
                for t in ("dose", "dosage", "start", "initiat", "reduce", "titrat", "adjust")
            )
            if _is_noise_window(window) and not dosing_ctx:
                continue

            value = int(match.group("val"))
            if value < 70 or value > 130:
                continue

            cmp_op = _normalize_cmp(match.group("cmp"))
            action = _context_action(window, kind="bp")
            if action is None:
                continue

            if cmp_op in ("<", "<="):
                key = (None, value, action)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "sbp_min": None,
                    "sbp_max": value,
                    "action": action,
                    "note": _normalize_ws(match.group(0)),
                    "source": "fda_xml",
                })

    strength = {"avoid": 3, "reduce": 2, "caution": 1, "continue": 0}
    by_max: dict[int, dict[str, Any]] = {}
    for rule in candidates:
        thr = int(rule["sbp_max"])
        prev = by_max.get(thr)
        if prev is None or strength.get(rule["action"], 0) > strength.get(prev["action"], 0):
            by_max[thr] = rule

    return [by_max[k] for k in sorted(by_max.keys())]


def _extract_monitoring_from_text(text: str) -> list[str]:
    """Extract short monitoring recommendations mentioned in the label."""
    findings: list[str] = []
    seen: set[str] = set()
    patterns = [
        r"Monitor\s+(?:serum\s+)?potassium[^.|]{0,80}",
        r"Monitor\s+(?:blood\s+pressure|BP)[^.|]{0,80}",
        r"Monitor\s+(?:heart\s+rate|HR)[^.|]{0,80}",
        r"Monitor\s+(?:renal\s+function|serum\s+creatinine|eGFR)[^.|]{0,80}",
        r"Assess\s+(?:renal\s+function|electrolytes)[^.|]{0,80}",
    ]
    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            item = _normalize_ws(match.group(0)).strip(" .;")
            key = item.lower()
            if key not in seen and 10 < len(item) < 160:
                seen.add(key)
                findings.append(item)
            if len(findings) >= 6:
                return findings
    return findings


def _extract_safety_adjustments(text: str) -> dict[str, Any]:
    """Derive K+/HR/BP adjustments and monitoring from FDA label text."""
    if not text:
        return {
            "potassium_adjustments": [],
            "heart_rate_adjustments": [],
            "bp_adjustments": [],
            "monitoring": [],
        }
    return {
        "potassium_adjustments": _extract_potassium_adjustments_from_text(text),
        "heart_rate_adjustments": _extract_hr_adjustments_from_text(text),
        "bp_adjustments": _extract_bp_adjustments_from_text(text),
        "monitoring": _extract_monitoring_from_text(text),
    }


def _merge_safety_adjustments(
    preferred: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Merge safety rules, keeping preferred (warnings) first then filling gaps."""

    def _merge_list(primary: list[dict], secondary: list[dict], key_fn) -> list[dict]:
        seen: set[tuple] = set()
        out: list[dict] = []
        for item in list(primary or []) + list(secondary or []):
            key = key_fn(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    return {
        "potassium_adjustments": _merge_list(
            preferred.get("potassium_adjustments", []),
            fallback.get("potassium_adjustments", []),
            lambda r: (r.get("k_min"), r.get("k_max"), r.get("adjustment")),
        ),
        "heart_rate_adjustments": _merge_list(
            preferred.get("heart_rate_adjustments", []),
            fallback.get("heart_rate_adjustments", []),
            lambda r: (r.get("hr_min"), r.get("hr_max"), r.get("action")),
        ),
        "bp_adjustments": _merge_list(
            preferred.get("bp_adjustments", []),
            fallback.get("bp_adjustments", []),
            lambda r: (r.get("sbp_min"), r.get("sbp_max"), r.get("action")),
        ),
        "monitoring": _merge_list(
            preferred.get("monitoring", []),
            fallback.get("monitoring", []),
            lambda r: (r.lower() if isinstance(r, str) else str(r)),
        ),
    }


def extract_all_drugs(drug_labels_dir: Path) -> list[dict[str, Any]]:
    """Extract dosing information from all drug label XML files in a directory."""
    drugs: list[dict[str, Any]] = []
    xml_files = list(Path(drug_labels_dir).rglob("*_label.xml"))
    print(f"Found {len(xml_files)} XML label files")

    for xml_file in xml_files:
        try:
            print(f"Processing: {xml_file.name}")
            drugs.append(parse_drug_label(xml_file))
        except Exception as e:
            print(f"Error processing {xml_file.name}: {e}")

    return drugs


if __name__ == "__main__":
    test_file = Path("data/heart_failure/raw/drug_labels/enalapril_maleate/enalapril_maleate_label.xml")
    if not test_file.exists():
        print(f"Test file not found: {test_file}")
    else:
        result = parse_drug_label(test_file)
        print("=== Enalapril Extraction Result (Parsel) ===")
        print(f"Drug Name: {result['drug_name']}")
        print(f"Dosage sections: {len(result['dosage_information'])}")
        print(f"Renal sections: {len(result['renal_adjustments'])}")
        print(f"K+ rules: {result['potassium_adjustments']}")
        print(f"Monitoring: {result['monitoring'][:3]}")
