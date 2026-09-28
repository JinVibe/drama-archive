"""DAG `publish_gold_catalog` — docs/AIRFLOW_DAGS.md §8 (quality gate) + §9 (publish).

Runs when silver.resolved updates, and every 15 minutes regardless so that
records resolved by an admin in the review queue (DM-104) get published
without anyone emitting an asset event.

    quality_gate    : per-record checks; ERROR -> REJECTED. Batch-level gate blocks
                      the run when most of the batch is broken.
    retire_excluded : dramas that a discovery DAG now lists in
                      manifests/{source}/excluded.json (not a drama / foreign) go
                      PUBLISHED -> HIDDEN; ones back in the manifest go HIDDEN -> PUBLISHED.
    publish         : each RESOLVED record in its own transaction:
                      canonical rows + provenance + canonical_version + outbox.

Emits asset://gold/catalog for search/graph downstream.
"""

from __future__ import annotations

import json
import os

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, dag, task
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

from dramamemory_data import staging
from dramamemory_data.publish.gold import publish_record, set_drama_status
from dramamemory_data.quality.checks import check_drama, gate_batch, has_errors
from dramamemory_data.sources import SOURCES

POSTGRES_CONN_ID = "dramamemory_postgres"
S3_CONN_ID = "dramamemory_s3"
RESOLVED_ASSET = Asset(name="silver.resolved", uri="asset://silver/resolved")
GOLD_ASSET = Asset(name="gold.catalog", uri="asset://gold/catalog")


def _taxonomy(cur) -> tuple[set[str], set[str]]:
    cur.execute("SELECT code FROM broadcaster")
    broadcasters = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT code FROM genre")
    genres = {r[0] for r in cur.fetchall()}
    return broadcasters, genres


@dag(
    dag_id="publish_gold_catalog",
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("*/15 * * * *", timezone="UTC"),
        assets=[RESOLVED_ASSET],
    ),
    catchup=False,
    max_active_runs=1,
    tags=["gold", "publish"],
    doc_md=__doc__,
)
def publish_gold_catalog():
    @task
    def quality_gate() -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        with pg.get_conn() as conn, conn.cursor() as cur:
            broadcasters, genres = _taxonomy(cur)
            rows = staging.fetch_by_status(cur, "RESOLVED")
            results = [
                (
                    row.id,
                    check_drama(row.payload, known_broadcasters=broadcasters, known_genres=genres),
                )
                for row in rows
            ]
            rejected = 0
            for staging_id, issues in results:
                if has_errors(issues):
                    staging.set_status(
                        cur, staging_id, "REJECTED", issues=[i.as_dict() for i in issues]
                    )
                    rejected += 1
                elif issues:
                    staging.set_status(
                        cur, staging_id, "RESOLVED", issues=[i.as_dict() for i in issues]
                    )
            conn.commit()
            gate_batch(results)  # raises -> task fails -> nothing publishes
        summary = {"checked": len(results), "rejected": rejected}
        print(f"quality gate summary: {summary}")
        return summary

    @task
    def retire_excluded(gate: dict[str, int]) -> dict[str, int]:
        """Apply discovery verdicts to rows already in gold. Only discovered sources
        write manifests, so the S3 read is scoped to those."""
        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        hidden = restored = 0
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        with pg.get_conn() as conn, conn.cursor() as cur:
            for code, source in SOURCES.items():
                if not source.discovered:
                    continue
                excluded_key = f"manifests/{code}/excluded.json"
                latest_key = f"manifests/{code}/latest.json"
                if s3.check_for_key(excluded_key, bucket_name=bucket):
                    excluded = json.loads(s3.read_key(excluded_key, bucket_name=bucket))["items"]
                    reasons = {e["external_id"]: e["reason"] for e in excluded}
                    hidden += set_drama_status(
                        cur,
                        source_code=code,
                        external_refs=list(reasons),
                        status="HIDDEN",
                        reason=reasons,
                    )
                if s3.check_for_key(latest_key, bucket_name=bucket):
                    items = json.loads(s3.read_key(latest_key, bucket_name=bucket))["items"]
                    restored += set_drama_status(
                        cur,
                        source_code=code,
                        external_refs=[i["external_id"] for i in items],
                        status="PUBLISHED",
                        reason="back in discovery manifest",
                    )
            conn.commit()
        summary = {"hidden": hidden, "restored": restored}
        print(f"retire excluded: {summary}")
        return summary

    @task(outlets=[GOLD_ASSET])
    def publish(gate: dict[str, int]) -> dict[str, int]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        created = updated = 0
        conn = pg.get_conn()
        try:
            with conn.cursor() as cur:
                _, genres = _taxonomy(cur)
                rows = staging.fetch_by_status(cur, "RESOLVED")
            for row in rows:
                with conn.cursor() as cur:
                    result = publish_record(
                        cur,
                        drama=row.payload,
                        resolution=row.resolution,
                        source_id=row.source_id,
                        source_record_id=row.source_record_id,
                        known_genres=genres,
                    )
                    staging.set_status(cur, row.id, "PUBLISHED")
                conn.commit()  # one transaction per record
                if result.created:
                    created += 1
                else:
                    updated += 1
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        summary = {"created": created, "updated": updated}
        print(f"publish summary: {summary}")
        return summary

    publish(retire_excluded(quality_gate()))


publish_gold_catalog()
