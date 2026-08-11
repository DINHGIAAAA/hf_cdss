# LocalStack (deprecated)

**This project no longer uses LocalStack for S3.**

LocalStack Community Edition does not persist S3 objects to mounted volumes — objects live in memory and are lost when the container is recreated.

Use **MinIO** instead. See [../minio/README.md](../minio/README.md).

Docker services should set `HF_CDSS_DOCKER_S3_ENDPOINT_URL=http://minio:9000`; host scripts use `HF_CDSS_S3_ENDPOINT_URL=http://localhost:4566`.
