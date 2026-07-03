"""Resolve active bundled dose-rules file from settings."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings

_MODULE_DIR = Path(__file__).resolve().parent
_DEFAULT_RULES_DIR = _MODULE_DIR / "rules"


def _version_suffix(version: str) -> str:
    normalized = version.strip()
    return normalized[1:] if normalized.startswith("v") else normalized


def dose_rules_bundle_dir() -> Path:
    override = (getattr(settings, "dose_rules_bundle_dir", None) or "").strip()
    if override:
        return Path(override)
    return _DEFAULT_RULES_DIR


def resolve_dose_rules_bundle_path() -> Path:
    path_override = (getattr(settings, "dose_rules_bundle_path", None) or "").strip()
    if path_override:
        return Path(path_override)
    version = _version_suffix(getattr(settings, "dose_rules_active_bundle_version", None) or "v1")
    return dose_rules_bundle_dir() / f"hf_dose_rules_v{version}.json"


def expected_bundle_version_label() -> str:
    return f"hf_dose_rules_v{_version_suffix(getattr(settings, 'dose_rules_active_bundle_version', None) or 'v1')}"
