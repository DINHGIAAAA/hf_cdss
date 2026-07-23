from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator

try:
    from airflow.sdk import TaskGroup
except ImportError:
    try:
        from airflow.utils.task_group import TaskGroup
    except ImportError:
        from airflow.models.taskgroup import TaskGroup  # type: ignore


PROJECT_ROOT = os.environ.get("HF_CDSS_PROJECT_ROOT", "/opt/airflow/project")
BACKEND_ROOT = f"{PROJECT_ROOT}/backend"
DATA_ROOT = f"{PROJECT_ROOT}/data/heart_failure"
# Ephemeral raw staging — not under data/heart_failure/raw
RAW_ROOT = os.environ.get("HF_CDSS_RAW_ROOT", "/tmp/hf_cdss_raw")
S3_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localstack:4566")
PYTHON = "python"
PIPELINE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_PIPELINE_TIMEOUT_HOURS", "72"))
KG_BASE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_KG_BASE_TIMEOUT_HOURS", "72"))
CATALOG_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_CATALOG_TIMEOUT_HOURS", "72"))
FINALIZE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_FINALIZE_TIMEOUT_HOURS", "6"))
LOAD_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_LOAD_TIMEOUT_HOURS", "4"))
STORE_TIMEOUT_HOURS = int(os.environ.get("HF_CDSS_AIRFLOW_STORE_TIMEOUT_HOURS", "4"))
SOURCES_REGISTRY = os.environ.get(
    "HF_CDSS_SOURCES_REGISTRY",
    f"{DATA_ROOT}/sources/sources.example.json",
)


def data_command(command: str) -> str:
    return (
        f"mkdir -p {DATA_ROOT} {RAW_ROOT} && cd {DATA_ROOT} && "
        f"HF_CDSS_DATA_ROOT={DATA_ROOT} HF_CDSS_RAW_ROOT={RAW_ROOT} "
        f"HF_CDSS_S3_ENDPOINT_URL={S3_ENDPOINT_URL} "
        f"PYTHONPATH={PROJECT_ROOT}:{BACKEND_ROOT} {command}"
    )


def pipeline_stage(stage: str, extra: str = "") -> str:
    return data_command(
        f"{PYTHON} -m scraper.orchestration.run_ingestion_pipeline "
        f"--stage {stage} --registry {SOURCES_REGISTRY} "
        f"--s3-endpoint-url {S3_ENDPOINT_URL} {extra}"
        ' --run-id "{{ run_id }}"'
    )


def extract_phase(phase: str, extra: str = "") -> str:
    """Run one extract phase without auto-resume (always execute phase steps)."""
    flags = "--skip-download"
    if extra:
        flags += f" {extra}"
    return pipeline_stage("extract", f"--extract-phase {phase} {flags}")


default_args = {
    "owner": "hf_cdss",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # Soft default; individual tasks override with longer extract timeouts.
    "execution_timeout": timedelta(hours=PIPELINE_TIMEOUT_HOURS),
}


with DAG(
    dag_id="heart_failure_kg_ingestion",
    description=(
        "S3-first clinical ingestion: acquire → load → extract group "
        "(kg_base, constraints, dose/interaction/gdmt catalogs) → store."
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
        execution_timeout=timedelta(hours=LOAD_TIMEOUT_HOURS),
        bash_command=pipeline_stage("load", "--skip-download"),
    )

    with TaskGroup(group_id="extract", tooltip="Parse KG base then catalog extract phases") as extract:
        kg_base = BashOperator(
            task_id="kg_base",
            execution_timeout=timedelta(hours=KG_BASE_TIMEOUT_HOURS),
            bash_command=extract_phase("kg_base"),
        )

        with TaskGroup(group_id="catalogs", tooltip="Constraint + governance catalog extracts") as catalogs:
            constraints = BashOperator(
                task_id="constraints",
                execution_timeout=timedelta(hours=CATALOG_TIMEOUT_HOURS),
                bash_command=extract_phase("constraints"),
            )
            dose_rules = BashOperator(
                task_id="dose_rules",
                execution_timeout=timedelta(hours=CATALOG_TIMEOUT_HOURS),
                bash_command=extract_phase("dose_rules"),
            )
            dose_safety_warnings = BashOperator(
                task_id="dose_safety_warnings",
                execution_timeout=timedelta(hours=max(6, CATALOG_TIMEOUT_HOURS // 2)),
                bash_command=extract_phase("dose_safety_warnings"),
            )
            interaction_rules = BashOperator(
                task_id="interaction_rules",
                execution_timeout=timedelta(hours=CATALOG_TIMEOUT_HOURS),
                bash_command=extract_phase("interaction_rules"),
            )
            gdmt_policies = BashOperator(
                task_id="gdmt_policies",
                execution_timeout=timedelta(hours=CATALOG_TIMEOUT_HOURS),
                bash_command=extract_phase("gdmt_policies"),
            )

            # dose_safety filters structured dose claims → must follow dose_rules
            dose_rules >> dose_safety_warnings

        finalize = BashOperator(
            task_id="finalize",
            execution_timeout=timedelta(hours=FINALIZE_TIMEOUT_HOURS),
            bash_command=extract_phase("finalize"),
        )

        kg_base >> catalogs >> finalize

    with TaskGroup(group_id="store", tooltip="Promote artifacts, sync S3, sync Postgres drafts") as store:
        promote_and_sync = BashOperator(
            task_id="promote_sync_governance",
            execution_timeout=timedelta(hours=STORE_TIMEOUT_HOURS),
            bash_command=pipeline_stage(
                "store",
                "--skip-download --cleanup-raw-staging --cleanup-workspace-outputs",
            ),
        )

    acquire >> load >> extract >> store
