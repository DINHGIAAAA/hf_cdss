import re
import unicodedata


MOJIBAKE_REPLACEMENTS = {
    "\u00e2\u20ac\u00a2": "-",
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u20ac\u00a6": "...",
    "\u00c2\u00b7": "-",
    "\u00c2": "",
    "\u00ef\u00bb\u00bf": "",
}

CALLOUT_MARKER_RE = re.compile(
    r"(?i)\b(Practice Point|Key Point|Clinical Pearl)\s+[\d.]+:"
)

# Common function-word pairs glued together when PDF layout drops spaces.
_GLUE_WORDS = (
    ("for", "people"),
    ("people", "with"),
    ("patient", "with"),
    ("patients", "with"),
    ("patients", "and"),
    ("and", "for"),
    ("as", "the"),
    ("so", "does"),
    ("dose", "adjustment"),
    ("renal", "function"),
    ("heart", "failure"),
    ("blood", "pressure"),
    ("drug", "interaction"),
    ("drug", "interactions"),
)

# Case-sensitive clinical fragments (leave capitalization intact).
_CLINICAL_GLUE = (
    ("with", "CKD"),
    ("or", "CKD"),
    ("and", "CKD"),
    ("in", "CKD"),
    ("with", "AKI"),
    ("or", "AKI"),
    ("HFrEF", "and"),
    ("HFpEF", "and"),
    ("HFmrEF", "and"),
    ("ARNI", "and"),
    ("SGLT2i", "and"),
    ("MRA", "and"),
    ("ACE", "inhibitor"),
    ("mmol/L", "is"),
    ("mg/dL", "is"),
    ("mmHg", "is"),
)

# Keep unit slash suffixes narrow so "mmol/Lis" is not treated as a unit path.
_UNIT_RE = re.compile(
    r"(?i)(\d)(mg|mcg|µg|g|mL|L|mmol|mmHg|bpm|kg|meq|mEq)"
    r"(/?(?:dL|mL|L|kg|min|h|hr|day|1\.73\s*m2?))?\b"
)
_ABBREV_NUMBER_RE = re.compile(
    r"\b(eGFR|GFR|SBP|DBP|HR|LVEF|EF|NYHA|BMI|HbA1c|INR|K\+|CrCl)(\d)"
)
# Long lowercase run then TitleCase word — do NOT use bare ([a-z])([A-Z]) (breaks HFrEF).
_CAMEL_BOUNDARY_RE = re.compile(r"([a-z]{3,})([A-Z][a-z])")
# lowercase/function word glued to clinical acronym (may continue into "and"/"or").
_LOWER_ACRONYM_RE = re.compile(
    r"([a-z]{2,})(CKD|AKI|CAD|PAD|COPD|NYHA|GDMT|SGLT2i?|ARNI|MRA|ACEI?|ARB|HFrEF|HFpEF|HFmrEF)"
    r"(?=(?:and|or|with|in)\b|[A-Z]|\b)"
)


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    for broken, replacement in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, replacement)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_inline_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", normalize_text(value)).strip()


def _apply_pair_glues(text: str, pairs: tuple[tuple[str, str], ...], *, ignore_case: bool) -> str:
    flags = re.IGNORECASE if ignore_case else 0
    # Multiple passes: "andforpeoplewith" → "and for" → "for people" → "people with".
    for _ in range(4):
        previous = text
        for left, right in pairs:
            glued = f"{re.escape(left)}{re.escape(right)}"
            # Full word: "peoplewith" / prefix of longer token: "andforpeoplewith".
            for pattern in (rf"\b{glued}\b", rf"\b{glued}(?=\w)"):
                text = re.sub(pattern, f"{left} {right}", text, flags=flags)
        if text == previous:
            break
    return text


def repair_pdf_flow_text(value: str | None) -> str:
    """Repair guideline PDF text: callout removal, de-hyphenation, glued words."""
    text = normalize_text(value)
    if not text:
        return ""

    # Sidebar callouts interrupt body text when PDF layout merges columns.
    text = re.sub(
        r"(?i)\s*(?:Practice Point|Key Point|Clinical Pearl)\s+[\d.]+:\s*[^.]*?\s+and\s+\w+-\s*",
        " ",
        text,
    )
    text = re.sub(
        r"(?i)\s*(?:Practice Point|Key Point|Clinical Pearl)\s+[\d.]+:\s*[^.\n]*\.?\s*",
        " ",
        text,
    )

    # De-hyphenate line breaks and spaced hyphen fragments from PDF wrapping.
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)-\s+(?=\w)", r"\1", text)

    # Soft line wraps become spaces.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Missing spaces after punctuation.
    text = re.sub(r",([A-Za-z])", r", \1", text)
    text = re.sub(r"\.([A-Za-z])", r". \1", text)

    # Conservative long-token "and" glues (ADA-style concatenations).
    text = re.sub(r"([a-z]{5,})and([a-z]{5,})", r"\1 and \2", text)
    text = re.sub(r"\bapeutic\b", "therapeutic", text, flags=re.IGNORECASE)

    # Function-word glues first, then split lower+acronym, then clinical fragments.
    text = _apply_pair_glues(text, _GLUE_WORDS, ignore_case=True)
    text = _LOWER_ACRONYM_RE.sub(r"\1 \2", text)
    text = _apply_pair_glues(text, _CLINICAL_GLUE, ignore_case=False)
    text = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", text)

    # Number ↔ unit / clinical abbreviation spacing.
    text = _UNIT_RE.sub(r"\1 \2\3", text)
    text = _ABBREV_NUMBER_RE.sub(r"\1 \2", text)
    text = re.sub(r"(\d)%", r"\1 %", text)
    # Re-run clinical glues after unit spacing (e.g. "mmol/Lis").
    text = _apply_pair_glues(text, _CLINICAL_GLUE, ignore_case=False)

    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def append_flow_line(buffer: str, line: str) -> str:
    """Join PDF flow lines with spaces and de-hyphenate word breaks."""
    line = normalize_text(line)
    if not line:
        return buffer
    if CALLOUT_MARKER_RE.search(line):
        return f"{buffer}\n\n{line}" if buffer else line
    if not buffer:
        return line
    if buffer.endswith("-"):
        return buffer[:-1] + line
    if buffer.endswith(("\n\n",)):
        return buffer + line
    return f"{buffer} {line}"
