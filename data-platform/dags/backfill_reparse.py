"""DAG `backfill_reparse` — docs/AIRFLOW_DAGS.md §5/§6, DM-208 (manual trigger).

Re-runs the silver/gold chain over raw snapshots that are already in object
storage, without fetching anything: the raw layer is the replay log
(README principle 1/2). Use it after a parser or resolution-rule change.

    params.source_code   which source's records (default wikidata)
    params.mode          "stale"  records whose staging row was parsed by an older
                                  parser_version than the current one (default)
                         "all"    every record of the source
                         "failed" only PARSE_FAILED / REJECTED rows

    select → mark the staging rows PARSE_FAILED so normalize_catalog picks them up
           → emit raw.source_records.{source} so the normal chain runs
             (normalize → entity_resolution → publish → search/graph)

Nothing is deleted: a re-parse upserts the same staging row (same
source_record_id) and publish maps onto the same canonical rows through
external_ref. Earlier re-parses were done with ad-hoc SQL; this is that SQL
with a name, parameters and an audit trail in the DAG run.
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.parsers import parser_for
from dramamemory_data.sources import SOURCES

POSTGRES_CONN_ID = "dramamemory_postgres"

SELECT = {
    "stale": """
        UPDATE staging_record st SET status = 'PARSE_FAILED'
          FROM source_record sr JOIN source s ON s.id = sr.source_id
         WHERE st.source_record_id = sr.id AND s.code = %(source)s
           AND st.parser_version <> %(version)s
           AND st.status IN ('PUBLISHED', 'REJECTED', 'PARSE_FAILED')
        """,
    "all": """
        UPDATE staging_record st SET status = 'PARSE_FAILED'
          FROM source_record sr JOIN source s ON s.id = sr.source_id
         WHERE st.source_record_id = sr.id AND s.code = %(source)s
           AND st.status IN ('PUBLISHED', 'REJECTED', 'PARSE_FAILED')
        """,
    "failed": """
        UPDATE staging_record st SET status = 'PARSE_FAILED'
          FROM source_record sr JOIN source s ON s.id = sr.source_id
         WHERE st.source_record_id = sr.id AND s.code = %(source)s
           AND st.status IN ('REJECTED', 'PARSE_FAILED')
        """,
}


@dag(
    dag_id="backfill_reparse",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["silver", "backfill"],
    params={
        "source_code": Param("wikidata", type="string", enum=sorted(SOURCES)),
        "mode": Param("stale", type="string", enum=["stale", "all", "failed"]),
    },
    doc_md=__doc__,
)
def backfill_reparse():
    @task
    def mark(params: dict) -> dict[str, str | int]:
        source = params["source_code"]
        mode = params["mode"]
        version, _ = parser_for(source)
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        with pg.get_conn() as conn, conn.cursor() as cur:
            cur.execute(SELECT[mode], {"source": source, "version": version})
            marked = cur.rowcount
            conn.commit()
        summary = {"source": source, "mode": mode, "parser_version": version, "marked": marked}
        print(f"backfill reparse: {summary}")
        return summary

    @task(outlets=[Asset(name="raw.source_records.wikidata", uri="asset://raw/source_records/wikidata")])
    def kick(summary: dict[str, str | int]) -> dict[str, str | int]:
        # The outlet is what normalize_catalog listens to. Only the wikidata asset is
        # declared here (Asset outlets must be static); other sources rely on the
        # 15-minute publish cron after normalize is triggered by hand.
        return summary

    kick(mark())


backfill_reparse()
