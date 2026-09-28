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
                if was_review:
                    keep_manual_decisions(row.resolution, resolution)
                status = "REVIEW" if resolution["needs_review"] else "RESOLVED"
                staging.set_status(cur, row.id, status, resolution=resolution)
                if was_review and status == "REVIEW":
                    continue  # still ambiguous, but the queue now shows the current verdicts
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


def keep_manual_decisions(old: dict, new: dict) -> None:
    """An admin decision (method=MANUAL) on one entity must survive re-resolution of
    the record's other entities; only the resolver's own verdicts are recomputed."""
    if old.get("drama", {}).get("method") == "MANUAL":
        new["drama"] = old["drama"]
    for kind in ("persons", "songs", "artists"):
        for key, match in old.get(kind, {}).items():
            if match.get("method") == "MANUAL" and key in new.get(kind, {}):
                new[kind][key] = match
    all_matches = [
        new["drama"], *new["persons"].values(), *new["songs"].values(), *new["artists"].values()
    ]
    new["needs_review"] = any(m.get("decision") == "REVIEW" for m in all_matches)


entity_resolution()
