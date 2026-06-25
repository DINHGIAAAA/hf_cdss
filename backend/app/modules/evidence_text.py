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


def _repair_pdf_flow_text(value: str) -> str:
    text = value
    if not text:
        return ""

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
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)-\s+(?=\w)", r"\1", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r",([A-Za-z])", r", \1", text)
    text = re.sub(r"\.([A-Za-z])", r". \1", text)
    text = re.sub(r"([a-z]{5,})and([a-z]{5,})", r"\1 and \2", text)
    text = re.sub(r"andfor([a-z])", r"and for \1", text, flags=re.IGNORECASE)
    text = re.sub(r"forpeople", r"for people", text, flags=re.IGNORECASE)
    text = re.sub(r"peoplewith", r"people with", text, flags=re.IGNORECASE)
    text = re.sub(r"withCKD", r"with CKD", text)
    text = re.sub(r"asthe", r"as the", text, flags=re.IGNORECASE)
    text = re.sub(r",so", r", so", text)
    text = re.sub(r"sodoes", r"so does", text, flags=re.IGNORECASE)
    text = re.sub(r"\bapeutic\b", "therapeutic", text, flags=re.IGNORECASE)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_evidence_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    for broken, replacement in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, replacement)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _repair_pdf_flow_text(text.strip())
    return text.strip()
