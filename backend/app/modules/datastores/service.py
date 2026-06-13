import logging
from typing import Any

from app.modules.datastores.artifacts import artifact_status, sync_artifacts_from_processed_bucket
from app.modules.datastores.common import DATA_ROOT
from app.modules.datastores.chroma import chroma_status, initialize_chroma
from app.modules.datastores.neo4j import initialize_neo4j, neo4j_status
from app.modules.datastores.postgres import initialize_postgres, postgres_status


logger = logging.getLogger(__name__)


def bootstrap_datastores() -> dict[str, Any]:
    results: dict[str, Any] = {}
    try:
        print("[datastore-bootstrap] syncing artifacts from processed storage...", flush=True)
        results["artifacts"] = sync_artifacts_from_processed_bucket(DATA_ROOT)
        print(f"[datastore-bootstrap] artifacts: {results['artifacts']}", flush=True)
    except Exception as exc:
        logger.warning("artifact sync unavailable: %s", exc)
        results["artifacts"] = {"status": "unavailable", "detail": str(exc)}
        print(f"[datastore-bootstrap] artifacts unavailable: {exc}", flush=True)

    for name, initializer in (
        ("postgres", initialize_postgres),
        ("chroma", initialize_chroma),
        ("neo4j", initialize_neo4j),
    ):
        try:
            print(f"[datastore-bootstrap] initializing {name}...", flush=True)
            results[name] = initializer()
            print(f"[datastore-bootstrap] {name}: {results[name]}", flush=True)
        except Exception as exc:
            logger.warning("%s bootstrap unavailable: %s", name, exc)
            results[name] = {"status": "unavailable", "detail": str(exc)}
            print(f"[datastore-bootstrap] {name} unavailable: {exc}", flush=True)
    return results


def datastore_status() -> dict[str, Any]:
    return {
        "artifacts": artifact_status(DATA_ROOT),
        "postgres": postgres_status(),
        "chroma": chroma_status(),
        "neo4j": neo4j_status(),
    }

