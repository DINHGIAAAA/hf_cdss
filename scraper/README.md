# Scraper Pipeline

This package owns clinical source acquisition, transformation, KG artifact processing,
validation, and S3 publishing. Runtime data remains under `data/heart_failure`, while
scraping logic lives here.

```text
scraper/
  acquisition/    download and stage raw sources from S3
  transform/      parse PDFs/XML and build normalized sections/chunks
  process/        extract entities, claims, rules, and KG relationships
  store/          publish processed outputs to S3
  validation/     validate generated KG artifacts
  orchestration/  run the end-to-end ingestion pipeline
```

Run the pipeline from the project root:

```powershell
py -m scraper.orchestration.run_ingestion_pipeline --use-existing
```

Postgres sync (after pipeline):

```powershell
py -m scraper.process.sync_governance_catalog --catalog all
```

**S3 vs local workspace:** Ingestion uploads to LocalStack S3 (`hf-cdss-raw`,
`hf-cdss-processed`). The `store` stage does **not** delete S3 objects. By default
Airflow sets `HF_CDSS_CLEANUP_WORKSPACE_OUTPUTS=false` so `data/heart_failure`
keeps a copy after store. If local folders were removed, `load` and `extract`
restore from `hf-cdss-processed` when `chunks.jsonl` is missing.

Avoid `docker compose down -v` unless you intend to wipe LocalStack volumes.

Interaction rules (FDA XML Drug Interactions → draft → Admin approve):

```powershell
py -m scraper.process.extract_fda_xml_interaction_claims
py -m scraper.orchestration.governance_catalog_steps --catalog interaction_rules
py -m scraper.process.sync_governance_catalog --catalog interaction_rules
```

See `backend/app/modules/interaction_checking/README.md` and
`docs/interaction_rules_fda_extract_proposal.md`.
