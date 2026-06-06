import json
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.modules.datastores.common import RELATIONSHIPS_PATH, read_jsonl
from app.schemas.graphrag import GraphFact


@lru_cache(maxsize=1)
def neo4j_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))


def initialize_neo4j() -> dict[str, Any]:
    relationships = read_jsonl(RELATIONSHIPS_PATH)
    driver = neo4j_driver()
    with driver.session() as session:
        session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE").consume()
        session.run(
            "CREATE INDEX relationship_id IF NOT EXISTS FOR ()-[r:RELATED]-() ON (r.relationship_id)"
        ).consume()
        session.run(
            "CREATE FULLTEXT INDEX relationship_search IF NOT EXISTS "
            "FOR ()-[r:RELATED]-() ON EACH [r.search_text]"
        ).consume()
        session.run("MATCH (:Entity)-[rel:RELATED]->(:Entity) DELETE rel").consume()
        session.run("MATCH (entity:Entity) WHERE NOT (entity)--() DELETE entity").consume()

        batch_size = 250
        for start in range(0, len(relationships), batch_size):
            batch = []
            for relationship in relationships[start : start + batch_size]:
                metadata = relationship.get("metadata", {})
                batch.append(
                    {
                        "relationship_id": relationship["relationship_id"],
                        "source_id": relationship["source_id"],
                        "source_type": relationship.get("source_type"),
                        "relationship_type": relationship["relationship_type"],
                        "target_id": relationship["target_id"],
                        "target_type": relationship.get("target_type"),
                        "metadata_json": json.dumps(metadata, ensure_ascii=False),
                        "search_text": " ".join(
                            [
                                relationship.get("source_id", ""),
                                relationship.get("relationship_type", ""),
                                relationship.get("target_id", ""),
                                " ".join(str(value) for value in metadata.values()),
                            ]
                        ).lower(),
                    }
                )
            session.run(
                """
                UNWIND $rows AS row
                MERGE (source:Entity {id: row.source_id})
                SET source.entity_type = row.source_type
                MERGE (target:Entity {id: row.target_id})
                SET target.entity_type = row.target_type
                MERGE (source)-[rel:RELATED {relationship_id: row.relationship_id}]->(target)
                SET rel.relationship_type = row.relationship_type,
                    rel.metadata_json = row.metadata_json,
                    rel.search_text = row.search_text
                """,
                rows=batch,
            ).consume()
    return {"status": "ok", "relationships": len(relationships)}


def retrieve_neo4j(terms: list[str], top_k: int) -> list[GraphFact]:
    search_query = " OR ".join(f'"{term}"' for term in terms if term)
    with neo4j_driver().session() as session:
        records = session.run(
            """
            CALL db.index.fulltext.queryRelationships('relationship_search', $search_query)
            YIELD relationship AS rel, score
            WITH startNode(rel) AS source, rel, endNode(rel) AS target, score
            RETURN source.id AS source_id, source.entity_type AS source_type,
                   rel.relationship_id AS fact_id, rel.relationship_type AS relationship_type,
                   rel.metadata_json AS metadata_json,
                   target.id AS target_id, target.entity_type AS target_type, score
            ORDER BY score DESC
            LIMIT $top_k
            """,
            search_query=search_query,
            top_k=top_k,
        )
        return [
            GraphFact(
                fact_id=record["fact_id"],
                source_id=record["source_id"],
                source_type=record["source_type"],
                relationship_type=record["relationship_type"],
                target_id=record["target_id"],
                target_type=record["target_type"],
                metadata=json.loads(record["metadata_json"] or "{}"),
            )
            for record in records
        ]


def neo4j_status() -> dict[str, Any]:
    try:
        with neo4j_driver().session() as session:
            count = session.run("MATCH ()-[r:RELATED]->() RETURN COUNT(r) AS count").single()["count"]
        return {"status": "ok", "relationships": count}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}
