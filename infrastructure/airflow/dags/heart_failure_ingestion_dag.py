from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator


PROJECT_ROOT = os.environ.get("HF_CDSS_PROJECT_ROOT", "/opt/airflow/project")
BACKEND_ROOT = f"{PROJECT_ROOT}/backend"
DATA_ROOT = f"{PROJECT_ROOT}/data/heart_failure"
# Ephemeral raw staging — not under data/heart_failure/raw
RAW_ROOT = os.environ.get("HF_CDSS_RAW_ROOT", "/tmp/hf_cdss_raw")
PYTHON = "python"
PIPELINE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_PIPELINE_TIMEOUT_HOURS", "48"))
SOURCES_REGISTRY = os.environ.get(
    "HF_CDSS_SOURCES_REGISTRY",
    f"{DATA_ROOT}/sources/sources.example.json",
)


def data_command(command: str) -> str:
    return (
        f"mkdir -p {DATA_ROOT} {RAW_ROOT} && cd {DATA_ROOT} && "
        f"HF_CDSS_DATA_ROOT={DATA_ROOT} HF_CDSS_RAW_ROOT={RAW_ROOT} "
        f"PYTHONPATH={PROJECT_ROOT}:{BACKEND_ROOT} {command}"
    )


def pipeline_stage(stage: str, extra: str = "") -> str:
    return data_command(
        f"{PYTHON} -m scraper.orchestration.run_ingestion_pipeline "
        f"--stage {stage} --registry {SOURCES_REGISTRY} {extra}"
        ' --run-id "{{ run_id }}"'
    )


default_args = {
    "owner": "hf_cdss",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="heart_failure_kg_ingestion",
    description=(
        "S3-first clinical ingestion: acquire (raw S3) → load (staging) → "
        "extract → store (processed S3 + governance)."
    ),
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["hf-cdss", "graphrag", "ingestion", "s3"],
) as dag:
    # Acquire: HTTP/DailyMed → hf-cdss-raw only. Skip re-fetch when objects already exist.
    acquire = BashOperator(
        task_id="acquire",
        execution_timeout=timedelta(hours=3),
        bash_command=(
            "set -euo pipefail; "
            "if aws --endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566} "
            "s3 ls s3://${HF_CDSS_RAW_BUCKET:-hf-cdss-raw}/${HF_CDSS_S3_PREFIX:-heart_failure}/ "
            "2>/dev/null | grep -q .; then "
            "  echo 'Raw prefix already populated in S3; acquire will use --skip-download --use-existing'; "
            f"  {pipeline_stage('acquire', '--skip-download --use-existing --allow-failures')}; "
            "else "
            "  echo 'Raw prefix empty; downloading sources into S3'; "
            f"  {pipeline_stage('acquire', '--use-existing --allow-failures')}; "
            "fi"
        ),
    )

    load = BashOperator(
        task_id="load",
        execution_timeout=timedelta(hours=2),
        bash_command=pipeline_stage("load", "--skip-download --auto-resume"),
    )

    extract = BashOperator(
        task_id="extract",
        execution_timeout=timedelta(hours=PIPELINE_TIMEOUT_HOURS),
        bash_command=pipeline_stage("extract", "--skip-download --auto-resume"),
    )

    store = BashOperator(
        task_id="store",
        execution_timeout=timedelta(hours=2),
        bash_command=pipeline_stage(
            "store",
            "--skip-download --auto-resume --cleanup-raw-staging --cleanup-workspace-outputs",
        ),
    )

    acquire >> load >> extract >> store
