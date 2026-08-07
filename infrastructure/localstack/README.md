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

## Persistence (stop / start without losing data)

**LocalStack Community** does not persist S3 via `PERSISTENCE=1` alone (that is a Pro feature). In CE,
bucket objects live under **`/tmp/localstack-s3-storage`** inside the container. Compose mounts a named
volume there:

- `hf_cdss_localstack_s3_storage` → `/tmp/localstack-s3-storage` (S3 objects)
- `hf_cdss_localstack_data` → `/var/lib/localstack` (LocalStack metadata)

The compose project name is fixed as **`hf_cdss`** so the same volumes are used whether you run from
repo root or `infrastructure/`.

**Safe:**

```powershell
docker compose -f infrastructure\docker-compose.yml stop
docker compose -f infrastructure\docker-compose.yml start
# or
docker compose -f infrastructure\docker-compose.yml down
docker compose -f infrastructure\docker-compose.yml up -d localstack
```

**Wipes S3 (and other DB volumes if you use -v on the whole stack):**

```powershell
docker compose -f infrastructure\docker-compose.yml down -v
```

Never use `-v` unless you intentionally want a clean slate.

**If you uploaded data before this S3 volume mount existed**, it was likely lost when the container
was recreated (objects only lived in container `/tmp`). Re-run ingestion once after `compose up`.

**If you uploaded data before volume names were pinned**, it may still be in the old volume
`infrastructure_localstack_data`. One-time copy into the new volume (LocalStack stopped):

```powershell
docker volume create hf_cdss_localstack_data
docker run --rm -v infrastructure_localstack_data:/from -v hf_cdss_localstack_data:/to alpine sh -c "cp -a /from/. /to/"
```

Then start LocalStack again with the standard compose file.

**Airflow cannot see S3:** If Airflow was started before the shared network fix, it may sit on
`infrastructure_default` while LocalStack is on another network — uploads in logs can target a
since-removed container. Recreate the stack from repo root:

```powershell
docker compose -f infrastructure\docker-compose.yml --profile airflow up -d --force-recreate localstack airflow
```

Verify from inside Airflow: `docker exec hf_cdss_airflow curl -s http://localstack:4566/_localstack/health`
should return JSON, not time out.

**Raw vs processed:** The `acquire` task only fills **`hf-cdss-raw`**. **`hf-cdss-processed`**
stays empty until later DAG tasks (`extract` / `store` / sync). List raw:

```powershell
docker compose -f infrastructure\docker-compose.yml exec localstack awslocal s3 ls s3://hf-cdss-raw/heart_failure/ --recursive --summarize
```

(Use `s3 ls` with a space — not `s3ls`.)

Verify objects after restart:

```powershell
docker compose -f infrastructure\docker-compose.yml exec localstack awslocal s3 ls s3://hf-cdss-processed/heart_failure/ --recursive --summarize
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
