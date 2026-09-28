"""DAG `graph_materialization` — docs/AIRFLOW_DAGS.md §13, docs/GRAPH_MODEL.md §6-§7, §15.

Runs when gold.catalog updates.

    ensure_schema      constraints/indexes (idempotent)
    reconcile          per-aggregate replace of dramas whose canonical_version is newer
                       than the graph's copy (or missing); remove unpublished dramas and
                       orphan nodes
    integrity_test     counts + invariants; blocks the asset when the graph disagrees
                       with PostgreSQL

Neo4j is a derived read model: dropping the database and re-running this DAG
rebuilds it entirely from PostgreSQL.
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, AssetAny, dag, task

from dramamemory_data.graph import projection as proj

POSTGRES_CONN_ID = "dramamemory_postgres"
GOLD_ASSET = Asset(name="gold.catalog", uri="asset://gold/catalog")
# Enrichment can change AIRED_BY (broadcaster inferred from kowiki categories).
ENRICHED_ASSET = Asset(name="enrich.synopsis", uri="asset://enrich/synopsis")
GRAPH_ASSET = Asset(name="graph.canonical", uri="asset://graph/canonical")


@dag(
    dag_id="graph_materialization",
    schedule=AssetAny(GOLD_ASSET, ENRICHED_ASSET),
    catchup=False,
    max_active_runs=1,
    tags=["graph", "neo4j"],
    doc_md=__doc__,
)
def graph_materialization():
    @task(pool="neo4j_write_pool")
    def ensure_schema() -> int:
        from dramamemory_data.graph import neo4j_client as neo

        driver = neo.connect()
        try:
            with driver.session() as session:
                for stmt in proj.SCHEMA_STATEMENTS:
                    session.run(stmt)
        finally:
            driver.close()
        return len(proj.SCHEMA_STATEMENTS)

    @task(pool="neo4j_write_pool")
    def reconcile(_: int) -> dict[str, int]:
        from dramamemory_data.graph import neo4j_client as neo

        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        driver = neo.connect()
        try:
            pg_versions = {
                int(r[0]): int(r[1]) for r in pg.get_records(proj.SELECT_PUBLISHED_VERSIONS)
            }
            graph_versions = {
                int(r["id"]): int(r["version"] or 0)
                for r in neo.run_rows(driver, proj.GRAPH_VERSIONS)
            }
            todo = proj.dramas_to_rebuild(pg_versions, graph_versions)

            with pg.get_conn() as conn, conn.cursor() as cur:
                for drama_id in todo:
                    cur.execute(proj.SELECT_DRAMA, (drama_id,))
                    row = cur.fetchone()
                    if row is None:
                        continue
                    neo.run_write(driver, proj.aggregate_statements(proj.row_to_aggregate(row)))

            removed = (
                neo.run_single(driver, proj.REMOVE_UNPUBLISHED, published=list(pg_versions)) or 0
            )
            orphans = neo.run_single(driver, proj.REMOVE_ORPHANS) or 0
        finally:
            driver.close()
        summary = {
            "published": len(pg_versions),
            "rebuilt": len(todo),
            "removed_dramas": int(removed),
            "removed_orphans": int(orphans),
        }
        print(f"graph reconcile: {summary}")
        return summary

    @task(outlets=[GRAPH_ASSET])
    def integrity_test(summary: dict[str, int]) -> dict[str, int]:
        from dramamemory_data.graph import neo4j_client as neo

        driver = neo.connect()
        try:
            stats = {
                name: int(neo.run_single(driver, q) or 0)
                for name, q in proj.INTEGRITY_QUERIES.items()
            }
        finally:
            driver.close()
        warnings = proj.check_integrity(stats, published_count=summary["published"])
        for w in warnings:
            print(f"WARNING: {w}")
        print(f"graph integrity: {stats}")
        return stats

    integrity_test(reconcile(ensure_schema()))


graph_materialization()
