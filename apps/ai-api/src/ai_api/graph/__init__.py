"""Read-only graph queries over the Neo4j read model (docs/GRAPH_MODEL.md §8, §13, §14).

No raw Cypher is exposed; every query is parameterized, bounded by limits and a timeout.
"""
