from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Param

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator


PROJECT_ROOT = os.environ.get("HF_CDSS_PROJECT_ROOT", "/opt/airflow/project")
DATA_ROOT = f"{PROJECT_ROOT}/data/heart_failure"
PYTHON = "python"


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
    description="Download clinical sources to S3 raw, then run the full batch KG pipeline and publish artifacts to S3 processed.",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["hf-cdss", "graphrag", "ingestion"],
    params={
        "registry": Param(
            "sources/sources.example.json",
            type="string",
            description="Registry path relative to data/heart_failure.",
        ),
        "skip_download": Param(
            False,
            type="boolean",
            description="Skip scraping when raw S3 already has registered sources.",
        ),
        "use_existing": Param(
            True,
            type="boolean",
            description="Do not overwrite already downloaded raw objects.",
        ),
        "build_rules": Param(
            True,
            type="boolean",
            description="Generate and classify rule artifacts.",
        ),
        "pipeline_run_id": Param(
            "",
            type="string",
            description="Optional stable artifact run id. Leave empty to use the Airflow run id.",
        ),
    },
) as dag:
    download_sources = BashOperator(
        task_id="download_sources",
        execution_timeout=timedelta(hours=3),
        bash_command=(
            "{% if params.skip_download %}"
            "echo 'Skipping download.'"
            "{% else %}"
            f"{data_command(PYTHON + ' -m scraper.acquisition.download_sources --registry {{ params.registry }} ')}"
            "--storage s3 "
            "--s3-bucket ${HF_CDSS_RAW_BUCKET:-hf-cdss-raw} "
            "--s3-prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
            "--s3-endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566}"
            " --timeout 180"
            "{{ ' --use-existing' if params.use_existing else '' }}"
            " --allow-failures"
            "{% endif %}"
        ),
    )

    run_kg_pipeline = BashOperator(
        task_id="run_kg_pipeline",
        execution_timeout=timedelta(hours=6),
        bash_command=(
            f"{data_command(PYTHON + ' -m scraper.orchestration.run_ingestion_pipeline --registry {{ params.registry }} --skip-download ')}"
            "{% if not params.build_rules %}--skip-rules {% endif %}"
            '--run-id "{{ params.pipeline_run_id or run_id }}"'
        ),
    )

    download_sources >> run_kg_pipeline
