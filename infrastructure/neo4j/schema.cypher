CREATE CONSTRAINT entity_id IF NOT EXISTS
FOR (entity:Entity) REQUIRE entity.id IS UNIQUE;

CREATE INDEX relationship_id IF NOT EXISTS
FOR ()-[relationship:RELATED]-() ON (relationship.relationship_id);

CREATE FULLTEXT INDEX relationship_search IF NOT EXISTS
FOR ()-[relationship:RELATED]-() ON EACH [relationship.search_text];

