# ChromaDB

ChromaDB stores evidence chunks and deterministic local embeddings.

The `datastore-init` service reads `data/heart_failure/artifacts/chunks/chunks.jsonl`,
creates a versioned collection such as `heart_failure_evidence_heart_failure_chunks_v2`.
Changing `INDEX_VERSION` creates a clean index without mutating an existing collection's
distance function.

Runtime data remains in the Docker named volume `chroma_data`.
