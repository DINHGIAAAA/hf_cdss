# PostgreSQL

PostgreSQL stores append-only recommendation and verification audit events.

- `init/001_cdss_audit.sql` initializes a new empty Docker volume.
- The `datastore-init` service also applies the schema idempotently for existing volumes.
- Runtime data remains in the Docker named volume `postgres_data`.

