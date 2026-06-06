import logging
from typing import Any

from app.modules.datastores.chroma import chroma_status, initialize_chroma
from app.modules.datastores.neo4j import initialize_neo4j, neo4j_status
from app.modules.datastores.postgres import initialize_postgres, postgres_status


logger = logging.getLogger(__name__)


def bootstrap_datastores() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, initializer in (
        ("postgres", initialize_postgres),
        ("chroma", initialize_chroma),
        ("neo4j", initialize_neo4j),
    ):
        try:
            results[name] = initializer()
        except Exception as exc:
            logger.warning("%s bootstrap unavailable: %s", name, exc)
            results[name] = {"status": "unavailable", "detail": str(exc)}
    return results


def datastore_status() -> dict[str, Any]:
    return {
        "postgres": postgres_status(),
        "chroma": chroma_status(),
        "neo4j": neo4j_status(),
    }

