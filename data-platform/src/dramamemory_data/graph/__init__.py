"""Neo4j graph projection (DM-802): canonical PostgreSQL rows -> Cypher statements.

`projection` is pure (no driver import) so it is unit-testable and DAG parsing never
needs the neo4j package; `neo4j_client` is the thin driver wrapper used inside tasks.
"""
