import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from scraper.orchestration.pipeline_checkpoint import (
    default_checkpoint_path,
    load_checkpoint,
    resolve_auto_resume,
    save_checkpoint,
    should_skip_step,
)
from scraper.paths import data_root, project_root

ROOT = data_root()
PROJECT_ROOT = project_root()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def run_step(
    name: str,
    command: list[str],
    *,
    dry_run: bool = False,
    run_id: str,
    checkpoint_path: Path,
    resume_from: str | None,
    checkpoint: dict | None,
) -> None:
    if should_skip_step(name, resume_from=resume_from, checkpoint=checkpoint):
        print(f"\n[{name}] skipped (checkpoint/resume)")
        return
    printable = " ".join(command)
    print(f"\n[{name}] {printable}")
    if dry_run:
        return
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT) if not existing_pythonpath else f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(command, cwd=ROOT, check=True, env=env)
    save_checkpoint(checkpoint_path, run_id=run_id, step_name=name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run clinical source ingestion into KG artifacts.")
    parser.add_argument("--registry", default=ROOT / "sources" / "sources.example.json", type=Path)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--download-dry-run", action="store_true")
    parser.add_argument("--use-existing", action="store_true")
    parser.add_argument("--storage", choices=["s3"], default="s3")
    parser.add_argument("--raw-bucket", default=os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw"))
    parser.add_argument("--processed-bucket", default=os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed"))
    parser.add_argument("--s3-prefix", default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"))
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"))
    parser.add_argument("--run-id", default=os.environ.get("HF_CDSS_PIPELINE_RUN_ID"))
    parser.add_argument("--skip-guideline-parse", action="store_true")
    parser.add_argument("--skip-rules", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the pipeline without executing steps.")
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Skip steps before this checkpoint step name (see .pipeline_checkpoint.json).",
    )
    parser.add_argument(
        "--auto-resume",
        action="store_true",
        help="Resume from checkpoint/artifacts for the same --run-id (used by Airflow retries).",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=None,
        type=Path,
        help="Checkpoint file path (default: data_root/.pipeline_checkpoint.json).",
    )
    args = parser.parse_args()

    python = sys.executable
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    checkpoint_path = args.checkpoint_file or default_checkpoint_path(ROOT)
    checkpoint = load_checkpoint(checkpoint_path)
    resume_from = resolve_auto_resume(
        resume_from=args.resume_from,
        auto_resume=args.auto_resume,
        checkpoint=checkpoint,
        run_id=run_id,
        data_root=ROOT,
    )
    print(f"Pipeline run id: {run_id}")
    if resume_from:
        print(f"Resuming from step: {resume_from} (checkpoint={checkpoint_path})")
    if not args.skip_download:
        command = [
            python,
            "-m",
            "scraper.acquisition.download_sources",
            "--registry",
            str(args.registry),
            "--storage",
            args.storage,
        ]
        command.extend(
            [
                "--s3-bucket",
                args.raw_bucket,
                "--s3-prefix",
                args.s3_prefix,
                "--s3-endpoint-url",
                args.s3_endpoint_url,
            ]
        )
        if args.download_dry_run:
            command.append("--dry-run")
        if args.use_existing:
            command.append("--use-existing")
        run_step(
            "download",
            command,
            dry_run=args.dry_run,
            run_id=run_id,
            checkpoint_path=checkpoint_path,
            resume_from=resume_from,
            checkpoint=checkpoint,
        )

    if not args.download_dry_run:
        run_step(
            "sync_sources_from_s3",
            [
                python,
                "-m",
                "scraper.acquisition.sync_sources_from_s3",
                "--registry",
                str(args.registry),
                "--bucket",
                args.raw_bucket,
                "--prefix",
                args.s3_prefix,
                "--endpoint-url",
                args.s3_endpoint_url,
            ],
            dry_run=args.dry_run,
            run_id=run_id,
            checkpoint_path=checkpoint_path,
            resume_from=resume_from,
            checkpoint=checkpoint,
        )

    if not args.skip_guideline_parse:
        run_step(
            "parse_guideline_pdf",
            [
                python,
                "-m",
                "scraper.transform.parse_guideline_pdf",
                "--input-dir",
                "raw/guidelines",
                "--registry",
                str(args.registry),
                "--documents-output",
                "processed/documents/guideline_documents.jsonl",
                "--sections-output",
                "processed/sections/guideline_sections.jsonl",
                "--tables-dir",
                "processed/tables",
                "--workers",
                "1",
            ],
            dry_run=args.dry_run,
            run_id=run_id,
            checkpoint_path=checkpoint_path,
            resume_from=resume_from,
            checkpoint=checkpoint,
        )
        run_step(
            "parse_guideline_html",
            [
                python,
                "-m",
                "scraper.transform.parse_guideline_html",
                "--input-dir",
                "raw/guidelines",
                "--registry",
                str(args.registry),
                "--sections-output",
                "processed/sections/guideline_html_sections.jsonl",
            ],
            dry_run=args.dry_run,
            run_id=run_id,
            checkpoint_path=checkpoint_path,
            resume_from=resume_from,
            checkpoint=checkpoint,
        )

    steps = [
        (
            "parse_drug_label_xml",
            [
                python,
                "-m",
                "scraper.transform.parse_drug_label_xml",
                "--input-dir",
                "raw/drug_labels",
                "--manifest",
                "artifacts/manifests/download_manifest.json",
                "--registry",
                str(args.registry),
                "--output",
                "processed/sections/drug_label_sections.jsonl",
            ],
        ),
        ("extract_important_sections", [python, "-m", "scraper.transform.extract_important_sections"]),
        ("chunk_sections", [python, "-m", "scraper.transform.chunk_sections"]),
        ("extract_entities", [python, "-m", "scraper.process.extract_entities"]),
        ("create_claims", [python, "-m", "scraper.process.create_claims"]),
    ]
    if not args.skip_rules:
        steps.extend(
            [
                ("generate_rules", [python, "-m", "scraper.process.generate_rules"]),
                ("classify_rules", [python, "-m", "scraper.process.classify_rules"]),
                (
                    "governance_catalog_steps",
                    [python, "-m", "scraper.orchestration.governance_catalog_steps"],
                ),
            ]
        )
    steps.extend(
        [
            ("derive_relationships", [python, "-m", "scraper.process.derive_relationships"]),
            ("validate_kg_artifacts", [python, "-m", "scraper.validation.validate_kg_artifacts", "--root", "."]),
            ("promote_artifacts", [python, "-m", "scraper.store.promote_artifacts", "--workspace", ".", "--run-id", run_id]),
        ]
    )

    step_kwargs = {
        "dry_run": args.dry_run,
        "run_id": run_id,
        "checkpoint_path": checkpoint_path,
        "resume_from": resume_from,
        "checkpoint": checkpoint,
    }

    for name, command in steps:
        run_step(name, command, **step_kwargs)

    run_step(
        "sync_processed_to_s3",
        [
            python,
            "-m",
            "scraper.store.sync_processed_to_s3",
            "--bucket",
            args.processed_bucket,
            "--prefix",
            args.s3_prefix,
            "--endpoint-url",
            args.s3_endpoint_url,
            "--run-id",
            run_id,
        ],
        **step_kwargs,
    )

    if not args.skip_rules:
        run_step(
            "sync_governance_catalogs",
            [python, "-m", "scraper.process.sync_governance_catalog", "--catalog", "all"],
            **step_kwargs,
        )

    print("\nPipeline complete. Rebuild datastore indexes with:")
    print("docker compose -f infrastructure\\docker-compose.yml up -d --build datastore-init backend")


if __name__ == "__main__":
    main()
