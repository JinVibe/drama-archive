"""DAG `search_document_build` — docs/AIRFLOW_DAGS.md §11.

Runs when gold.catalog updates. Re-renders the search document of every
published drama whose canonical row changed since its document was written,
skips writes when the content hash is unchanged, and removes documents of
dramas that are no longer published. Emits asset://search/documents for the
embedding refresh (DM-601).
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task

from dramamemory_data.search.documents import (
    DELETE_STALE,
    DOCUMENT_VERSION,
    SELECT_DRAMAS,
    render_drama,
    row_to_source,
    upsert_document,
)

POSTGRES_CONN_ID = "dramamemory_postgres"
GOLD_ASSET = Asset(name="gold.catalog", uri="asset://gold/catalog")
DOCUMENTS_ASSET = Asset(name="search.documents", uri="asset://search/documents")


@dag(
    dag_id="search_document_build",
    schedule=[GOLD_ASSET],
    catchup=False,
    max_active_runs=1,
    tags=["search", "projection"],
    doc_md=__doc__,
)
def search_document_build():
    @task(outlets=[DOCUMENTS_ASSET])
    def build() -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        written = unchanged = 0
        with pg.get_conn() as conn, conn.cursor() as cur:
            cur.execute(SELECT_DRAMAS, (DOCUMENT_VERSION,))
            rows = cur.fetchall()
            for row in rows:
                doc = render_drama(row_to_source(row))
                if upsert_document(cur, doc):
                    written += 1
                else:
                    unchanged += 1
            cur.execute(DELETE_STALE)
            removed = cur.rowcount
            conn.commit()
        summary = {
            "candidates": len(rows), "written": written, "unchanged": unchanged, "removed": removed
        }
        print(f"search document build: {summary}")
        return summary

    build()


search_document_build()
