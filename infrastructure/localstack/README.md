# LocalStack S3

LocalStack provides S3-compatible buckets for the ingestion pipeline. Source files are
scraped into the raw bucket, while normalized sections, chunks, claims, and KG artifacts
are published to the processed bucket.

Default buckets:

```text
hf-cdss-raw
hf-cdss-processed
```

Default prefix:

```text
heart_failure/
```

Start LocalStack:

```powershell
docker compose -f infrastructure\docker-compose.yml up -d localstack
```

List buckets:

```powershell
docker compose -f infrastructure\docker-compose.yml exec localstack awslocal s3 ls
```

Upload/downloads are handled by:

```text
py -m scraper.acquisition.download_sources --storage s3
py -m scraper.acquisition.sync_sources_from_s3
py -m scraper.store.sync_processed_to_s3
py -m scraper.store.sync_processed_from_s3
```

**Persistence:** The pipeline never deletes objects from S3. `store` may delete local
`processed/` and `artifacts/` only when `HF_CDSS_CLEANUP_WORKSPACE_OUTPUTS=true`
(default in CLI; Airflow compose defaults to `false`). Raw binaries live in
`hf-cdss-raw`; KG outputs in `hf-cdss-processed`.

Do **not** run `docker compose down -v` if you want to keep LocalStack data — that
removes the `localstack_data` volume. Re-runs use `load` / `extract`, which restore
from processed S3 when local chunks are missing.
