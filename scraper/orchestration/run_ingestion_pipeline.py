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
from scraper.store.sync_processed_to_s3 import (
    cleanup_workspace_outputs,
    upload_full_workspace,
    upload_step_artifacts,
)
from scraper.store.sync_raw_to_s3 import sync_raw_staging_to_s3
from scraper.store.s3_inventory import count_s3_objects, min_raw_s3_objects

ROOT = data_root()
PROJECT_ROOT = project_root()


def workspace_kg_artifacts_present(workspace: Path) -> bool:
    """True when chunks exist locally (minimal signal that extract kg_base ran)."""
    chunks = workspace / "artifacts/chunks/chunks.jsonl"
    try:
        return chunks.is_file() and chunks.stat().st_size > 0
    except OSError:
        return False


def restore_processed_workspace_from_s3(
    *,
    workspace: Path,
    processed_bucket: str,
    s3_prefix: str,
    s3_endpoint_url: str,
    dry_run: bool,
) -> int:
    """Pull processed/artifacts from S3 when local workspace was cleared after store."""
    if dry_run or workspace_kg_artifacts_present(workspace):
        return 0
    print(
        "Local processed/artifacts missing or empty; restoring from "
        f"s3://{processed_bucket}/{s3_prefix.strip('/')}/ ..."
    )
    restored = restore_from_s3(
        workspace=workspace,
        bucket=processed_bucket,
        prefix=s3_prefix,
        endpoint_url=s3_endpoint_url,
    )
    print(f"Restored {restored} file(s) from processed S3")
    return restored


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

CATALOG_EXTRACT_PHASES = frozenset(
    {
        "dose_rules",
        "dose_safety_warnings",
        "interaction_rules",
        "gdmt_policies",
    }
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


def publish_processed_workspace_to_s3(
    *,
    label: str,
    workspace: Path,
    processed_bucket: str,
    s3_prefix: str,
    s3_endpoint_url: str,
    run_id: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    uploaded = upload_full_workspace(
        workspace=workspace,
        bucket=processed_bucket,
        prefix=s3_prefix,
        endpoint_url=s3_endpoint_url,
        run_id=run_id,
        dry_run=dry_run,
    )
    print(f"[{label}] published {uploaded} processed workspace file(s) to s3://{processed_bucket}/{s3_prefix}")


def backfill_raw_staging_to_s3(
    *,
    label: str,
    staging_root: Path,
    raw_bucket: str,
    s3_prefix: str,
    s3_endpoint_url: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    uploaded = sync_raw_staging_to_s3(
        staging_root=staging_root,
        bucket=raw_bucket,
        prefix=s3_prefix,
        endpoint_url=s3_endpoint_url,
        dry_run=dry_run,
    )
    if uploaded:
        print(f"[{label}] backfilled {uploaded} raw staging file(s) to s3://{raw_bucket}/{s3_prefix}")


def run_acquire(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """HTTP/DailyMed fetch → raw S3 bucket only (no local raw under data/)."""
    if args.skip_download:
        count = count_s3_objects(
            bucket=args.raw_bucket,
            prefix=args.s3_prefix,
            endpoint_url=args.s3_endpoint_url,
        )
        minimum = min_raw_s3_objects()
        if count < minimum:
            raise SystemExit(
                f"[acquire] --skip-download refused: only {count} object(s) under "
                f"s3://{args.raw_bucket}/{args.s3_prefix} (need >= {minimum}). "
                "Run acquire without --skip-download."
            )
        print(f"[acquire] raw S3 OK ({count} objects); skipping download")
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
    run_step("download", command, upload_artifacts=True, **step_kwargs)
    if not args.dry_run:
        raw_count = count_s3_objects(
            bucket=args.raw_bucket,
            prefix=args.s3_prefix,
            endpoint_url=args.s3_endpoint_url,
        )
        print(f"[acquire] raw S3 object count after download: {raw_count}")
        backfill_raw_staging_to_s3(
            label="acquire",
            staging_root=raw_root(),
            raw_bucket=args.raw_bucket,
            s3_prefix=args.s3_prefix,
            s3_endpoint_url=args.s3_endpoint_url,
            dry_run=args.dry_run,
        )
        publish_processed_workspace_to_s3(
            label="acquire",
            workspace=ROOT,
            processed_bucket=args.processed_bucket,
            s3_prefix=args.s3_prefix,
            s3_endpoint_url=args.s3_endpoint_url,
            run_id=step_kwargs["run_id"],
            dry_run=args.dry_run,
        )


def run_load(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Materialize raw S3 → ephemeral staging; restore processed from S3 when local workspace is empty."""
    restore_processed_workspace_from_s3(
        workspace=ROOT,
        processed_bucket=args.processed_bucket,
        s3_prefix=args.s3_prefix,
        s3_endpoint_url=args.s3_endpoint_url,
        dry_run=args.dry_run,
    )
    if args.auto_resume and not args.dry_run:
        local_progress = infer_last_completed_from_artifacts(ROOT)
        if local_progress is None and workspace_kg_artifacts_present(ROOT):
            print("[load] local artifacts present after S3 restore; continuing")

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
    backfill_raw_staging_to_s3(
        label="load",
        staging_root=raw_root(),
        raw_bucket=args.raw_bucket,
        s3_prefix=args.s3_prefix,
        s3_endpoint_url=args.s3_endpoint_url,
        dry_run=args.dry_run,
    )
    print(f"[load] raw staging ready at {raw_root()}")


def run_extract_kg_base(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Parse sources → chunks → entities → claims."""
    import gc  # Memory cleanup
    from scraper.orchestration.data_quality_report import report_kg_base

    labels_path = drug_labels_dir()
    guidelines_path = guidelines_dir()
    # Ephemeral /tmp staging is empty after container recreate; pull raw from S3 first.
    if not any(labels_path.glob("**/*")) and not any(guidelines_path.glob("**/*")):
        print(
            f"[kg_base] raw staging empty at {raw_root()}; syncing from "
            f"s3://{args.raw_bucket}/{args.s3_prefix} before parse"
        )
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

    labels = str(labels_path)
    guidelines = str(guidelines_path)

    # Parse guidelines - these can run in parallel if both input dirs exist
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
                "2",
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
        gc.collect()  # Free memory after parsing

    # Sequential steps with memory cleanup between heavy tasks
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
        gc.collect()  # Free memory after each step

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
    if not workspace_kg_artifacts_present(ROOT):
        restore_processed_workspace_from_s3(
            workspace=ROOT,
            processed_bucket=args.processed_bucket,
            s3_prefix=args.s3_prefix,
            s3_endpoint_url=args.s3_endpoint_url,
            dry_run=args.dry_run,
        )
    if not workspace_kg_artifacts_present(ROOT):
        raise SystemExit(
            f"[{catalog}] cannot extract: artifacts/chunks/chunks.jsonl missing locally and on processed S3. "
            "Run load (restore) and kg_base, or restore s3://processed/.../artifacts/chunks/."
        )
    for name, command in catalog_pipeline_steps(python, match):
        run_step(name, command, **step_kwargs)
    if not args.dry_run:
        report_governance_catalog(ROOT, catalog)
    publish_processed_workspace_to_s3(
        label=f"extract/{catalog}",
        workspace=ROOT,
        processed_bucket=args.processed_bucket,
        s3_prefix=args.s3_prefix,
        s3_endpoint_url=args.s3_endpoint_url,
        run_id=step_kwargs["run_id"],
        dry_run=args.dry_run,
    )


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
    restore_processed_workspace_from_s3(
        workspace=ROOT,
        processed_bucket=args.processed_bucket,
        s3_prefix=args.s3_prefix,
        s3_endpoint_url=args.s3_endpoint_url,
        dry_run=args.dry_run,
    )
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

    phase_only = phase not in {"all", "finalize"}
    if phase_only and not args.dry_run:
        publish_processed_workspace_to_s3(
            label=f"extract/{phase}",
            workspace=ROOT,
            processed_bucket=args.processed_bucket,
            s3_prefix=args.s3_prefix,
            s3_endpoint_url=args.s3_endpoint_url,
            run_id=step_kwargs["run_id"],
            dry_run=args.dry_run,
        )


def run_store(python: str, args: argparse.Namespace, step_kwargs: dict) -> None:
    """Promote current/runs, re-sync promoted paths to S3, sync Postgres, cleanup staging."""
    run_id = step_kwargs["run_id"]

    if args.require_human_approval:
        approved = input(
            f"[store] Pipeline run {run_id} — type 'yes' to promote extracted artifacts to production KB: "
        ).strip()
        if approved.lower() != "yes":
            print("[store] Aborted by user. Artifacts not promoted.")
            return

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

    backfill_raw_staging_to_s3(
        label="store",
        staging_root=raw_root(),
        raw_bucket=args.raw_bucket,
        s3_prefix=args.s3_prefix,
        s3_endpoint_url=args.s3_endpoint_url,
        dry_run=args.dry_run,
    )

    if args.cleanup_raw_staging and not args.dry_run:
        cleanup_staging(raw_root())

    if args.cleanup_workspace_outputs and not args.dry_run:
        cleanup_workspace_outputs(ROOT)
    elif not args.dry_run:
        print(
            "[store] kept local processed/ and artifacts/ "
            "(HF_CDSS_CLEANUP_WORKSPACE_OUTPUTS=false or --no-cleanup-workspace-outputs)"
        )


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
    parser.add_argument(
        "--force-extract-phase",
        action="store_true",
        help="Re-run extract steps for this phase (ignore checkpoint resume).",
    )
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
    parser.add_argument(
        "--require-human-approval",
        action=argparse.BooleanOptionalAction,
        default=os.environ.get("HF_REQUIRE_HUMAN_APPROVAL", "false").lower() in {"1", "true", "yes"},
        help="Pause before promoting to production KB for manual confirmation (default: false, use in CI with --no-require-human-approval).",
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

    if (
        args.stage in {"extract", "all"}
        and args.force_extract_phase
        and getattr(args, "extract_phase", "all") != "all"
    ):
        resume_from = None
        print("force-extract-phase: ignoring checkpoint resume for this extract run")

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
