import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, command: list[str], dry_run: bool = False) -> None:
    printable = " ".join(command)
    print(f"\n[{name}] {printable}")
    if dry_run:
        return
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run clinical source ingestion into KG artifacts.")
    parser.add_argument("--registry", default=ROOT / "sources" / "sources.example.json", type=Path)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--download-dry-run", action="store_true")
    parser.add_argument("--use-existing", action="store_true")
    parser.add_argument("--storage", choices=["local", "s3"], default=os.environ.get("HF_CDSS_DATA_STORAGE", "local"))
    parser.add_argument("--s3-bucket", default=os.environ.get("HF_CDSS_S3_BUCKET", "hf-cdss-data"))
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
            "scripts/download_sources.py",
            "--registry",
            str(args.registry),
            "--storage",
            args.storage,
        ]
        if args.storage == "s3":
            command.extend(
                [
                    "--s3-bucket",
                    args.s3_bucket,
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

    if args.storage == "s3" and not args.download_dry_run:
        run_step(
            "sync_sources_from_s3",
            [
                python,
                "scripts/sync_sources_from_s3.py",
                "--registry",
                str(args.registry),
                "--bucket",
                args.s3_bucket,
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
                "scripts/parse_guideline_pdf.py",
                "--input-dir",
                "raw/guidelines",
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
                "scripts/parse_drug_label_xml.py",
                "--input-dir",
                "raw/drug_labels",
                "--manifest",
                "artifacts/manifests/download_manifest.json",
                "--output",
                "processed/sections/drug_label_sections.jsonl",
            ],
        ),
        ("extract_important_sections", [python, "scripts/extract_important_sections.py"]),
        ("chunk_sections", [python, "scripts/chunk_sections.py"]),
        ("extract_entities", [python, "scripts/extract_entities.py"]),
        ("create_claims", [python, "scripts/create_claims.py"]),
    ]
    if not args.skip_rules:
        steps.extend(
            [
                ("generate_rules", [python, "scripts/generate_rules.py"]),
                ("classify_rules", [python, "scripts/classify_rules.py"]),
            ]
        )
    steps.extend(
        [
            ("derive_relationships", [python, "scripts/derive_relationships.py"]),
            ("validate_kg_artifacts", [python, "scripts/validate_kg_artifacts.py", "--root", "."]),
        ]
    )

    for name, command in steps:
        run_step(name, command, args.dry_run)

    print("\nPipeline complete. Rebuild datastore indexes with:")
    print("docker compose -f infrastructure\\docker-compose.yml up -d --build datastore-init backend")


if __name__ == "__main__":
    main()
