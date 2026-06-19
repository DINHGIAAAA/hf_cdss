import math

from app.core.config import settings
from app.modules.datastores import artifacts
from app.modules.datastores.common import hashing_embedding


def test_hashing_embedding_is_stable_and_normalized() -> None:
    first = hashing_embedding("heart failure renal potassium")
    second = hashing_embedding("heart failure renal potassium")

    assert first == second
    assert len(first) == 384
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_hashing_embedding_changes_with_clinical_context() -> None:
    renal = hashing_embedding("heart failure renal potassium")
    rhythm = hashing_embedding("heart failure atrial fibrillation")

    assert renal != rhythm


def test_s3_artifact_sync_downloads_current_artifacts_to_runtime_cache(tmp_path, monkeypatch) -> None:
    class FakeS3Client:
        def download_file(self, bucket, key, target):
            payloads = {
                "heart_failure/artifacts/current/manifest.json": "{}",
                "heart_failure/artifacts/current/artifacts/chunks/chunks.jsonl": '{"chunk_id":"c1"}\n',
                "heart_failure/artifacts/current/artifacts/relationships/relationships.jsonl": '{"relationship_id":"r1"}\n',
                "heart_failure/artifacts/current/artifacts/entities/entities.jsonl": '{"entity_id":"e1"}\n',
                "heart_failure/artifacts/current/artifacts/claims/claims.jsonl": '{"claim_id":"cl1"}\n',
            }
            if key not in payloads:
                raise FileNotFoundError(key)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(payloads[key])

    monkeypatch.setattr(settings, "processed_bucket", "hf-cdss-processed")
    monkeypatch.setattr(settings, "s3_prefix", "heart_failure")
    monkeypatch.setattr(artifacts, "_s3_client", lambda: FakeS3Client())

    result = artifacts.sync_artifacts_from_processed_bucket(tmp_path)

    assert result["status"] == "ok"
    assert result["source_set"] == "current"
    assert (tmp_path / "artifacts/chunks/chunks.jsonl").exists()
    assert (tmp_path / "artifacts/current/manifest.json").exists()

def test_artifact_sync_fails_when_required_s3_artifact_is_missing(tmp_path, monkeypatch) -> None:
    class FakeS3Client:
        def download_file(self, bucket, key, target):
            payloads = {
                "heart_failure/artifacts/current/manifest.json": "{}",
            }
            if key not in payloads:
                raise FileNotFoundError(key)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(payloads[key])

    monkeypatch.setattr(settings, "processed_bucket", "hf-cdss-processed")
    monkeypatch.setattr(settings, "s3_prefix", "heart_failure")
    monkeypatch.setattr(artifacts, "_s3_client", lambda: FakeS3Client())

    import pytest

    with pytest.raises(RuntimeError, match="Required processed artifacts"):
        artifacts.sync_artifacts_from_processed_bucket(tmp_path)

