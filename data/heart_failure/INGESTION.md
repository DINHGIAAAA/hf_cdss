# Clinical Source Ingestion Pipeline

This pipeline turns curated clinical source files into GraphRAG artifacts.

```text
sources registry
  -> download manifest
  -> PDF/XML parsing
  -> important section selection
  -> chunking
  -> entity extraction
  -> claim extraction
  -> rule classification
  -> relationship derivation
  -> validation
  -> ChromaDB + Neo4j bootstrap
```

## Add A Source

Copy or edit:

```text
data/heart_failure/sources/sources.example.json
```

Each source should include:

- `source_id`
- `title`
- `source_type`
- `publisher`
- `url`
- `target_path`
- `license_note`

Use official sources when possible, such as AHA/ACC/HFSA, ESC, KDIGO, ADA, or DailyMed.

## Dry Run

Check the planned pipeline without changing files:

```powershell
python data\heart_failure\scripts\run_ingestion_pipeline.py --dry-run --download-dry-run
```

Check only planned downloads:

```powershell
python data\heart_failure\scripts\download_sources.py --dry-run
```

## Run With Existing Local Files

If PDFs/XML files already exist under `data/heart_failure/raw`, skip network downloads:

```powershell
python data\heart_failure\scripts\run_ingestion_pipeline.py --skip-download
```

If you want to use the registry but avoid replacing files that already exist:

```powershell
python data\heart_failure\scripts\run_ingestion_pipeline.py --use-existing
```

## Store Source Files In LocalStack S3

Raw clinical source files can be stored in LocalStack instead of being kept in the repo.
The default local bucket is:

```text
s3://hf-cdss-data/heart_failure/
```

Start LocalStack:

```powershell
docker compose -f infrastructure\docker-compose.yml up -d localstack
```

Download registered sources into LocalStack:

```powershell
python data\heart_failure\scripts\download_sources.py --storage s3 --use-existing
```

Sync source files from LocalStack to the local runtime before parsing:

```powershell
python data\heart_failure\scripts\sync_sources_from_s3.py
```

Run the full ingestion pipeline using LocalStack-backed source storage:

```powershell
python data\heart_failure\scripts\run_ingestion_pipeline.py --storage s3 --use-existing
```

In Airflow, the `heart_failure_kg_ingestion` DAG defaults to `storage=s3`. It downloads
registered source files to LocalStack, syncs them into the runtime, then runs parsing and
KG generation.

## Validate Artifacts

```powershell
python data\heart_failure\scripts\validate_kg_artifacts.py --root data\heart_failure
```

## Load Into Datastores

After artifacts are regenerated:

```powershell
docker compose -f infrastructure\docker-compose.yml up -d --build datastore-init backend
```

This updates:

- ChromaDB evidence chunks
- Neo4j graph relationships

## Run With Airflow

The same pipeline is available as an Airflow DAG:

```text
heart_failure_kg_ingestion
```

Start Airflow with the optional Compose profile:

```powershell
docker compose -f infrastructure\docker-compose.yml --profile airflow up -d --build airflow
```

Open:

```text
http://localhost:8080
```

Default development login:

```text
username: admin
password: admin
```

Trigger the DAG manually. Useful DAG parameters:

- `skip_download=true`: use files already present under `data/heart_failure/raw`.
- `use_existing=true`: download only files that are missing.
- `parse_guidelines=false`: skip expensive PDF parsing when processed guideline sections already exist.
- `build_rules=true`: regenerate rule artifacts before deriving graph relationships.

The DAG runs these tasks in order:

```text
download_sources
  -> parse_guideline_pdf
  -> parse_drug_label_xml
  -> extract_important_sections
  -> chunk_sections
  -> extract_entities
  -> create_claims
  -> generate_rules
  -> classify_rules
  -> derive_relationships
  -> validate_kg_artifacts
  -> bootstrap_datastores
```

`bootstrap_datastores` reloads ChromaDB and Neo4j from the generated artifacts and checks
PostgreSQL audit table availability.

## Safety Notes

Automated extraction is not clinical validation. Relationships and generated rules must
retain source provenance and should be reviewed before being treated as hard safety rules.
