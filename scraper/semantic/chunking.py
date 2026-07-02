"""Structure-aware and semantic breakpoint chunking."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable

from scraper.semantic import config
from scraper.semantic.embeddings import cosine_similarity, embed_texts
from scraper.transform.text_normalization import repair_pdf_flow_text


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
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", block)
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
        if current and token_estimate(candidate) > max_tokens:
            merged.append(current)
            current = block
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def _semantic_breakpoints(blocks: list[str]) -> list[int]:
    if len(blocks) <= 1:
        return []

    try:
        vectors = embed_texts(blocks)
    except Exception:
        return []

    breakpoints: list[int] = []
    for index in range(len(vectors) - 1):
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
) -> list[str]:
    blocks = paragraph_blocks(text)
    if not blocks:
        return []

    oversized: list[str] = []
    sized_blocks: list[str] = []
    for block in blocks:
        if token_estimate(block) > chunk_size:
            oversized.extend(_split_oversized_block(block, chunk_size, overlap, token_estimate))
        else:
            sized_blocks.append(block)

    breakpoints = _semantic_breakpoints(sized_blocks) if len(sized_blocks) > 1 else []
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
) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", block)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not sentences:
        return [block]

    breakpoints = _semantic_breakpoints(sentences) if len(sentences) > 1 else []
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
