# MinIO S3 (replaces LocalStack CE)

Docker Compose uses **MinIO** for S3-compatible storage. LocalStack Community Edition keeps S3 objects **in memory** (`EphemeralS3ObjectStore`) and does **not** survive `docker compose up --force-recreate` even with volume mounts.

MinIO stores all objects on a named Docker volume and survives container recreate/restart.

## Endpoints

| Use | URL |
|-----|-----|
| S3 API (host) | `http://localhost:4566` |
| S3 API (in Docker network) | `http://minio:9000` |
| MinIO console | `http://localhost:9001` |

Credentials (defaults):

```text
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=testtest
```

Buckets (created by `minio-init` on every `compose up`):

```text
hf-cdss-raw
hf-cdss-processed
```

Prefix: `heart_failure/`

## Persistence

Volume: `hf_cdss_minio_data` → `/data` inside MinIO.

**Safe** (data kept):

```powershell
docker compose -f infrastructure\docker-compose.yml stop
docker compose -f infrastructure\docker-compose.yml start
docker compose -f infrastructure\docker-compose.yml down
docker compose -f infrastructure\docker-compose.yml up -d minio
```

**Wipes S3** (and Postgres/Neo4j if whole stack):

```powershell
docker compose -f infrastructure\docker-compose.yml down -v
```

Never use `-v` unless you want a clean slate.

## Verify

```powershell
docker compose -f infrastructure\docker-compose.yml exec minio mc alias set hf http://127.0.0.1:9000 test testtest
docker compose -f infrastructure\docker-compose.yml exec minio mc ls hf/hf-cdss-processed/heart_failure/ --recursive --summarize
```

Or from host (after one-time upload):

```powershell
$env:AWS_ACCESS_KEY_ID="test"
$env:AWS_SECRET_ACCESS_KEY="testtest"
aws --endpoint-url http://localhost:4566 s3 ls s3://hf-cdss-processed/heart_failure/ --recursive --summarize
```

## Re-upload after migration from LocalStack

If buckets are empty but local artifacts still exist:

```powershell
cd c:\Users\VinhNgo\hf_cdss
$env:HF_CDSS_S3_ENDPOINT_URL="http://localhost:4566"
$env:AWS_ACCESS_KEY_ID="test"
$env:AWS_SECRET_ACCESS_KEY="testtest"
py -m scraper.store.sync_processed_to_s3
```

## Migration from old LocalStack volumes

Old volumes `hf_cdss_localstack_data` / `hf_cdss_localstack_s3_storage` are unused. Remove when no longer needed:

```powershell
docker volume rm hf_cdss_localstack_data hf_cdss_localstack_s3_storage
```
