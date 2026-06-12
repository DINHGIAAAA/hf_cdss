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


def normalize_evidence_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    for broken, replacement in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, replacement)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

