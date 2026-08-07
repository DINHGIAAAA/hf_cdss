"""Normalize GDMT policy_body guidance and status fields after LLM extraction."""

from __future__ import annotations

from typing import Any

ALLOWED_GDMT_STATUSES = frozenset(
    {"consider", "recommend", "review", "avoid", "consider_with_caution"},
)


def ensure_str_list(value: Any) -> list[str]:
    """Coerce prose or list into a list of non-empty strings (never split str by char)."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    text = str(value).strip()
    return [text] if text else []


def normalize_gdmt_status(value: Any, *, default: str = "consider") -> str:
    """Pick one status; reject LLM schema strings like 'review|consider|avoid'."""
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if "|" in text:
        for part in text.split("|"):
            token = part.strip()
            if token in ALLOWED_GDMT_STATUSES:
                return token
        return default
    if text in ALLOWED_GDMT_STATUSES:
        return text
    return default


def normalize_guidance(guidance: Any) -> dict[str, list[str]]:
    default = {
        "reasoning_base": [],
        "actions": [],
        "monitoring": [],
    }
    if guidance is None:
        return default

    if isinstance(guidance, dict):
        return {
            "reasoning_base": ensure_str_list(guidance.get("reasoning_base")),
            "actions": ensure_str_list(guidance.get("actions")),
            "monitoring": ensure_str_list(guidance.get("monitoring")),
        }

    if isinstance(guidance, list):
        if not guidance:
            return default
        if all(isinstance(item, dict) for item in guidance):
            reasoning: list[str] = []
            actions: list[str] = []
            monitoring: list[str] = []
            for item in guidance:
                reasoning.extend(ensure_str_list(item.get("reasoning_base")))
                actions.extend(ensure_str_list(item.get("actions")))
                monitoring.extend(ensure_str_list(item.get("monitoring")))
            return {
                "reasoning_base": reasoning,
                "actions": actions,
                "monitoring": monitoring,
            }
        if all(isinstance(item, str) for item in guidance):
            return {**default, "reasoning_base": ensure_str_list(guidance)}

    return default


def normalize_policy_body(body: dict[str, Any] | None) -> dict[str, Any]:
    if not body or not isinstance(body, dict):
        return {}

    out = dict(body)
    guidance = normalize_guidance(out.get("guidance"))
    out["guidance"] = guidance

    # Legacy top-level copies — keep in sync with guidance for old rows
    if out.get("actions") is not None:
        out["actions"] = ensure_str_list(out.get("actions"))
    if out.get("monitoring") is not None:
        out["monitoring"] = ensure_str_list(out.get("monitoring"))

    if "hfref_default_status" in out:
        out["hfref_default_status"] = normalize_gdmt_status(
            out.get("hfref_default_status"),
            default="consider",
        )
    if "non_hfref_status" in out:
        out["non_hfref_status"] = normalize_gdmt_status(
            out.get("non_hfref_status"),
            default="review",
        )

    for key in ("med_detection_terms", "warning_targets", "aliases"):
        if key in out:
            out[key] = ensure_str_list(out.get(key))

    return out
