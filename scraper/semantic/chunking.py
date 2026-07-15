"""Structure-aware and semantic breakpoint chunking."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Callable

from scraper.semantic import config
from scraper.semantic.embeddings import cosine_similarity, embed_texts
from scraper.transform.text_normalization import repair_pdf_flow_text


logger = logging.getLogger(__name__)

# Clinical-safe sentence splitter: avoids splitting on decimal numbers or units
# - (?<=[.!?])\s+ : split after sentence-ending punctuation
# - (?![a-zA-Z]{1,4}/) : negative lookahead prevents split if followed by unit like mL/, mg/
# - (?<!\d\.) : negative lookbehind prevents split after decimal point (e.g., "5.5 mmol")
# - (?=[A-Z0-9(]) : split before capital letter, number, or opening parenthesis
_SENTENCE_SPLITTER = re.compile(
    r"(?<=[.!?])\s+(?![a-zA-Z]{1,4}/)(?<!\d\.)\s*(?=[A-Z0-9(])"
)
_NUMBERED_LIST_LINE = re.compile(r"^\s*\d+\.\s")
_BULLET_LIST_LINE = re.compile(r"^\s*(?:[-•*]|\u2022)\s")
_INLINE_NUMBERED_ITEM = re.compile(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Za-z(])")
_INLINE_BULLET_ITEM = re.compile(r"(?:^|\s)([-•*]|\u2022)\s+(?=[A-Za-z(])")
_DOSING_LINE = re.compile(
    r"\b(?:mg|mcg|g|units?|daily|twice|titrate|titration|dose|dosage|administer|starting dose|target dose)\b",
    re.IGNORECASE,
)


def _is_clinical_list_or_dosing_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(
        _NUMBERED_LIST_LINE.match(stripped)
        or _BULLET_LIST_LINE.match(stripped)
        or _DOSING_LINE.search(stripped)
    )


def _block_looks_like_clinical_list(block: str) -> bool:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) >= 2:
        clinical_lines = sum(1 for line in lines if _is_clinical_list_or_dosing_line(line))
        if clinical_lines >= 2:
            return True
    numbered_items = re.findall(r"(?:^|\n|\s)\d+\.\s+\S", block)
    bullet_items = re.findall(r"(?:^|\n)\s*(?:[-•*]|\u2022)\s+\S", block)
    return len(numbered_items) >= 2 or len(bullet_items) >= 2


def _adjacent_blocks_should_stay_together(left: str, right: str) -> bool:
    left_line = left.rsplit("\n", 1)[-1].strip()
    right_line = right.split("\n", 1)[0].strip()
    return _is_clinical_list_or_dosing_line(left_line) and _is_clinical_list_or_dosing_line(right_line)


def _split_inline_numbered_items(text: str) -> list[str]:
    """Split glued PDF text like '1. Start ... 2. Titrate ...' into list items."""
    matches = list(_INLINE_NUMBERED_ITEM.finditer(text))
    if len(matches) < 2:
        return []

    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.start(1) if match.start(1) > 0 else match.start()
        end = matches[index + 1].start(1) if index + 1 < len(matches) else len(text)
        item = text[start:end].strip()
        if item:
            items.append(item)
    return items


def _split_inline_bullet_items(text: str) -> list[str]:
    matches = list(_INLINE_BULLET_ITEM.finditer(text))
    if len(matches) < 2:
        return []

    items: list[str] = []
    for index, match in enumerate(matches):
        start = match.start(1)
        end = matches[index + 1].start(1) if index + 1 < len(matches) else len(text)
        item = text[start:end].strip()
        if item:
            items.append(item)
    return items


def _clinical_list_items(block: str) -> list[str]:
    """Return atomic list items; never split inside one numbered/bullet entry."""
    block = block.strip()
    if not block:
        return []

    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) >= 2 and sum(1 for line in lines if _is_clinical_list_or_dosing_line(line)) >= 2:
        return lines

    inline_numbered = _split_inline_numbered_items(block)
    if len(inline_numbered) >= 2:
        return inline_numbered

    inline_bullets = _split_inline_bullet_items(block)
    if len(inline_bullets) >= 2:
        return inline_bullets

    return [block]


def _safe_sentence_split(text: str) -> list[str]:
    """Split text into sentences, preserving clinical units and decimals.

    Handles patterns like:
    - "eGFR < 30 mL/min/1.73m2" stays intact
    - "serum potassium greater than 5.5 mmol/L" stays intact
    - "Administer 100 mg daily. Monitor BP." splits correctly
    """
    # First protect common clinical patterns by temporarily replacing
    protected: list[tuple[str, str]] = []
    patterns = [
        (r"\d+(?:\.\d+)?\s*(?:mL/min/1\.73\s*m\s*2|mL/min|mEq/L|mmol/L|mg/dL|mmHg|bpm)", "<PROTECTED_UNIT>"),
        (r"\d+(?:\.\d+)?\s*(?:kg|m|mL|mg|mmol|mEq|%)", "<PROTECTED_UNIT>"),
    ]

    for pattern, replacement in patterns:
        for match in re.finditer(pattern, text):
            placeholder = f"__PROT_{len(protected)}__"
            protected.append((placeholder, match.group(0)))
            text = text[:match.start()] + placeholder + text[match.end():]

    # Split sentences
    sentences = _SENTENCE_SPLITTER.split(text)

    # Restore protected patterns
    result: list[str] = []
    for sentence in sentences:
        for placeholder, original in protected:
            sentence = sentence.replace(placeholder, original)
        cleaned = sentence.strip()
        if cleaned:
            result.append(cleaned)

    return result


def paragraph_blocks(text: str) -> list[str]:
    repaired = repair_pdf_flow_text(text or "")
    if not repaired.strip():
        return []

    blocks: list[str] = []
    for raw_block in re.split(r"\n\s*\n+", repaired):
        block = raw_block.strip()
        if not block:
            continue
        if block.startswith("# "):
            blocks.append(block)
            continue
        if _block_looks_like_clinical_list(block):
            items = _clinical_list_items(block)
            if len(items) == 1:
                blocks.append(items[0])
            else:
                blocks.extend(items)
            continue
        sentences = _safe_sentence_split(block)
        if len(sentences) <= 1:
            blocks.append(block)
            continue
        for sentence in sentences:
            cleaned = sentence.strip()
            if cleaned:
                blocks.append(cleaned)
    return blocks


def _merge_blocks(blocks: list[str], token_estimate: Callable[[str], int], max_tokens: int) -> list[str]:
    merged: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if current and token_estimate(candidate) > max_tokens and not _adjacent_blocks_should_stay_together(current, block):
            merged.append(current)
            current = block
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def _truncate_for_embed(text: str) -> str:
    max_chars = max(512, config.EMBEDDING_MAX_INPUT_CHARS)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _semantic_breakpoints(
    blocks: list[str],
    *,
    token_estimate: Callable[[str], int] | None = None,
    use_semantic: bool = True,
) -> list[int]:
    if not use_semantic:
        return []
    if len(blocks) <= 1:
        return []
    if len(blocks) < config.SEMANTIC_CHUNK_MIN_BLOCKS:
        return []
    if len(blocks) > config.SEMANTIC_CHUNK_MAX_BLOCKS:
        logger.info(
            "Semantic chunk breakpoints skipped: %s blocks > max %s (structure-only)",
            len(blocks),
            config.SEMANTIC_CHUNK_MAX_BLOCKS,
        )
        return []
    if token_estimate is not None:
        total_tokens = sum(token_estimate(block) for block in blocks)
        if total_tokens < config.SEMANTIC_CHUNK_MIN_TOKENS:
            return []

    try:
        vectors = embed_texts([_truncate_for_embed(block) for block in blocks])
    except Exception as exc:
        logger.warning(
            "Semantic chunk breakpoints unavailable (%s: %s); "
            "using structure-only chunking for %s blocks",
            type(exc).__name__,
            exc,
            len(blocks),
        )
        return []

    if len(vectors) != len(blocks):
        logger.warning(
            "Semantic chunk breakpoints unavailable (vector count %s != blocks %s); "
            "using structure-only chunking",
            len(vectors),
            len(blocks),
        )
        return []

    breakpoints: list[int] = []
    for index in range(len(vectors) - 1):
        if _adjacent_blocks_should_stay_together(blocks[index], blocks[index + 1]):
            continue
        similarity = cosine_similarity(vectors[index], vectors[index + 1])
        if similarity < config.SEMANTIC_CHUNK_BREAKPOINT_THRESHOLD:
            breakpoints.append(index + 1)
    return breakpoints


def _group_by_breakpoints(blocks: list[str], breakpoints: list[int]) -> list[str]:
    if not breakpoints:
        return ["\n\n".join(blocks)]
    groups: list[str] = []
    start = 0
    for point in sorted(set(breakpoints)):
        group = "\n\n".join(blocks[start:point]).strip()
        if group:
            groups.append(group)
        start = point
    tail = "\n\n".join(blocks[start:]).strip()
    if tail:
        groups.append(tail)
    return groups


def structure_semantic_chunk_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    token_estimate: Callable[[str], int],
    use_semantic: bool = True,
) -> list[str]:
    blocks = paragraph_blocks(text)
    if not blocks:
        return []

    oversized: list[str] = []
    sized_blocks: list[str] = []
    for block in blocks:
        if token_estimate(block) > chunk_size:
            oversized.extend(_split_oversized_block(block, chunk_size, overlap, token_estimate, use_semantic=use_semantic))
        else:
            sized_blocks.append(block)

    breakpoints = (
        _semantic_breakpoints(sized_blocks, token_estimate=token_estimate, use_semantic=use_semantic)
        if len(sized_blocks) > 1
        else []
    )
    grouped = _group_by_breakpoints(sized_blocks, breakpoints)
    chunks = _merge_blocks(grouped, token_estimate, chunk_size)
    chunks.extend(oversized)

    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    return _apply_overlap(chunks, overlap, token_estimate)


def _split_oversized_block(
    block: str,
    chunk_size: int,
    overlap: int,
    token_estimate: Callable[[str], int],
    *,
    use_semantic: bool = True,
) -> list[str]:
    if _block_looks_like_clinical_list(block):
        items = _clinical_list_items(block)
        return _merge_blocks(items, token_estimate, chunk_size)

    sentences = _safe_sentence_split(block)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not sentences:
        return [block]

    breakpoints = (
        _semantic_breakpoints(sentences, token_estimate=token_estimate, use_semantic=use_semantic)
        if len(sentences) > 1
        else []
    )
    groups = _group_by_breakpoints(sentences, breakpoints)
    return _merge_blocks(groups, token_estimate, chunk_size)


def _apply_overlap(chunks: list[str], overlap: int, token_estimate: Callable[[str], int]) -> list[str]:
    if len(chunks) <= 1:
        return chunks

    overlapped: list[str] = [chunks[0]]
    for index in range(1, len(chunks)):
        previous = overlapped[-1]
        prefix = _tail_tokens(previous, overlap, token_estimate)
        combined = f"{prefix}\n\n{chunks[index]}".strip() if prefix else chunks[index]
        overlapped.append(combined)
    return overlapped


def _tail_tokens(text: str, overlap: int, token_estimate: Callable[[str], int]) -> str:
    words = text.split()
    if not words:
        return ""
    low = 0
    high = len(words)
    best = ""
    while low <= high:
        mid = (low + high) // 2
        candidate = " ".join(words[-mid:]) if mid else ""
        size = token_estimate(candidate)
        if size <= overlap:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best
