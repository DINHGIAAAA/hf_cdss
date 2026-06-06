# Datastore integration

The Docker stack uses each datastore for a separate responsibility:

- PostgreSQL stores append-only recommendation and verification audit events.
- ChromaDB stores evidence chunks and deterministic local embeddings for vector retrieval.
- Neo4j stores evidence entities and relationships for graph retrieval.
- LocalStack S3 stores raw downloaded clinical source files for ingestion.
- JSONL artifacts remain the fallback when ChromaDB or Neo4j is unavailable.

For runtime efficiency, PostgreSQL writes use a bounded connection pool, Neo4j retrieval
uses a full-text relationship index, and ChromaDB uses versioned collections so unchanged
evidence is not re-indexed at every startup.

Verification retrieves only the configured top-k evidence items and passes compact,
agent-specific context to the parallel LLM verifiers. The default verifier mode uses
precomputed compact context instead of mandatory tool calls, which keeps local CPU
latency suitable for demo use.

## Startup

```powershell
docker compose -f infrastructure\docker-compose.yml up -d --build
```

The one-shot `datastore-init` service idempotently creates the PostgreSQL audit table and
upserts local evidence artifacts into ChromaDB and Neo4j before the backend starts.
FastAPI startup bootstrap is disabled in Docker so API startup stays fast and predictable.

To regenerate GraphRAG artifacts from source files, see
`data/heart_failure/INGESTION.md`.

For scheduled or UI-driven ingestion, start the optional Airflow service:

```powershell
docker compose -f infrastructure\docker-compose.yml --profile airflow up -d --build airflow
```

Then open `http://localhost:8080` and trigger the `heart_failure_kg_ingestion` DAG.

## Verify datastore usage

```powershell
Invoke-RestMethod http://localhost:8000/health/dependencies
```

`POST /graphrag/context` and `POST /verify` return `context.retrieval_sources`. In Docker,
the expected sources are `neo4j` and `chromadb`. If either service is unavailable, the
response reports `local_relationships` or `local_chunks`.

Audit history for a case is available from `GET /audit/{case_id}`.

## Retrieval behavior

ChromaDB uses a deterministic hashing embedding so the stack starts without downloading a
second embedding model. It combines token and adjacent-token features and cosine search.
This is suitable for the current MVP artifacts; a medical embedding model can replace
`hashing_embedding` later without changing the GraphRAG API.
