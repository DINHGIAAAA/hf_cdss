"""Parameterized governance catalog pipeline steps (extract → generate → classify)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceCatalog:
    name: str
    extract_module: str
    generate_module: str
    classify_module: str


GOVERNANCE_CATALOGS: tuple[GovernanceCatalog, ...] = (
    GovernanceCatalog(
        name="dose_rules",
        extract_module="scraper.process.extract_structured_dose_claims",
        generate_module="scraper.process.generate_dose_rules",
        classify_module="scraper.process.classify_dose_rules",
    ),
    GovernanceCatalog(
        name="dose_safety_warnings",
        extract_module="scraper.process.extract_structured_dose_safety_claims",
        generate_module="scraper.process.generate_dose_safety_warnings",
        classify_module="scraper.process.classify_dose_safety_warnings",
    ),
    GovernanceCatalog(
        name="interaction_rules",
        extract_module="scraper.process.extract_structured_interaction_claims",
        generate_module="scraper.process.generate_interaction_rules",
        classify_module="scraper.process.classify_interaction_rules",
    ),
    GovernanceCatalog(
        name="gdmt_policies",
        extract_module="scraper.process.extract_structured_gdmt_policy_claims",
        generate_module="scraper.process.generate_gdmt_policies",
        classify_module="scraper.process.classify_gdmt_policies",
    ),
)

CATALOG_NAMES = tuple(c.name for c in GOVERNANCE_CATALOGS)


def _fda_extract_command(python: str) -> list[str]:
    return [
        python,
        "-m",
        "scraper.process.extract_fda_xml_interaction_claims",
        # Batch ingestion stays deterministic; optional LLM remap is slow on junk table cells.
        "--no-llm-normalize",
    ]


def _dose_rules_extract_command(python: str) -> list[str]:
    return [
        python,
        "-m",
        "scraper.process.extract_structured_dose_claims",
        # Prefer full parsed labels (includes nested SPL dosage subsections).
        # Chunks historically dropped many labels via cross-doc MinHash dedupe.
        "--input",
        "processed/sections/drug_label_sections.jsonl",
        "--drug-labels-only",
        "--dosage-sections-only",
    ]


def catalog_pipeline_steps(python: str, catalog: GovernanceCatalog) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    if catalog.name == "interaction_rules":
        steps.append(("extract_fda_xml_interaction_claims", _fda_extract_command(python)))
    extract_cmd = (
        _dose_rules_extract_command(python)
        if catalog.name == "dose_rules"
        else [python, "-m", catalog.extract_module]
    )
    steps.extend(
        [
            (f"extract_{catalog.name}", extract_cmd),
            (f"generate_{catalog.name}", [python, "-m", catalog.generate_module]),
            (f"classify_{catalog.name}", [python, "-m", catalog.classify_module]),
        ]
    )
    return steps


def pipeline_steps(python: str) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    for catalog in GOVERNANCE_CATALOGS:
        steps.extend(catalog_pipeline_steps(python, catalog))
    return steps


def main() -> None:
    import argparse
    import os

    from scraper.orchestration.data_quality_report import report_governance_catalog
    from scraper.paths import data_root, python_import_path

    parser = argparse.ArgumentParser(description="Run governance catalog extract/generate/classify steps.")
    parser.add_argument("--catalog", choices=list(CATALOG_NAMES), default=None)
    args = parser.parse_args()

    python = sys.executable
    # Same workspace as run_ingestion_pipeline (HF_CDSS_DATA_ROOT / data/heart_failure).
    root = data_root()
    env = os.environ.copy()
    import_path = python_import_path()
    env["PYTHONPATH"] = import_path if not env.get("PYTHONPATH") else f"{import_path}{os.pathsep}{env['PYTHONPATH']}"
    env["PYTHONUNBUFFERED"] = "1"

    catalogs = [c for c in GOVERNANCE_CATALOGS if c.name == args.catalog] if args.catalog else list(GOVERNANCE_CATALOGS)
    for catalog in catalogs:
        print(f"\n### governance catalog start: {catalog.name}", flush=True)
        for step_name, command in catalog_pipeline_steps(python, catalog):
            print(f"\n[{step_name}] {' '.join(command)}", flush=True)
            subprocess.run(command, cwd=str(root), check=True, env=env)
        report_governance_catalog(root, catalog.name)
        print(f"### governance catalog done: {catalog.name}", flush=True)


if __name__ == "__main__":
    main()
