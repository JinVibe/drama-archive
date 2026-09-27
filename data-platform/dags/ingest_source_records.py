"""DAG family `ingest_source_records__{source}` — docs/AIRFLOW_DAGS.md §5.

One DAG per registered source so each gets its own pool, schedule and raw asset.
Manifest items are fetched in chunks (dynamic task mapping over chunks, not
items, so a 2,500-item source is ~100 tasks instead of 2,500):

    fetch → validate_http → content_hash → write_object_storage → write_source_record

Idempotency key: source_id + external_id + content_hash. Unchanged pages create
neither a new object nor a new source_record row.

Manifest resolution: manifests/{source}/latest.json in the raw bucket when a
discovery DAG has written one, otherwise the local file named by the `manifest`
param. Sources flagged `discovered` are scheduled on their discovery asset.
"""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.ingestion.manifest import Manifest, dedupe_items, load_manifest
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
    discovery_asset = Asset(
        name=f"raw.discovery.{source_code}", uri=f"asset://raw/discovery/{source_code}"
    )

    @dag(
        dag_id=f"ingest_source_records__{source_code}",
        schedule=[discovery_asset] if source.discovered else None,
        catchup=False,
        max_active_runs=1,
        tags=["ingestion", "raw", source_code],
        params={
            "manifest": Param(
                f"{source_code}.json",
                type="string",
                description="Local manifest file (data-platform/manifests/) used when no "
                "manifests/{source}/latest.json exists in the raw bucket",
            ),
            "chunk_size": Param(25, type="integer", minimum=1, maximum=500),
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
        def load_chunks(params: dict) -> list[list[dict[str, str]]]:
            s3 = S3Hook(aws_conn_id=S3_CONN_ID)
            bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
            key = f"manifests/{source_code}/latest.json"
            if s3.check_for_key(key, bucket_name=bucket):
                manifest = Manifest.model_validate_json(s3.read_key(key, bucket_name=bucket))
                print(f"manifest from s3://{bucket}/{key}")
            else:
                manifest = load_manifest(MANIFEST_DIR / params["manifest"])
                print(f"manifest from local file {params['manifest']}")
            if manifest.source_code != source_code:
                raise ValueError(
                    f"manifest source_code {manifest.source_code!r} != dag source {source_code!r}"
                )
            items = [item.as_task_arg() for item in dedupe_items(manifest.items)]
            size = int(params["chunk_size"])
            chunks = [items[i : i + size] for i in range(0, len(items), size)]
            print(f"{len(items)} items in {len(chunks)} chunks")
            return chunks

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
        def snapshot_chunk(batch: list[dict[str, str]], source_id: int) -> dict[str, int]:
            s3 = S3Hook(aws_conn_id=S3_CONN_ID)
            pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
            bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
            new = unchanged = 0
            with pg.get_conn() as conn:
                for item in batch:
                    result = fetch(item["url"], source)
                    with conn.cursor() as cur:
                        stored = store_snapshot(
                            store=s3, bucket=bucket, cur=cur, source_code=source_code,
                            source_id=source_id, external_id=item["external_id"],
                            entity_type=item["entity_type"], result=result,
                        )
                    conn.commit()  # checkpoint per item: a failed chunk never re-fetches these
                    if stored.source_record_id is None:
                        unchanged += 1
                    else:
                        new += 1
                    if source.min_interval_seconds:
                        time.sleep(source.min_interval_seconds)
            return {"fetched": len(batch), "new_records": new, "unchanged": unchanged}

        @task(outlets=[raw_asset])
        def emit_raw_asset(results: list[dict[str, int]]) -> dict[str, int]:
            summary = {
                "fetched": sum(r["fetched"] for r in results),
                "new_records": sum(r["new_records"] for r in results),
                "unchanged": sum(r["unchanged"] for r in results),
            }
            print(f"ingest summary for {source_code}: {json.dumps(summary)}")
            return summary

        chunks = load_chunks()
        source_id = resolve_source_id()
        results = snapshot_chunk.partial(source_id=source_id).expand(batch=chunks)
        emit_raw_asset(results)

    return ingest_source_records()


for _code in SOURCES:
    globals()[f"ingest_source_records__{_code}"] = build_ingest_dag(_code)
