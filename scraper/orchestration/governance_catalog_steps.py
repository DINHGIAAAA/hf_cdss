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


def pipeline_steps(python: str) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    for catalog in GOVERNANCE_CATALOGS:
        if catalog.name == "interaction_rules":
            steps.append(
                (
                    "extract_fda_xml_interaction_claims",
                    [python, "-m", "scraper.process.extract_fda_xml_interaction_claims"],
                )
            )
        steps.extend(
            [
                (f"extract_{catalog.name}", [python, "-m", catalog.extract_module]),
                (f"generate_{catalog.name}", [python, "-m", catalog.generate_module]),
                (f"classify_{catalog.name}", [python, "-m", catalog.classify_module]),
            ]
        )
    return steps


def main() -> None:
    import argparse
    import os

    from scraper.paths import project_root, python_import_path

    parser = argparse.ArgumentParser(description="Run governance catalog extract/generate/classify steps.")
    parser.add_argument("--catalog", choices=[c.name for c in GOVERNANCE_CATALOGS], default=None)
    args = parser.parse_args()

    python = sys.executable
    root = project_root()
    env = os.environ.copy()
    import_path = python_import_path()
    env["PYTHONPATH"] = import_path if not env.get("PYTHONPATH") else f"{import_path}{os.pathsep}{env['PYTHONPATH']}"

    catalogs = [c for c in GOVERNANCE_CATALOGS if c.name == args.catalog] if args.catalog else list(GOVERNANCE_CATALOGS)
    for catalog in catalogs:
        steps: list[tuple[str, list[str]]] = []
        if catalog.name == "interaction_rules":
            steps.append(
                (
                    "extract_fda_xml_interaction_claims",
                    [python, "-m", "scraper.process.extract_fda_xml_interaction_claims"],
                )
            )
        steps.extend(
            [
                (f"extract_{catalog.name}", [python, "-m", catalog.extract_module]),
                (f"generate_{catalog.name}", [python, "-m", catalog.generate_module]),
                (f"classify_{catalog.name}", [python, "-m", catalog.classify_module]),
            ]
        )
        for step_name, command in steps:
            print(f"\n[{step_name}] {' '.join(command)}")
            subprocess.run(command, cwd=str(root), check=True, env=env)


if __name__ == "__main__":
    main()
