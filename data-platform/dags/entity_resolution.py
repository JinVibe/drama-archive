"""DAG `entity_resolution` — docs/AIRFLOW_DAGS.md §7.

Runs when the silver catalog asset updates. For every staging_record in status
NEW, decides per nested entity: AUTO_MERGE (canonical id), REVIEW, or CREATE_NEW.
Records with any REVIEW decision go to the admin review queue (status REVIEW);
the rest become RESOLVED and flow to publish_gold_catalog.

Records already in REVIEW are re-resolved too: once an admin has decided one
record for a person (which publishes a source_entity_map row with that person's
external_ref), every other pending record naming the same person resolves by
EXTERNAL_ID on the next run. One decision per person, not per drama.
"""

from __future__ import annotations

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from dramamemory_data import staging
from dramamemory_data.entity_resolution.matching import resolve_record
from dramamemory_data.entity_resolution.repo import PostgresRepo

POSTGRES_CONN_ID = "dramamemory_postgres"
SILVER_ASSET = Asset(name="silver.catalog", uri="asset://silver/catalog")
RESOLVED_ASSET = Asset(name="silver.resolved", uri="asset://silver/resolved")


@dag(
    dag_id="entity_resolution",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("*/15 * * * *", timezone="UTC"),
        assets=[SILVER_ASSET],
    ),
    catchup=False,
    max_active_runs=1,
    tags=["silver", "entity-resolution"],
    doc_md=__doc__,
)
def entity_resolution():
    @task(outlets=[RESOLVED_ASSET])
    def resolve_new_records() -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        resolved = review = cleared = 0
        with pg.get_conn() as conn, conn.cursor() as cur:
            repo = PostgresRepo(cur)
            rows = staging.fetch_by_status(cur, "NEW") + staging.fetch_by_status(cur, "REVIEW")
            for row in rows:
                was_review = row.resolution is not None and row.resolution.get("needs_review")
                resolution = resolve_record(row.payload, row.source_id, repo)
                status = "REVIEW" if resolution["needs_review"] else "RESOLVED"
                if was_review and status == "REVIEW":
                    continue  # still ambiguous: keep the queue entry untouched
                staging.set_status(cur, row.id, status, resolution=resolution)
                if was_review:
                    cleared += 1
                elif status == "REVIEW":
                    review += 1
                else:
                    resolved += 1
            conn.commit()
        summary = {"resolved": resolved, "review": review, "review_cleared": cleared}
        print(f"entity resolution summary: {summary}")
        return summary

    resolve_new_records()


entity_resolution()
