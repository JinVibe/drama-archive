"""DAG `embedding_refresh` — docs/AIRFLOW_DAGS.md §12.

Runs when search.documents updates. Embeds every search_document whose text
changed since it was last embedded (or that was embedded by another model),
in small checkpointed batches, by calling ai-api's /internal/embed so the model
lives in one process. Emits asset://search/embeddings.
"""

from __future__ import annotations

import os

import httpx
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task

POSTGRES_CONN_ID = "dramamemory_postgres"
DOCUMENTS_ASSET = Asset(name="search.documents", uri="asset://search/documents")
EMBEDDINGS_ASSET = Asset(name="search.embeddings", uri="asset://search/embeddings")
BATCH = 16

SELECT_PENDING = """
SELECT id, title, synopsis
  FROM search_document
 WHERE embedding_updated_at IS NULL OR embedding_updated_at < updated_at
    OR embedding_model IS DISTINCT FROM %s
 ORDER BY id
 LIMIT %s
"""

UPDATE_EMBEDDING = """
UPDATE search_document
   SET embedding_synopsis = %s::vector, embedding_model = %s, embedding_updated_at = now()
 WHERE id = %s
"""


def embed_synopsis_text(title: str, synopsis: str) -> str | None:
    """The one vector per document (V14, V20): the plot with its title. The
    metadata-only vector measured as noise next to FTS and the graph and was dropped.
    None when the drama has no synopsis — such a document has no vector at all."""
    if not synopsis:
        return None
    return f"{title}\n줄거리: {synopsis}"


@dag(
    dag_id="embedding_refresh",
    schedule=[DOCUMENTS_ASSET],
    catchup=False,
    max_active_runs=1,
    tags=["search", "embedding"],
    doc_md=__doc__,
)
def embedding_refresh():
    @task(pool="embedding_api_pool", outlets=[EMBEDDINGS_ASSET])
    def refresh() -> dict[str, int | str]:
        base = os.environ["DRAMAMEMORY_AI_API_URL"]
        headers = {"X-Internal-Token": os.environ.get("DRAMAMEMORY_AI_API_TOKEN", "")}
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        ready = httpx.get(f"{base}/health/ready", timeout=30).raise_for_status().json()
        model = ready["embedding_model"]

        embedded = 0
        with httpx.Client(base_url=base, headers=headers, timeout=300) as client:
            while True:
                with pg.get_conn() as conn, conn.cursor() as cur:
                    cur.execute(SELECT_PENDING, (model, BATCH))
                    rows = cur.fetchall()
                    if not rows:
                        break
                    synopsis_texts = [embed_synopsis_text(t, s) for _, t, s in rows]
                    with_synopsis = [x for x in synopsis_texts if x]
                    vectors: list = []
                    if with_synopsis:
                        resp = client.post("/internal/embed", json={"texts": with_synopsis})
                        resp = resp.raise_for_status().json()
                        if resp["model"] != model:
                            raise RuntimeError(
                                f"model changed mid-run: {resp['model']} != {model}"
                            )
                        vectors = resp["vectors"]
                    syn_vecs = iter(vectors)
                    for (doc_id, *_), syn_text in zip(rows, synopsis_texts, strict=True):
                        syn_vec = str(next(syn_vecs)) if syn_text else None
                        cur.execute(UPDATE_EMBEDDING, (syn_vec, model, doc_id))
                    conn.commit()  # checkpoint per batch (docs §20)
                    embedded += len(rows)
        summary = {"embedded": embedded, "model": model}
        print(f"embedding refresh: {summary}")
        return summary

    refresh()


embedding_refresh()
