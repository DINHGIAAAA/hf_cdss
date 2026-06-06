# LocalStack S3

LocalStack provides a local S3-compatible bucket for clinical source files used by the
ingestion pipeline.

Default bucket:

```text
hf-cdss-data
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
data/heart_failure/scripts/download_sources.py --storage s3
data/heart_failure/scripts/sync_sources_from_s3.py
```
