from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator


PROJECT_ROOT = os.environ.get("HF_CDSS_PROJECT_ROOT", "/opt/airflow/project")
DATA_ROOT = f"{PROJECT_ROOT}/data/heart_failure"
PYTHON = "python"
PIPELINE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_PIPELINE_TIMEOUT_HOURS", "48"))

# Defaults — override via docker-compose env, not the Airflow trigger UI.
SOURCES_REGISTRY = os.environ.get("HF_CDSS_SOURCES_REGISTRY", "sources/sources.example.json")
SKIP_DOWNLOAD = os.environ.get("HF_CDSS_INGESTION_SKIP_DOWNLOAD", "true").lower() in {"1", "true", "yes"}


def data_command(command: str) -> str:
    return f"mkdir -p {DATA_ROOT} && cd {DATA_ROOT} && PYTHONPATH={PROJECT_ROOT} {command}"


default_args = {
    "owner": "hf_cdss",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


with DAG(
    dag_id="heart_failure_kg_ingestion",
    description="Ingest clinical sources and run the full KG pipeline (zero trigger config).",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["hf-cdss", "graphrag", "ingestion"],
) as dag:
    if SKIP_DOWNLOAD:
        download_sources = BashOperator(
            task_id="download_sources",
            bash_command="echo 'Skipping download (HF_CDSS_INGESTION_SKIP_DOWNLOAD=true). Raw sources expected in S3.'",
        )
    else:
        download_sources = BashOperator(
            task_id="download_sources",
            execution_timeout=timedelta(hours=3),
            bash_command=(
                f"{data_command(PYTHON + f' -m scraper.acquisition.download_sources --registry {SOURCES_REGISTRY} ')}"
                "--storage s3 "
                "--s3-bucket ${HF_CDSS_RAW_BUCKET:-hf-cdss-raw} "
                "--s3-prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
                "--s3-endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566} "
                "--timeout 180 --use-existing --allow-failures"
            ),
        )

    run_kg_pipeline = BashOperator(
        task_id="run_kg_pipeline",
        execution_timeout=timedelta(hours=PIPELINE_TIMEOUT_HOURS),
        bash_command=(
            f"{data_command(PYTHON + f' -m scraper.orchestration.run_ingestion_pipeline --registry {SOURCES_REGISTRY} --skip-download --auto-resume ')}"
            '--run-id "{{ run_id }}"'
        ),
    )

    download_sources >> run_kg_pipeline
