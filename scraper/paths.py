import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data" / "heart_failure"


def project_root() -> Path:
    return PROJECT_ROOT


def backend_root() -> Path:
    return BACKEND_ROOT


def python_import_path() -> str:
    """Repo root plus backend/ so scraper steps can import app.* datastores."""
    return f"{PROJECT_ROOT}{os.pathsep}{BACKEND_ROOT}"


def data_root() -> Path:
    """Workspace for processed/artifacts/sources config — not for durable raw binaries."""
    return Path(os.environ.get("HF_CDSS_DATA_ROOT", DEFAULT_DATA_ROOT)).resolve()


def raw_root() -> Path:
    """Ephemeral raw staging directory (S3 is the durable source of truth).

    Defaults to ``.work/heart_failure/raw`` under the project (gitignored), never
    ``data/heart_failure/raw``. Override with ``HF_CDSS_RAW_ROOT`` (e.g. ``/tmp/hf_cdss_raw``).
    """
    override = (os.environ.get("HF_CDSS_RAW_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    return (PROJECT_ROOT / ".work" / "heart_failure" / "raw").resolve()


def drug_labels_dir() -> Path:
    return raw_root() / "drug_labels"


def guidelines_dir() -> Path:
    return raw_root() / "guidelines"


def sources_registry_path() -> Path:
    return data_root() / "sources" / "sources.example.json"


def default_raw_staging_fallback() -> Path:
    """Temp-dir fallback when .work is not writable."""
    return Path(tempfile.gettempdir()) / "hf_cdss" / "raw"
