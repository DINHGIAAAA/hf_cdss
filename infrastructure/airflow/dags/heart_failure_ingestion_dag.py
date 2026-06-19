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
BACKEND_ROOT = f"{PROJECT_ROOT}/backend"
PYTHON = "python"
PARSE_GUIDELINE_COMMAND = (
    f"{PYTHON} -m scraper.transform.parse_guideline_pdf "
    "--input-dir raw/guidelines "
    "--documents-output processed/documents/guideline_documents.jsonl "
    "--sections-output processed/sections/guideline_sections.jsonl "
    "--tables-dir processed/tables "
    "--workers 1"
)


def data_command(command: str) -> str:
    return f"mkdir -p {DATA_ROOT} && cd {DATA_ROOT} && PYTHONPATH={PROJECT_ROOT} {command}"


def backend_command(command: str) -> str:
    return f"cd {BACKEND_ROOT} && PYTHONPATH={BACKEND_ROOT} {command}"


default_args = {
    "owner": "hf_cdss",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


with DAG(
    dag_id="heart_failure_kg_ingestion",
    description="Scrape clinical sources into S3 raw, rebuild Heart Failure KG artifacts, publish S3 processed, and reload datastores.",
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
            description="Skip scraping/downloading only when raw bucket already contains registered source objects.",
        ),
        "use_existing": Param(
            True,
            type="boolean",
            description="Do not overwrite already downloaded files.",
        ),
        "parse_guidelines": Param(
            True,
            type="boolean",
            description="Parse guideline PDFs from staged S3 raw files.",
        ),
        "build_rules": Param(
            True,
            type="boolean",
            description="Regenerate and classify rule artifacts.",
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
        bash_command=(
            "if [ '{{ params.skip_download }}' = 'True' ]; then "
            "echo 'Skipping download.'; "
            "else "
            f"{data_command(PYTHON + ' -m scraper.acquisition.download_sources --registry {{ params.registry }} ')}"
            "--storage s3 "
            "--s3-bucket ${HF_CDSS_RAW_BUCKET:-hf-cdss-raw} "
            "--s3-prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
            "--s3-endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566} "
            "{{ ' --use-existing' if params.use_existing else '' }}; "
            "fi"
        ),
    )

    sync_sources_from_s3 = BashOperator(
        task_id="sync_sources_from_s3",
        bash_command=(
            f"{data_command(PYTHON + ' -m scraper.acquisition.sync_sources_from_s3 --registry {{ params.registry }} ')}"
            "--bucket ${HF_CDSS_RAW_BUCKET:-hf-cdss-raw} "
            "--prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
            "--endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566}"
        ),
    )

    parse_guideline_pdf = BashOperator(
        task_id="parse_guideline_pdf",
        bash_command=(
            "if [ '{{ params.parse_guidelines }}' = 'True' ]; then "
            f"{data_command(PARSE_GUIDELINE_COMMAND + ' --registry {{ params.registry }}')}; "
            "else "
            "echo 'Skipping guideline PDF parsing; using existing processed sections.'; "
            "fi"
        ),
    )

    parse_drug_label_xml = BashOperator(
        task_id="parse_drug_label_xml",
        bash_command=data_command(
            f"{PYTHON} -m scraper.transform.parse_drug_label_xml "
            "--input-dir raw/drug_labels "
            "--manifest artifacts/manifests/download_manifest.json "
            "--output processed/sections/drug_label_sections.jsonl"
        ),
    )

    publish_guidelines_to_kafka = BashOperator(
        task_id="publish_guidelines_to_kafka",
        bash_command=data_command(
            f"{PYTHON} -m scraper.process.publish_to_kafka "
            "--input-file processed/sections/guideline_sections.jsonl "
            "--topic ${HF_CDSS_KAFKA_IMPORTANT_SECTIONS_TOPIC:-important_sections} "
            "--kafka-bootstrap-servers ${HF_CDSS_KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
        ),
    )

    publish_drug_labels_to_kafka = BashOperator(
        task_id="publish_drug_labels_to_kafka",
        bash_command=data_command(
            f"{PYTHON} -m scraper.process.publish_to_kafka "
            "--input-file processed/sections/drug_label_sections.jsonl "
            "--topic ${HF_CDSS_KAFKA_IMPORTANT_SECTIONS_TOPIC:-important_sections} "
            "--kafka-bootstrap-servers ${HF_CDSS_KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}"
        ),
    )

    sync_processed_to_s3 = BashOperator(
        task_id="sync_processed_to_s3",
        bash_command=data_command(
            f"{PYTHON} -m scraper.store.sync_processed_to_s3 "
            "--bucket ${{HF_CDSS_PROCESSED_BUCKET:-hf-cdss-processed}} "
            "--prefix ${{HF_CDSS_S3_PREFIX:-heart_failure}} "
            "--endpoint-url ${{HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566}} "
            "--run-id \"{{{{ params.pipeline_run_id or run_id }}}}\""
        ),
    )

    cleanup_local_processed_files = BashOperator(
        task_id="cleanup_local_processed_files",
        bash_command=data_command("rm -f processed/sections/*.jsonl processed/documents/*.jsonl"),
    )

    # Airflow giờ đây chỉ làm nhiệm vụ Data Ingestion.
    # Dữ liệu sau khi parse sẽ được đẩy vào Kafka và xử lý bởi các Docker services.
    download_sources >> sync_sources_from_s3
    sync_sources_from_s3 >> [parse_guideline_pdf, parse_drug_label_xml]
    [parse_guideline_pdf, parse_drug_label_xml] >> sync_processed_to_s3
    parse_guideline_pdf >> publish_guidelines_to_kafka
    parse_drug_label_xml >> publish_drug_labels_to_kafka
    [sync_processed_to_s3, publish_guidelines_to_kafka, publish_drug_labels_to_kafka] >> cleanup_local_processed_files
