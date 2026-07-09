import os
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
    return Path(os.environ.get("HF_CDSS_DATA_ROOT", DEFAULT_DATA_ROOT)).resolve()
