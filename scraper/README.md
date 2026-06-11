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

The legacy files under `data/heart_failure/scripts` are thin compatibility wrappers
that dispatch into this package.
