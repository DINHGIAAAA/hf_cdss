import argparse
import os
import subprocess
import sys
from pathlib import Path

from scraper.paths import data_root, project_root

ROOT = data_root()
PROJECT_ROOT = project_root()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def run_step(name: str, command: list[str], dry_run: bool = False) -> None:
    printable = " ".join(command)
    print(f"\n[{name}] {printable}")
    if dry_run:
        return
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PROJECT_ROOT) if not existing_pythonpath else f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"
    subprocess.run(command, cwd=ROOT, check=True, env=env)


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
    parser.add_argument("--skip-guideline-parse", action="store_true")
    parser.add_argument("--skip-rules", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the pipeline without executing steps.")
    args = parser.parse_args()

    python = sys.executable
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
        run_step("download", command, args.dry_run)

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
            args.dry_run,
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
            args.dry_run,
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
            ]
        )
    steps.extend(
        [
            ("derive_relationships", [python, "-m", "scraper.process.derive_relationships"]),
            ("validate_kg_artifacts", [python, "-m", "scraper.validation.validate_kg_artifacts", "--root", "."]),
        ]
    )

    for name, command in steps:
        run_step(name, command, args.dry_run)

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
        ],
        args.dry_run,
    )

    print("\nPipeline complete. Rebuild datastore indexes with:")
    print("docker compose -f infrastructure\\docker-compose.yml up -d --build datastore-init backend")


if __name__ == "__main__":
    main()
