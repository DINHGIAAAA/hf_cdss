"""Stable, human-readable catalog IDs.

Label parts must be structured tokens (drug key, calc type, severity, …).
Never put free-text evidence / message prose into the visible label — that
produced IDs like::

    warfarin_sodium_fixed_dose_anticoagulant_warfarin_sodium_is_a_prescripti_e58950be

Prefer::

    warfarin_sodium_fixed_dose_e58950be
"""

from __future__ import annotations

import hashlib
import re


def slug(value: str | None, *, max_len: int | None = None) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "")).strip("_").lower()
    cleaned = re.sub(r"_+", "_", cleaned) or "unknown"
    if max_len is not None and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("_") or "unknown"
    return cleaned


def _compact_join(parts: list[str], *, max_len: int) -> str:
    labels = [slug(part) for part in parts if part and str(part).strip()]
    labels = [item for item in labels if item and item != "unknown"]
    if not labels:
        return "unknown"
    joined = "_".join(labels)
    if len(joined) <= max_len:
        return joined
    # Prefer keeping the first tokens (drug / type) and trim the tail.
    out: list[str] = []
    for token in labels:
        candidate = "_".join([*out, token]) if out else token
        if out and len(candidate) > max_len:
            break
        if not out and len(token) > max_len:
            return token[:max_len].rstrip("_")
        out.append(token)
    return "_".join(out)[:max_len].rstrip("_") or "unknown"


def stable_id(
    *label_parts: str | None,
    uniqueness: list[str | None] | None = None,
    prefix: str = "",
    max_label_len: int = 48,
) -> str:
    """Build `{prefix?}{readable_label}_{sha1[:8]}` from structured tokens."""
    label = _compact_join([str(p) for p in label_parts if p is not None], max_len=max_label_len)
    digest_bits = [label, *[str(item) for item in (uniqueness or []) if item not in (None, "")]]
    digest = hashlib.sha1("|".join(digest_bits).encode("utf-8")).hexdigest()[:8]
    prefix_clean = slug(prefix, max_len=12) if prefix else ""
    if prefix_clean and prefix_clean != "unknown":
        return f"{prefix_clean}_{label}_{digest}"
    return f"{label}_{digest}"
