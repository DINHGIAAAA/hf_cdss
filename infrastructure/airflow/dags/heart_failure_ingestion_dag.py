from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Param
from airflow.operators.bash import BashOperator


PROJECT_ROOT = os.environ.get("HF_CDSS_PROJECT_ROOT", "/opt/airflow/project")
DATA_ROOT = f"{PROJECT_ROOT}/data/heart_failure"
BACKEND_ROOT = f"{PROJECT_ROOT}/backend"
PYTHON = "python"
PARSE_GUIDELINE_COMMAND = (
    f"{PYTHON} scripts/parse_guideline_pdf.py "
    "--input-dir raw/guidelines "
    "--documents-output processed/documents/guideline_documents.jsonl "
    "--sections-output processed/sections/guideline_sections.jsonl "
    "--tables-dir processed/tables "
    "--workers 1"
)


def data_command(command: str) -> str:
    return f"cd {DATA_ROOT} && {command}"


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
    description="Download clinical sources, rebuild Heart Failure KG artifacts, and reload ChromaDB/Neo4j/Postgres.",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule_interval=None,
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
            True,
            type="boolean",
            description="Use local files under data/heart_failure/raw instead of downloading.",
        ),
        "use_existing": Param(
            True,
            type="boolean",
            description="Do not overwrite already downloaded files.",
        ),
        "storage": Param(
            "s3",
            enum=["local", "s3"],
            description="Store downloaded source files locally or in LocalStack/S3.",
        ),
        "parse_guidelines": Param(
            False,
            type="boolean",
            description="Parse guideline PDFs. Disable for faster runs when PDF sections already exist.",
        ),
        "build_rules": Param(
            True,
            type="boolean",
            description="Regenerate and classify rule artifacts.",
        ),
    },
) as dag:
    download_sources = BashOperator(
        task_id="download_sources",
        bash_command=(
            "if [ '{{ params.skip_download }}' = 'True' ]; then "
            "echo 'Skipping download.'; "
            "else "
            f"{data_command(PYTHON + ' scripts/download_sources.py --registry {{{{ params.registry }}}} ')}"
            "--storage {{ params.storage }} "
            "--s3-bucket ${HF_CDSS_S3_BUCKET:-hf-cdss-data} "
            "--s3-prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
            "--s3-endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566} "
            "{{ ' --use-existing' if params.use_existing else '' }}; "
            "fi"
        ),
    )

    sync_sources_from_s3 = BashOperator(
        task_id="sync_sources_from_s3",
        bash_command=(
            "if [ '{{ params.storage }}' = 's3' ]; then "
            f"{data_command(PYTHON + ' scripts/sync_sources_from_s3.py --registry {{{{ params.registry }}}} ')}"
            "--bucket ${HF_CDSS_S3_BUCKET:-hf-cdss-data} "
            "--prefix ${HF_CDSS_S3_PREFIX:-heart_failure} "
            "--endpoint-url ${HF_CDSS_S3_ENDPOINT_URL:-http://localstack:4566}; "
            "else "
            "echo 'Using local raw files; skipping S3 sync.'; "
            "fi"
        ),
    )

    parse_guideline_pdf = BashOperator(
        task_id="parse_guideline_pdf",
        bash_command=(
            "if [ '{{ params.parse_guidelines }}' = 'True' ]; then "
            f"{data_command(PARSE_GUIDELINE_COMMAND)}; "
            "else "
            "echo 'Skipping guideline PDF parsing; using existing processed sections.'; "
            "fi"
        ),
    )

    parse_drug_label_xml = BashOperator(
        task_id="parse_drug_label_xml",
        bash_command=data_command(
            f"{PYTHON} scripts/parse_drug_label_xml.py "
            "--input-dir raw/drug_labels "
            "--manifest artifacts/manifests/download_manifest.json "
            "--output processed/sections/drug_label_sections.jsonl"
        ),
    )

    extract_important_sections = BashOperator(
        task_id="extract_important_sections",
        bash_command=data_command(f"{PYTHON} scripts/extract_important_sections.py"),
    )

    chunk_sections = BashOperator(
        task_id="chunk_sections",
        bash_command=data_command(f"{PYTHON} scripts/chunk_sections.py"),
    )

    extract_entities = BashOperator(
        task_id="extract_entities",
        bash_command=data_command(f"{PYTHON} scripts/extract_entities.py"),
    )

    create_claims = BashOperator(
        task_id="create_claims",
        bash_command=data_command(f"{PYTHON} scripts/create_claims.py"),
    )

    generate_rules = BashOperator(
        task_id="generate_rules",
        bash_command=(
            "if [ '{{ params.build_rules }}' = 'True' ]; then "
            f"{data_command(PYTHON + ' scripts/generate_rules.py')}; "
            "else "
            "echo 'Skipping rule generation.'; "
            "fi"
        ),
    )

    classify_rules = BashOperator(
        task_id="classify_rules",
        bash_command=(
            "if [ '{{ params.build_rules }}' = 'True' ]; then "
            f"{data_command(PYTHON + ' scripts/classify_rules.py')}; "
            "else "
            "echo 'Skipping rule classification.'; "
            "fi"
        ),
    )

    derive_relationships = BashOperator(
        task_id="derive_relationships",
        bash_command=data_command(f"{PYTHON} scripts/derive_relationships.py"),
    )

    validate_kg_artifacts = BashOperator(
        task_id="validate_kg_artifacts",
        bash_command=data_command(f"{PYTHON} scripts/validate_kg_artifacts.py --root ."),
    )

    bootstrap_datastores = BashOperator(
        task_id="bootstrap_datastores",
        bash_command=backend_command(f"{PYTHON} -m app.scripts.bootstrap_datastores"),
    )

    (
        download_sources
        >> sync_sources_from_s3
        >> parse_guideline_pdf
        >> parse_drug_label_xml
        >> extract_important_sections
        >> chunk_sections
        >> extract_entities
        >> create_claims
        >> generate_rules
        >> classify_rules
        >> derive_relationships
        >> validate_kg_artifacts
        >> bootstrap_datastores
    )
