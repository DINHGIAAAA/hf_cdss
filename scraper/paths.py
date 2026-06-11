import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data" / "heart_failure"


def project_root() -> Path:
    return PROJECT_ROOT


def data_root() -> Path:
    return Path(os.environ.get("HF_CDSS_DATA_ROOT", DEFAULT_DATA_ROOT)).resolve()
