# LocalStack (deprecated)

**This project no longer uses LocalStack for S3.**

LocalStack Community Edition does not persist S3 objects to mounted volumes — objects live in memory and are lost when the container is recreated.

Use **MinIO** instead. See [../minio/README.md](../minio/README.md).

The Docker network alias `localstack` still points to MinIO so existing `HF_CDSS_S3_ENDPOINT_URL=http://localstack:4566` settings keep working.
