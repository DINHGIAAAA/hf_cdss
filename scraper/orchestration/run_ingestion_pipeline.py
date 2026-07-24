"""Staged KG ingestion: acquire → load → extract → store.

Durable stores:
- Raw binaries: ``HF_CDSS_RAW_BUCKET`` (S3)
- Processed sections/artifacts: ``HF_CDSS_PROCESSED_BUCKET`` (S3) after extract

Local ``data/heart_failure`` is ephemeral workspace/config. Extract publishes to
processed S3 while keeping local files for store (promote + Postgres). Store then
cleans local ``processed/`` + ``artifacts/`` and raw staging.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from scraper.acquisition.sync_sources_from_s3 import cleanup_staging
from scraper.orchestration.pipeline_checkpoint import (
    default_checkpoint_path,
    infer_last_completed_from_artifacts,
    load_checkpoint,
    resolve_auto_resume,
    save_checkpoint,
    should_skip_step,
)
from scraper.paths import (
    data_root,
    drug_labels_dir,
    guidelines_dir,
    project_root,
    python_import_path,
    raw_root,
    sources_registry_path,
)
from scraper.store.sync_processed_from_s3 import restore_from_s3
from scraper.store.sync_processed_to_s3 import cleanup_workspace_outputs, upload_step_artifacts

ROOT = data_root()
PROJECT_ROOT = project_root()
STAGES = ("acquire", "load", "extract", "store", "all")
EXTRACT_PHASES = (
    "kg_base",
    "constraints",
    "dose_rules",
    "dose_safety_warnings",
    "interaction_rules",
    "gdmt_policies",
    "finalize",
    "all",
)

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
    processed_bucket: str,
    s3_prefix: str,
    s3_endpoint_url: str,
    upload_artifacts: bool = True,
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
    import_path = python_import_path()
    env["PYTHONPATH"] = import_path if not existing_pythonpath else f"{import_path}{os.pathsep}{existing_pythonpath}"
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure child processes resolve the same ephemeral raw staging root.
    env.setdefault("HF_CDSS_RAW_ROOT", str(raw_root()))
    env.setdefault("HF_CDSS_DATA_ROOT", str(ROOT))
    subprocess.run(command, cwd=ROOT, check=True, env=env)
    save_checkpoint(checkpoint_path, run_id=run_id, step_name=name)
    if not upload_artifacts:
        return
    uploaded = upload_step_artifacts(
        name,
        workspace=ROOT,
        bucket=processed_bucket,
        prefix=s3_prefix,
        endpoint_url=s3_endpoint_url,
    )
    if uploaded:
        print(f"[{name}] synced {uploaded} artifact file(s) to S3")


def run_acquire(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """HTTP/DailyMed fetch → raw S3 bucket only (no local raw under data/)."""
    if args.skip_download:
        print("\n[acquire] skipped (--skip-download); expecting objects already in raw S3")
        return
    command = [
        python,
        "-m",
        "scraper.acquisition.download_sources",
        "--registry",
        str(args.registry),
        "--storage",
        "s3",
        "--s3-bucket",
        args.raw_bucket,
        "--s3-prefix",
        args.s3_prefix,
        "--s3-endpoint-url",
        args.s3_endpoint_url,
    ]
    if args.download_dry_run:
        command.append("--dry-run")
    if args.use_existing:
        command.append("--use-existing")
    if args.allow_failures:
        command.append("--allow-failures")
    run_step("download", command, upload_artifacts=False, **step_kwargs)


def run_load(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Materialize raw S3 → ephemeral staging; optionally restore processed from S3."""
    if args.auto_resume and not args.dry_run:
        local_progress = infer_last_completed_from_artifacts(ROOT)
        if local_progress is None:
            print("No local pipeline artifacts found; attempting restore from processed S3...")
            restored = restore_from_s3(
                workspace=ROOT,
                bucket=args.processed_bucket,
                prefix=args.s3_prefix,
                endpoint_url=args.s3_endpoint_url,
            )
            print(f"Restored {restored} file(s) from s3://{args.processed_bucket}/{args.s3_prefix}")

    if args.download_dry_run:
        return

    run_step(
        "sync_sources_from_s3",
        [
            python,
            "-m",
            "scraper.acquisition.sync_sources_from_s3",
            "--mode",
            "prefix",
            "--bucket",
            args.raw_bucket,
            "--prefix",
            args.s3_prefix,
            "--endpoint-url",
            args.s3_endpoint_url,
            "--workspace",
            str(ROOT),
            "--raw-root",
            str(raw_root()),
            "--purge-legacy-data-raw",
        ],
        upload_artifacts=False,
        **step_kwargs,
    )
    print(f"[load] raw staging ready at {raw_root()}")


def run_extract_kg_base(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Parse sources → chunks → entities → claims."""
    from scraper.orchestration.data_quality_report import report_kg_base

    labels = str(drug_labels_dir())
    guidelines = str(guidelines_dir())

    if not args.skip_guideline_parse:
        run_step(
            "parse_guideline_pdf",
            [
                python,
                "-m",
                "scraper.transform.parse_guideline_pdf",
                "--input-dir",
                guidelines,
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
            **step_kwargs,
        )
        run_step(
            "parse_guideline_html",
            [
                python,
                "-m",
                "scraper.transform.parse_guideline_html",
                "--input-dir",
                guidelines,
                "--registry",
                str(args.registry),
                "--sections-output",
                "processed/sections/guideline_html_sections.jsonl",
            ],
            **step_kwargs,
        )

    for name, command in [
        (
            "parse_drug_label_xml",
            [
                python,
                "-m",
                "scraper.transform.parse_drug_label_xml",
                "--input-dir",
                labels,
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
    ]:
        run_step(name, command, **step_kwargs)

    if not args.dry_run:
        report_kg_base(ROOT)


def run_extract_constraints(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    from scraper.orchestration.data_quality_report import report_constraints

    if args.skip_rules:
        print("\n[constraints] skipped (--skip-rules)")
        return
    for name, command in [
        ("generate_rules", [python, "-m", "scraper.process.generate_rules"]),
        ("refine_constraint_conditions", [python, "-m", "scraper.process.refine_constraint_conditions"]),
        ("classify_rules", [python, "-m", "scraper.process.classify_rules"]),
    ]:
        run_step(name, command, **step_kwargs)
    if not args.dry_run:
        report_constraints(ROOT)


def run_extract_governance_catalog(
    python: str,
    args: argparse.Namespace,
    step_kwargs: dict,
    *,
    catalog: str,
) -> None:
    from scraper.orchestration.data_quality_report import report_governance_catalog
    from scraper.orchestration.governance_catalog_steps import (
        GOVERNANCE_CATALOGS,
        catalog_pipeline_steps,
    )

    if args.skip_rules:
        print(f"\n[{catalog}] skipped (--skip-rules)")
        return
    match = next((item for item in GOVERNANCE_CATALOGS if item.name == catalog), None)
    if match is None:
        raise ValueError(f"Unknown governance catalog: {catalog}")
    for name, command in catalog_pipeline_steps(python, match):
        run_step(name, command, **step_kwargs)
    if not args.dry_run:
        report_governance_catalog(ROOT, catalog)


def run_extract_finalize(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    from scraper.orchestration.data_quality_report import report_finalize

    for name, command in [
        ("derive_relationships", [python, "-m", "scraper.process.derive_relationships"]),
        (
            "repair_chunk_provenance",
            [
                python,
                "-m",
                "scraper.process.repair_chunk_provenance",
                "--chunks",
                "artifacts/chunks/chunks.jsonl",
                "--claims",
                "artifacts/claims/claims.jsonl",
                "--registry",
                str(args.registry),
            ],
        ),
        ("validate_kg_artifacts", [python, "-m", "scraper.validation.validate_kg_artifacts", "--root", "."]),
    ]:
        run_step(name, command, **step_kwargs)

    if not args.dry_run:
        report_finalize(ROOT)

    run_id = step_kwargs["run_id"]
    run_step(
        "publish_extract_to_processed_s3",
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
        upload_artifacts=False,
        **step_kwargs,
    )
    if not args.skip_rules:
        run_step(
            "publish_governance_catalogs_to_s3",
            [
                python,
                "-m",
                "scraper.store.upload_governance_catalogs_to_s3",
                "--bucket",
                args.processed_bucket,
                "--prefix",
                args.s3_prefix,
                "--endpoint-url",
                args.s3_endpoint_url,
            ],
            upload_artifacts=False,
            **step_kwargs,
        )
    print(
        f"[extract/finalize] published to s3://{args.processed_bucket}/{args.s3_prefix} "
        "(local workspace kept for store/promote; cleaned after store)"
    )


def run_extract(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Parse / transform / claim / rule generation, then publish to processed S3."""
    phase = getattr(args, "extract_phase", "all") or "all"
    print(f"Extract phase: {phase}")

    if phase in {"kg_base", "all"}:
        run_extract_kg_base(python, args, step_kwargs)
    if phase in {"constraints", "all"}:
        run_extract_constraints(python, args, step_kwargs)
    if phase in {"dose_rules", "all"}:
        run_extract_governance_catalog(python, args, step_kwargs, catalog="dose_rules")
    if phase in {"dose_safety_warnings", "all"}:
        run_extract_governance_catalog(python, args, step_kwargs, catalog="dose_safety_warnings")
    if phase in {"interaction_rules", "all"}:
        run_extract_governance_catalog(python, args, step_kwargs, catalog="interaction_rules")
    if phase in {"gdmt_policies", "all"}:
        run_extract_governance_catalog(python, args, step_kwargs, catalog="gdmt_policies")
    if phase in {"finalize", "all"}:
        run_extract_finalize(python, args, step_kwargs)


def run_store(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Promote current/runs, re-sync promoted paths to S3, sync Postgres, cleanup staging."""
    run_id = step_kwargs["run_id"]

    run_step(
        "promote_artifacts",
        [python, "-m", "scraper.store.promote_artifacts", "--workspace", ".", "--run-id", run_id],
        **step_kwargs,
    )
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
        upload_artifacts=False,
        **step_kwargs,
    )
    if not args.skip_rules:
        run_step(
            "sync_governance_catalogs",
            [python, "-m", "scraper.process.sync_governance_catalog", "--catalog", "all"],
            upload_artifacts=False,
            **step_kwargs,
        )

    if args.cleanup_raw_staging and not args.dry_run:
        cleanup_staging(raw_root())

    if args.cleanup_workspace_outputs and not args.dry_run:
        cleanup_workspace_outputs(ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run staged clinical source ingestion (S3-first).")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="all",
        help="Pipeline stage to run (Airflow uses acquire|load|extract|store).",
    )
    parser.add_argument(
        "--extract-phase",
        choices=EXTRACT_PHASES,
        default="all",
        help=(
            "When --stage extract: which extract phase to run "
            "(kg_base|constraints|dose_rules|dose_safety_warnings|interaction_rules|gdmt_policies|finalize|all)."
        ),
    )
    parser.add_argument("--registry", default=None, type=Path)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--download-dry-run", action="store_true")
    parser.add_argument("--use-existing", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    parser.add_argument("--raw-bucket", default=os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw"))
    parser.add_argument("--processed-bucket", default=os.environ.get("HF_CDSS_PROCESSED_BUCKET", "hf-cdss-processed"))
    parser.add_argument("--s3-prefix", default=os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure"))
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566"))
    parser.add_argument("--run-id", default=os.environ.get("HF_CDSS_PIPELINE_RUN_ID"))
    parser.add_argument("--skip-guideline-parse", action="store_true")
    parser.add_argument("--skip-rules", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-from", default=None)
    parser.add_argument("--auto-resume", action="store_true")
    parser.add_argument("--checkpoint-file", default=None, type=Path)
    parser.add_argument(
        "--cleanup-raw-staging",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("HF_CDSS_CLEANUP_RAW_STAGING", "true").lower() in {"1", "true", "yes"},
        help="Delete ephemeral raw staging after store (default: true).",
    )
    parser.add_argument(
        "--cleanup-workspace-outputs",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("HF_CDSS_CLEANUP_WORKSPACE_OUTPUTS", "true").lower() in {"1", "true", "yes"},
        help="After store finishes, delete local processed/ and artifacts/ (default: true).",
    )
    args = parser.parse_args()
    args.registry = Path(args.registry) if args.registry else sources_registry_path()

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
    print(f"Stage: {args.stage}")
    if args.stage in {"extract", "all"}:
        print(f"Extract phase: {args.extract_phase}")
    print(f"Data workspace: {ROOT}")
    print(f"Raw staging (ephemeral): {raw_root()}")
    if resume_from:
        print(f"Resuming from step: {resume_from} (checkpoint={checkpoint_path})")

    step_kwargs = {
        "dry_run": args.dry_run,
        "run_id": run_id,
        "checkpoint_path": checkpoint_path,
        "resume_from": resume_from,
        "checkpoint": checkpoint,
        "processed_bucket": args.processed_bucket,
        "s3_prefix": args.s3_prefix,
        "s3_endpoint_url": args.s3_endpoint_url,
    }

    stage = args.stage
    if stage in {"acquire", "all"}:
        run_acquire(python, args, step_kwargs)
    if stage in {"load", "all"}:
        run_load(python, args, step_kwargs)
    if stage in {"extract", "all"}:
        run_extract(python, args, step_kwargs)
    if stage in {"store", "all"}:
        run_store(python, args, step_kwargs)

    if stage == "all":
        print("\nPipeline complete. Rebuild datastore indexes with:")
        print("docker compose -f infrastructure\\docker-compose.yml up -d --build datastore-init backend")


if __name__ == "__main__":
    main()
