"""DAG `source_discovery_wikidata` — docs/AIRFLOW_DAGS.md §4 for the `wikidata` source.

Weekly (and on demand). Builds the manifest of Korean dramas to fetch from two
lists — a broad Wikidata SPARQL query and the per-year Korean Wikipedia drama
categories — and classifies every candidate as drama / not a drama / unknown
(dramamemory_data.discovery.wikidata, normalization.program_kind). Writes

    manifests/wikidata/latest.json     items to fetch (DRAMA + UNKNOWN), dated copy too
    manifests/wikidata/excluded.json   NOT_DRAMA and foreign items with the reason;
                                       publish_gold_catalog hides anything already
                                       published that appears here

and emits raw.discovery.wikidata so ingest_source_records__wikidata runs.

Quality rule (§4): if the new count is under 60% of the previous manifest, the
run fails instead of publishing a manifest that would look like mass deletion.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import httpx
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.sdk import Asset, Param, dag, task

from dramamemory_data.discovery import wikidata as disc
from dramamemory_data.sources import get_source

S3_CONN_ID = "dramamemory_s3"
SOURCE = "wikidata"
DISCOVERY_ASSET = Asset(name=f"raw.discovery.{SOURCE}", uri=f"asset://raw/discovery/{SOURCE}")
LATEST_KEY = f"manifests/{SOURCE}/latest.json"
EXCLUDED_KEY = f"manifests/{SOURCE}/excluded.json"


@dag(
    dag_id="source_discovery_wikidata",
    schedule="@weekly",
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "discovery", SOURCE],
    params={"year_from": Param(2006, type="integer", minimum=1950, maximum=2100)},
    doc_md=__doc__,
)
def source_discovery_wikidata():
    @task(pool=get_source(SOURCE).pool, outlets=[DISCOVERY_ASSET])
    def discover(params: dict) -> dict[str, int | str]:
        wikidata = get_source(SOURCE)
        kowiki = get_source("kowiki")
        year_from = int(params["year_from"])
        year_to = datetime.now(UTC).year + 1

        with httpx.Client(follow_redirects=True) as client:
            sparql_qids = disc.list_qids(
                client, year_from=year_from, user_agent=wikidata.user_agent
            )
            print(f"sparql candidates: {len(sparql_qids)}")

            kowiki_pages: dict[str, dict] = {}
            for category in disc.year_categories(year_from, year_to):
                members = disc.category_members(
                    client,
                    category,
                    user_agent=kowiki.user_agent,
                    min_interval=kowiki.min_interval_seconds,
                )
                kowiki_pages.update(members)
                print(f"{category}: {len(members)} pages")

            qids = sorted(sparql_qids | {p["qid"] for p in kowiki_pages.values() if p.get("qid")})
            details = disc.fetch_details(
                client,
                qids,
                user_agent=wikidata.user_agent,
                min_interval=wikidata.min_interval_seconds,
            )
            cands = disc.build_candidates(sparql_qids, kowiki_pages, details)
            for c in cands.values():
                c.decide()

            # Ambiguous items with an article: let its categories decide.
            lookup = [c for c in cands.values() if disc.needs_category_lookup(c)]
            cats = disc.page_categories(
                client,
                [c.article for c in lookup],
                user_agent=kowiki.user_agent,
                min_interval=kowiki.min_interval_seconds,
            )
            for c in lookup:
                c.kowiki_categories = cats.get(c.article, [])
                c.decide()

        items, excluded = disc.decide(cands)
        kinds = {k: sum(1 for i in items if i["kind"] == k) for k in ("DRAMA", "UNKNOWN")}
        reasons = {
            r: sum(1 for e in excluded if e["reason"] == r) for r in ("not_a_drama", "foreign")
        }

        s3 = S3Hook(aws_conn_id=S3_CONN_ID)
        bucket = os.environ["DRAMAMEMORY_RAW_BUCKET"]
        previous = 0
        if s3.check_for_key(LATEST_KEY, bucket_name=bucket):
            previous = len(json.loads(s3.read_key(LATEST_KEY, bucket_name=bucket)).get("items", []))
        if previous and len(items) < previous * 0.6:
            raise RuntimeError(
                f"discovery dropped from {previous} to {len(items)} items; not publishing manifest"
            )

        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
        manifest = json.dumps({"source_code": SOURCE, "items": items}, ensure_ascii=False)
        s3.load_string(
            manifest, key=f"manifests/{SOURCE}/{stamp}.json", bucket_name=bucket, replace=True
        )
        s3.load_string(manifest, key=LATEST_KEY, bucket_name=bucket, replace=True)
        s3.load_string(
            json.dumps(
                {"source_code": SOURCE, "generated_at": stamp, "items": excluded},
                ensure_ascii=False,
            ),
            key=EXCLUDED_KEY,
            bucket_name=bucket,
            replace=True,
        )
        summary = {
            "items": len(items),
            "previous": previous,
            "sparql": len(sparql_qids),
            "kowiki_pages": len(kowiki_pages),
            "category_lookups": len(lookup),
            **kinds,
            **reasons,
            "manifest": LATEST_KEY,
        }
        print(f"wikidata discovery: {summary}")
        return summary

    discover()


source_discovery_wikidata()
