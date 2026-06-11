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

Preferred command from the project root:

```powershell
py -m scraper.orchestration.run_ingestion_pipeline --dry-run --download-dry-run
```

Check only planned downloads:

```powershell
py -m scraper.acquisition.download_sources --dry-run
```

## Run With Existing S3 Objects

The registry URL is the source of truth. Raw PDFs/XML are scraped into LocalStack S3,
not committed to the repo. If you want to avoid replacing objects that already exist:

```powershell
py -m scraper.orchestration.run_ingestion_pipeline --use-existing
```

Use `--skip-download` only when the raw bucket already contains every registered source
object.

## Store Data In LocalStack S3

Raw clinical source files and processed KG artifacts are stored in separate LocalStack
S3 buckets:

```text
s3://hf-cdss-raw/heart_failure/
s3://hf-cdss-processed/heart_failure/
```

Start LocalStack:

```powershell
docker compose -f infrastructure\docker-compose.yml up -d localstack
```

Scrape registered sources into the raw bucket:

```powershell
py -m scraper.acquisition.download_sources --storage s3 --use-existing
```

Stage raw source files from S3 into the runtime workspace before parsing:

```powershell
py -m scraper.acquisition.sync_sources_from_s3
```

Run the full S3-backed ingestion pipeline:

```powershell
py -m scraper.orchestration.run_ingestion_pipeline --use-existing
```

The pipeline uploads `processed/` and `artifacts/` to the processed bucket after
validation. Local files under `raw/`, `processed/`, and `artifacts/` are temporary
runtime outputs and are ignored by git.

In Airflow, the `heart_failure_kg_ingestion` DAG defaults to S3-only storage. It scrapes
registered source files to the raw bucket, stages them into the runtime, runs parsing and
KG generation, publishes processed outputs, then reloads datastores from the processed
bucket.

## Validate Artifacts

```powershell
py -m scraper.validation.validate_kg_artifacts --root data\heart_failure
```

Legacy files under `data/heart_failure/scripts` are compatibility wrappers. New scraping
logic lives under `scraper/`.

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

- `skip_download=true`: use objects already present in the raw S3 bucket.
- `use_existing=true`: download only raw S3 objects that are missing.
- `parse_guidelines=false`: skip expensive PDF parsing only when processed sections are available in the runtime.
- `build_rules=true`: regenerate rule artifacts before deriving graph relationships.

The DAG runs these tasks in order:

```text
download_sources
  -> sync_sources_from_s3
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
  -> sync_processed_to_s3
  -> bootstrap_datastores
```

`bootstrap_datastores` downloads required KG artifacts from the processed bucket, reloads
ChromaDB and Neo4j, and checks PostgreSQL audit table availability.

## Safety Notes

Automated extraction is not clinical validation. Relationships and generated rules must
retain source provenance and should be reviewed before being treated as hard safety rules.
