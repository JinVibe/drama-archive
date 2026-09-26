"""DAG family `ingest_source_records__{source}` — docs/AIRFLOW_DAGS.md §5.

One DAG per registered source so each gets its own pool, schedule and raw asset.
Flow per manifest item (dynamically mapped):

    fetch → validate_http → content_hash → write_object_storage → write_source_record

Idempotency key: source_id + external_id + content_hash. Unchanged pages create
neither a new object nor a new source_record row.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.ingestion.manifest import dedupe_items, load_manifest
from dramamemory_data.ingestion.snapshot import fetch
from dramamemory_data.ingestion.store import store_snapshot
from dramamemory_data.sources import SOURCES, get_source

POSTGRES_CONN_ID = "dramamemory_postgres"
S3_CONN_ID = "dramamemory_s3"
MANIFEST_DIR = Path("/opt/airflow/manifests")


def build_ingest_dag(source_code: str):
    source = get_source(source_code)
    raw_asset = Asset(
        name=f"raw.source_records.{source_code}",
        uri=f"asset://raw/source_records/{source_code}",
    )

    @dag(
        dag_id=f"ingest_source_records__{source_code}",
        schedule=None,  # triggered manually or by the discovery DAG once it exists
        catchup=False,
        max_active_runs=1,
        tags=["ingestion", "raw", source_code],
        params={
            "manifest": Param(
                f"{source_code}.json",
                type="string",
                description="Manifest file name under data-platform/manifests/",
            ),
        },
        default_args={
            "retries": 2,
            "retry_delay": timedelta(minutes=1),
            "retry_exponential_backoff": True,
        },
        doc_md=__doc__,
    )
    def ingest_source_records():
        @task
        def load_items(params: dict) -> list[dict[str, str]]:
            manifest = load_manifest(MANIFEST_DIR / params["manifest"])
            if manifest.source_code != source_code:
                raise ValueError(
                    f"manifest source_code {manifest.source_code!r} != dag source {source_code!r}"
                )
            return [item.as_task_arg() for item in dedupe_items(manifest.items)]

        @task
        def resolve_source_id() -> int:
            hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
            row = hook.get_first(
                "SELECT id, active FROM source WHERE code = %s", parameters=(source_code,)
            )
            if row is None:
                raise RuntimeError(
                    f"source {source_code!r} missing from source table; seed it via migration"
                )
            source_id, active = row
            if not active:
                raise RuntimeError(f"source {source_code!r} is inactive")
            return int(source_id)

        @task(pool=source.pool, max_active_tis_per_dag=4)
        def snapshot_item(item: dict[str, str], source_id: int) -> dict:
            result = fetch(item["url"], source)

            s3 = S3Hook(aws_conn_id=S3_CONN_ID)
            pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
            bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]

            with pg.get_conn() as conn, conn.cursor() as cur:
                stored = store_snapshot(
                    store=s3,
                    bucket=bucket,
                    cur=cur,
                    source_code=source_code,
                    source_id=source_id,
                    external_id=item["external_id"],
                    entity_type=item["entity_type"],
                    result=result,
                )
                conn.commit()

            return {
                "external_id": item["external_id"],
                "entity_type": item["entity_type"],
                "object_key": stored.object_key,
                "content_hash": stored.content_hash,
                "source_record_id": stored.source_record_id,
                "object_written": stored.object_written,
            }

        @task(outlets=[raw_asset])
        def emit_raw_asset(results: list[dict]) -> dict[str, int]:
            new = sum(1 for r in results if r["source_record_id"] is not None)
            summary = {"fetched": len(results), "new_records": new, "unchanged": len(results) - new}
            print(f"ingest summary for {source_code}: {summary}")
            return summary

        items = load_items()
        source_id = resolve_source_id()
        results = snapshot_item.partial(source_id=source_id).expand(item=items)
        emit_raw_asset(results)

    return ingest_source_records()


for _code in SOURCES:
    globals()[f"ingest_source_records__{_code}"] = build_ingest_dag(_code)
