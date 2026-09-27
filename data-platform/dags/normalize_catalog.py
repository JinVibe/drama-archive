"""DAG `normalize_catalog` — docs/AIRFLOW_DAGS.md §6.

Runs when any raw source_records asset updates. For every DRAMA source_record
without a staging row (or whose previous parse failed):

    load raw object → parse (source-specific) → normalize → validate → staging_record

Parse failures are dead-lettered as status PARSE_FAILED with the error; they are
not retried on the same payload. A new parser version re-parses them.
"""

from __future__ import annotations

import os

from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import Asset, AssetAny, dag, task

from dramamemory_data import staging
from dramamemory_data.parsers import parser_for
from dramamemory_data.sources import SOURCES

POSTGRES_CONN_ID = "dramamemory_postgres"
S3_CONN_ID = "dramamemory_s3"

RAW_ASSETS = [
    Asset(name=f"raw.source_records.{code}", uri=f"asset://raw/source_records/{code}")
    for code in SOURCES
]
SILVER_ASSET = Asset(name="silver.catalog", uri="asset://silver/catalog")


@dag(
    dag_id="normalize_catalog",
    schedule=AssetAny(*RAW_ASSETS),
    catchup=False,
    max_active_runs=1,
    tags=["silver", "normalize"],
    doc_md=__doc__,
)
def normalize_catalog():
    @task
    def select_unparsed() -> list[dict]:
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        rows = pg.get_records(staging.SELECT_UNPARSED)
        return [
            {"source_record_id": r[0], "source_code": r[1], "object_key": r[3], "source_url": r[4]}
            for r in rows
        ]

    @task(outlets=[SILVER_ASSET])
    def parse_and_stage(records: list[dict]) -> dict[str, int]:
        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        pg = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        parsed = failed = skipped = 0

        with pg.get_conn() as conn, conn.cursor() as cur:
            for rec in records:
                try:
                    parser_version, parse = parser_for(rec["source_code"])
                except KeyError:
                    skipped += 1
                    continue
                body = s3.get_key(rec["object_key"], bucket_name=bucket).get()["Body"].read()
                try:
                    drama = parse(body)
                except ValueError as exc:  # parser errors are ValueError subclasses
                    staging.upsert_parse_failed(
                        cur,
                        source_record_id=rec["source_record_id"],
                        parser_version=parser_version,
                        error=str(exc),
                    )
                    failed += 1
                    continue
                staging.upsert_parsed(
                    cur,
                    source_record_id=rec["source_record_id"],
                    parser_version=parser_version,
                    drama=drama,
                )
                parsed += 1
            conn.commit()

        summary = {"parsed": parsed, "parse_failed": failed, "no_parser": skipped}
        print(f"normalize summary: {summary}")
        return summary

    parse_and_stage(select_unparsed())


normalize_catalog()
