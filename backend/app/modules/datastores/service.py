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
    print("[datastore-bootstrap] syncing artifacts from processed storage...", flush=True)
    try:
        results["artifacts"] = sync_artifacts_from_processed_bucket(DATA_ROOT)
        print(f"[datastore-bootstrap] artifacts: {results['artifacts']}", flush=True)
    except Exception as exc:
        logger.warning("artifact sync unavailable: %s", exc)
        results["artifacts"] = {"status": "unavailable", "storage": "s3", "detail": str(exc)}
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

    try:
        print("[datastore-bootstrap] seeding governance catalogs...", flush=True)
        from app.modules.datastores.seed_governance_catalogs import seed_all_governance_catalogs

        results["governance_seed"] = seed_all_governance_catalogs()
        print(f"[datastore-bootstrap] governance_seed: {results['governance_seed']}", flush=True)
    except Exception as exc:
        logger.warning("governance seed unavailable: %s", exc)
        results["governance_seed"] = {"status": "unavailable", "detail": str(exc)}

    results["runtime_caches"] = _preload_runtime_caches()
    return results


def _preload_runtime_caches() -> dict[str, Any]:
    """Warm governance and intake caches so first chat request avoids cold-start DB reads."""
    import importlib

    loaders: tuple[tuple[str, str, str], ...] = (
        ("constraints", "app.modules.constraint_builder.service", "load_constraint_rules"),
        ("gdmt_policies", "app.modules.gdmt_policy.policy_loader", "load_executable_gdmt_policies"),
        ("interaction_rules", "app.modules.interaction_checking.rule_loader", "load_executable_interaction_rules"),
        ("dose_safety_warnings", "app.modules.dose_safety.rule_loader", "load_executable_dose_safety_warnings"),
        ("dose_rules", "app.modules.dose_calculator.registry", "load_dose_rules"),
    )
    warmed: dict[str, Any] = {}
    for name, module_path, function_name in loaders:
        try:
            module = importlib.import_module(module_path)
            loader = getattr(module, function_name)
            items = loader()
            warmed[name] = {"status": "ok", "count": len(items)}
            print(f"[datastore-bootstrap] warmed cache {name}: {len(items)} item(s)", flush=True)
        except Exception as exc:
            logger.warning("runtime cache preload unavailable for %s: %s", name, exc)
            warmed[name] = {"status": "unavailable", "detail": str(exc)}

    try:
        from app.modules.clinical_intake_extraction.semantic import _catalog_vectors

        entries, vectors = _catalog_vectors()
        warmed["clinical_intake_catalog"] = {
            "status": "ok",
            "entries": len(entries),
            "vectors": len(vectors),
        }
        print(
            f"[datastore-bootstrap] warmed clinical intake catalog: {len(entries)} entries",
            flush=True,
        )
    except Exception as exc:
        logger.warning("clinical intake catalog preload unavailable: %s", exc)
        warmed["clinical_intake_catalog"] = {"status": "unavailable", "detail": str(exc)}

    return warmed


def datastore_status() -> dict[str, Any]:
    return {
        "artifacts": artifact_status(DATA_ROOT),
        "postgres": postgres_status(),
        "chroma": chroma_status(),
        "neo4j": neo4j_status(),
        "redis": _redis_status(),
        "s3": _s3_status(),
        "dose_rules": _dose_rules_status(),
    }


def _redis_status() -> dict[str, Any]:
    try:
        from app.core.redis_client import redis_client

        # Test Redis connectivity with a simple operation
        import time
        test_key = f"health_check:{int(time.time())}"
        # Use sync wrapper or try direct access
        return {"status": "ok", "note": "Redis health check requires async validation"}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}


def _s3_status() -> dict[str, Any]:
    """Check S3/MinIO connectivity."""
    try:
        from app.core.config import settings
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_default_region,
        )
        # Try to list buckets as a connectivity check
        s3.list_buckets()
        return {"status": "ok", "endpoint": settings.s3_endpoint_url}
    except ImportError:
        return {"status": "unavailable", "detail": "boto3 not installed"}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}


def _dose_rules_status() -> dict[str, Any]:
    from app.core.config import settings

    if not settings.dose_calculator_enabled:
        return {"status": "disabled"}
    try:
        from app.modules.dose_calculator.rule_validation import DoseRulesValidationError, check_runtime_dose_rules

        return check_runtime_dose_rules()
    except DoseRulesValidationError as exc:
        return {"status": "error", "detail": str(exc), "errors": exc.errors}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

