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

# Common words glued together when PDF layout extraction drops spaces.
_GLUE_WORDS = ()  # reserved for future targeted repairs


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

    # Conservative repairs for common ADA/PDF glue patterns (long tokens only).
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

