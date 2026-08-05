from pathlib import Path

from scraper.orchestration.run_ingestion_pipeline import workspace_kg_artifacts_present


def test_workspace_kg_artifacts_present_false_when_missing(tmp_path: Path) -> None:
    assert workspace_kg_artifacts_present(tmp_path) is False


def test_workspace_kg_artifacts_present_false_when_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "artifacts/chunks/chunks.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    assert workspace_kg_artifacts_present(tmp_path) is False


def test_workspace_kg_artifacts_present_true_when_nonempty(tmp_path: Path) -> None:
    path = tmp_path / "artifacts/chunks/chunks.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"chunk_id":"c1"}\n', encoding="utf-8")
    assert workspace_kg_artifacts_present(tmp_path) is True
