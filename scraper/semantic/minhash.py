"""MinHash signatures for cheap near-duplicate detection before embedding dedupe.

Uses Locality-Sensitive Hashing (LSH) with banding technique for O(n) average
comparison time instead of O(n²).
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable


def _shingles(text: str, *, width: int = 3) -> Iterable[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(tokens) < width:
        yield " ".join(tokens)
        return
    for index in range(len(tokens) - width + 1):
        yield " ".join(tokens[index : index + width])


def minhash_signature(text: str, *, num_perm: int = 64) -> tuple[int, ...]:
    if not text.strip():
        return tuple()

    signature = [2**63 - 1] * num_perm
    for shingle in _shingles(text):
        digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for band in range(num_perm):
            band_hash = int.from_bytes(
                hashlib.blake2b(f"{band}:{value}".encode("utf-8"), digest_size=8).digest(),
                "big",
            )
            if band_hash < signature[band]:
                signature[band] = band_hash
    return tuple(signature)


def minhash_jaccard(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    matches = sum(1 for a, b in zip(left, right) if a == b)
    return matches / len(left)


# --- LSH Banding for O(n) average deduplication ---


def _compute_buckets(
    signature: tuple[int, ...],
    *,
    num_bands: int = 8,
) -> dict[int, int]:
    """Compute band hash buckets for LSH.

    Returns a dict mapping band_index -> band_hash.
    Documents with same (band_index, band_hash) are candidate duplicates.
    """
    num_perm = len(signature)
    if num_perm < num_bands:
        num_bands = max(1, num_perm)

    band_size = num_perm // num_bands
    buckets: dict[int, int] = {}
    for band_idx in range(num_bands):
        start = band_idx * band_size
        end = start + band_size
        band_slice = signature[start:end]
        # Convert int tuple to bytes for hashing (8 bytes per int)
        band_bytes = b"".join(val.to_bytes(8, "big") for val in band_slice)
        band_hash = hashlib.blake2b(band_bytes, digest_size=8).hexdigest()
        buckets[band_idx] = int(band_hash, 16)
    return buckets


def minhash_candidate_buckets(
    records: list[dict],
    *,
    text_field: str,
    num_perm: int = 64,
    num_bands: int = 8,
) -> dict[str, set[str]]:
    """Build LSH candidate buckets for O(1) lookup of potential duplicates.

    Returns dict mapping record_id -> set of candidate duplicate ids.
    Only records sharing at least one bucket are candidates.
    """
    buckets: dict[tuple[int, int], set[str]] = {}
    record_buckets: dict[str, dict[int, int]] = {}

    for record in records:
        record_id = record.get("chunk_id") or record.get("id") or str(id(record))
        text = record.get(text_field) or ""
        signature = minhash_signature(text, num_perm=num_perm)
        if not signature:
            continue

        record_buckets[record_id] = _compute_buckets(
            signature, num_bands=num_bands
        )

        for band_idx, band_hash in record_buckets[record_id].items():
            key = (band_idx, band_hash)
            if key not in buckets:
                buckets[key] = set()
            buckets[key].add(record_id)

    # Build candidates: for each record, find all records sharing at least one bucket
    candidates: dict[str, set[str]] = {r.get("chunk_id") or r.get("id") or str(id(r)): set() for r in records}
    for bucket_records in buckets.values():
        for rid in bucket_records:
            candidates[rid] = candidates.get(rid, set()) | (bucket_records - {rid})

    return candidates
