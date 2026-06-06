# Neo4j

Neo4j stores entities and evidence relationships used by GraphRAG.

`schema.cypher` documents the schema applied idempotently by `datastore-init`.
Relationship retrieval uses the `relationship_search` full-text index instead of scanning
the whole graph.

Runtime data remains in the Docker named volume `neo4j_data`.

